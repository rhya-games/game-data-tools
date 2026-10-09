#!/usr/bin/env python3
"""Build index/quests.jsonl: every quest in the game, with the items each one asks for.
  build_quests.py [--client OngoingQuests.lub] [--out FILE]
Sources (all read from the data folder, nothing is downloaded here):
  client file   pages/downloads/OngoingQuests.lub  title, description and summary of ~11,000 quests (ROenglishRE translation)
  quest_db      rathena/db/{pre-re,re}/quest_db.yml  title, time limit, kill targets, item drop targets
  NPC scripts   rathena/npc/**  the quest ids an NPC sets/checks/completes, the items it takes (delitem, countitem) and gives (getitem)
--uaro CSV (default notes/quest-uaro.csv) records what is and is not on uaRO. Columns: scope,value,status,note (status yes or no, default no). Scopes: file (an NPC script path, or a folder
ending in /), quest (an id), range (ids a-b), title (text in the title). A quest from scripts is marked "no" when every NPC that handles
it is in the marked files, and "yes" when any of them is; id, range and title rules mark it directly. The first matching rule wins, so put exceptions first. Unmarked quests are "unknown".
uaRO's own quests (hat, weapon, pet and other quests) come from data/uaro-quests.json, which this repo owns (seeded by import_loot_sheet.py).
They appear as quests with ids like uaro-mystic-rose, origin "uaro", status yes, and their ingredients as items taken.
Script facts are heuristic: an item is attached to the nearest quest id mentioned before it in the same NPC (or the first one after it),
and every item carries the NPC, map and file it came from so it can be checked. Items given as variables or expressions are skipped."""
import argparse, json, os, re, sys
from pathlib import Path
ROOT = os.environ.get('GAME_DATA', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def die(msg): sys.exit(f'error: {msg}')

# ---- client quest list -------------------------------------------------------------------------------------------------------------
def lua_string(s): return s.replace('\\"', '"').replace('\\\\', '\\')

def parse_client(path):
    t = Path(path).read_text(encoding='utf-8', errors='replace')
    out = {}
    for m in re.finditer(r'^\t\[(\d+)\] = \{\n(.*?)^\t\},?$', t, re.S | re.M):
        b = m.group(2)
        title = re.search(r'^\t\tTitle = "((?:[^"\\]|\\.)*)"', b, re.M)
        desc = re.search(r'^\t\tDescription = \{(.*?)^\t\t\}', b, re.S | re.M)
        summ = re.search(r'^\t\tSummary = "((?:[^"\\]|\\.)*)"', b, re.M)
        lines = [lua_string(x) for x in re.findall(r'"((?:[^"\\]|\\.)*)"', desc.group(1))] if desc else []
        out[int(m.group(1))] = {'title': lua_string(title.group(1)) if title else '', 'description': lines, 'summary': lua_string(summ.group(1)) if summ else ''}
    return out

# ---- emulator databases ------------------------------------------------------------------------------------------------------------
def load_items(rathena):
    """aegis name (lower) -> (id, display name); id -> display name"""
    import glob, yaml
    loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader); by_aegis, by_id = {}, {}
    for mode in ('pre-re', 're'):
        for f in glob.glob(f'{rathena}/db/{mode}/item_db_*.yml'):
            for d in yaml.load(Path(f).read_text(encoding='utf-8'), Loader=loader).get('Body', []):
                nm = d.get('Name', d.get('AegisName'))
                by_aegis.setdefault(str(d['AegisName']).lower(), (d['Id'], nm)); by_id.setdefault(d['Id'], nm)
    return by_aegis, by_id

def parse_quest_db(rathena, mode, by_aegis):
    import yaml
    loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
    path = Path(rathena) / 'db' / mode / 'quest_db.yml'
    if not path.is_file(): return {}
    out = {}
    for d in yaml.load(path.read_text(encoding='utf-8'), Loader=loader).get('Body', []):
        q = {'title': d.get('Title', ''), 'time_limit': d.get('TimeLimit', 0), 'targets': [{k.lower(): v for k, v in t.items() if k in ('Mob', 'Count', 'Location')} for t in d.get('Targets', [])], 'drops': []}
        for x in d.get('Drops', []):
            it = by_aegis.get(str(x.get('Item')).lower())
            q['drops'].append({'mob': x.get('Mob'), 'item': it[0] if it else None, 'item_name': it[1] if it else x.get('Item'), 'count': x.get('Count', 1), 'rate': x.get('Rate')})
        out[d['Id']] = q
    return out

# ---- NPC scripts -------------------------------------------------------------------------------------------------------------------
QUEST_CALL = re.compile(r'\b(setquest|checkquest|completequest|erasequest|questprogress|isbegin_quest|changequest)\b\s*\(?\s*(\d{3,6})(?:\s*,\s*(\d{3,6}))?')
DEL = re.compile(r'\b(delitem2?)\b\s*\(?\s*([A-Za-z_]\w*|\d+)\s*,\s*([^;)]+)')
COUNT = re.compile(r'\bcountitem2?\s*\(\s*([A-Za-z_]\w*|\d+)\s*\)\s*(<=|>=|==|!=|<|>)?\s*(\d+)?')
GET = re.compile(r'\b(getitem2?|getitembound2?)\b\s*\(?\s*([A-Za-z_]\w*|\d+)\s*,\s*([^;),]+)')
NPC_HEAD = re.compile(r'^(?:(?P<map>[\w@.\-]+),\d+,\d+,\d+|-|function)\t(?:script|shop|cashshop)\t(?P<name>[^\t]+)\t')

def strip_comments(text):
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    return re.sub(r'//[^\n]*', '', text)

def split_npcs(text):
    """Yield (map, name, body) for each script block (a header line at column 0 up to the closing } at column 0)."""
    lines = text.split('\n'); i = 0
    while i < len(lines):
        m = NPC_HEAD.match(lines[i])
        if m and lines[i].rstrip().endswith('{'):
            j = i + 1
            while j < len(lines) and not re.match(r'^\}\s*$', lines[j]): j += 1
            yield (m.group('map') or '', m.group('name'), '\n'.join(lines[i + 1:j])); i = j
        i += 1

def resolve(token, by_aegis, by_id):
    if token.isdigit(): return int(token), by_id.get(int(token), '')
    hit = by_aegis.get(token.lower())
    return (hit[0], hit[1]) if hit else (None, token)

def qty(expr):
    e = expr.strip()
    return int(e) if e.isdigit() else None

def needed(comparison, n):
    """How many an NPC wants when it tests countitem(x) <comparison> n (it checks for having enough, or for lacking)."""
    if n is None: return None
    return {'>': n + 1, '<=': n + 1, '!=': max(n, 1)}.get(comparison, n)

def parse_script(text, by_aegis, by_id):
    """[(npc name, map, quest ids (ordered), items [(kind, item id, name, qty, comparator, quest id or None)])]"""
    out = []
    for mp, name, body in split_npcs(strip_comments(text)):
        events = []   # (position, 'quest'|'item', payload)
        for m in QUEST_CALL.finditer(body):
            ids = [int(x) for x in (m.group(2), m.group(3)) if x]
            for q in ids: events.append((m.start(), 'quest', (m.group(1), q)))
        for m in DEL.finditer(body):
            iid, nm = resolve(m.group(2), by_aegis, by_id); events.append((m.start(), 'item', ('takes', iid, nm, qty(m.group(3)), None)))
        for m in COUNT.finditer(body):
            iid, nm = resolve(m.group(1), by_aegis, by_id); events.append((m.start(), 'item', ('checks', iid, nm, needed(m.group(2), int(m.group(3)) if m.group(3) else None), m.group(2))))
        for m in GET.finditer(body):
            iid, nm = resolve(m.group(2), by_aegis, by_id); events.append((m.start(), 'item', ('gives', iid, nm, qty(m.group(3)), None)))
        events.sort(key=lambda e: e[0])
        quests = list(dict.fromkeys(p[1] for _, k, p in events if k == 'quest'))
        if not quests: continue
        current, pending, items = None, [], []
        for _, kind, p in events:
            if kind == 'quest': current = p[1]; items += [it + (current,) for it in pending]; pending = []
            elif current is not None: items.append(p + (current,))
            else: pending.append(p)
        items += [p + (quests[0],) for p in pending]   # items seen before any quest id belong to the first quest the NPC mentions
        out.append((name, mp, quests, items))
    return out

def script_mode(rel):
    parts = rel.split('/')
    return 'pre-re' if 'pre-re' in parts else 're' if 're' in parts else 'both'

def parse_npcs(rathena, by_aegis, by_id):
    """{quest id: {'npcs': [...], 'items': [...]}}"""
    base = Path(rathena) / 'npc'
    if not base.is_dir(): return {}
    quests = {}
    for f in sorted(base.rglob('*.txt')):
        text = f.read_text(encoding='utf-8', errors='replace')
        if 'quest' not in text: continue
        rel = f.relative_to(rathena).as_posix(); mode = script_mode(rel)
        for name, mp, ids, items in parse_script(text, by_aegis, by_id):
            for q in ids:
                e = quests.setdefault(q, {'npcs': [], 'items': []}); npc = {'name': name, 'map': mp, 'file': rel, 'mode': mode}
                if npc not in e['npcs']: e['npcs'].append(npc)
            for kind, iid, nm, n, cmp_, q in items:
                it = {'relation': kind, 'item': iid, 'item_name': nm, 'qty': n, 'npc': name, 'map': mp, 'file': rel, 'mode': mode}
                if cmp_: it['comparison'] = cmp_
                e = quests[q]
                if it not in e['items']: e['items'].append(it)
    return quests

def load_uaro_rules(path):
    import csv
    if not path or not os.path.isfile(path): return []
    with open(path, encoding='utf-8', newline='') as f: rules = [r for r in csv.DictReader(f) if (r.get('scope') or '').strip() and not r['scope'].startswith('#')]
    for r in rules:
        if r['scope'] not in ('file', 'quest', 'range', 'title'): die(f'{path}: unknown scope {r["scope"]!r} (use file, quest, range or title)')
        r['status'] = (r.get('status') or 'no').strip().lower()
        if r['status'] not in ('yes', 'no'): die(f'{path}: status must be yes or no, not {r["status"]!r}')
    return rules

def uaro_status(qid, title, npcs, rules):
    """('yes' or 'no', rule note) from the first rule that matches the quest, else ('unknown', '')."""
    for r in rules:
        v, scope = r['value'].strip(), r['scope']
        if scope == 'quest' and str(qid) == v: return r['status'], r.get('note', '')
        if scope == 'range':
            lo, _, hi = v.partition('-')
            if lo.isdigit() and hi.isdigit() and int(lo) <= qid <= int(hi): return r['status'], r.get('note', '')
        if scope == 'title' and v.lower() in title.lower(): return r['status'], r.get('note', '')
        if scope == 'file' and npcs:
            hit = [n['file'] == v or (v.endswith('/') and n['file'].startswith(v)) for n in npcs]
            if (r['status'] == 'yes' and any(hit)) or (r['status'] == 'no' and all(hit)): return r['status'], r.get('note', '')
    return 'unknown', ''

def uaro_rows(path):
    """Index rows for the uaRO quests in data/uaro-quests.json (records flagged is_quest)."""
    if not path or not os.path.isfile(path): return []
    rows = []
    for r in json.loads(Path(path).read_text(encoding='utf-8')).get('quests', []):
        if not r.get('is_quest'): continue
        items = [{'relation': 'takes', 'item': i.get('item_id'), 'item_name': i['item'], 'qty': i.get('qty'), 'npc': r.get('npc') or '', 'map': r.get('location') or '', 'file': 'data/uaro-quests.json', 'mode': 'uaro'} | ({'note': i['note']} if i.get('note') else {}) for i in r['ingredients']]
        rows.append({'id': r['id'], 'title': r['name'], 'origin': 'uaro', 'uaro': 'yes', 'uaro_note': 'uaRO quest data (' + ', '.join(r.get('categories', [])) + ')', 'client': None, 'db': {}, 'npcs': [], 'items': items, 'categories': r.get('categories', []), 'wiki': r.get('wiki')})
    return rows

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--uaro-data', default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'uaro-quests.json'))
    ap.add_argument('--client', default=f'{ROOT}/pages/downloads/OngoingQuests.lub'); ap.add_argument('--rathena', default=f'{ROOT}/rathena')
    ap.add_argument('--out', default=f'{ROOT}/index/quests.jsonl'); ap.add_argument('--uaro', default=f'{ROOT}/notes/quest-uaro.csv', help='CSV of rules marking quests that are not on uaRO')
    a = ap.parse_args(argv)
    if not os.path.isdir(a.rathena): die(f'{a.rathena} not found. Run setup.sh.')
    client = parse_client(a.client) if os.path.isfile(a.client) else {}
    if not client: print(f'note: {a.client} not found or empty, so quests will have no client text (see README)', file=sys.stderr)
    by_aegis, by_id = load_items(a.rathena)
    dbs = {m: parse_quest_db(a.rathena, m, by_aegis) for m in ('pre-re', 're')}
    scripts = parse_npcs(a.rathena, by_aegis, by_id); rules = load_uaro_rules(a.uaro)
    ids = sorted(set(client) | set(dbs['pre-re']) | set(dbs['re']) | set(scripts))
    os.makedirs(os.path.dirname(a.out), exist_ok=True); tmp = a.out + '.tmp'; marked = 0
    with open(tmp, 'w', encoding='utf-8') as f:
        for i in ids:
            c = client.get(i); s = scripts.get(i, {'npcs': [], 'items': []})
            title = (c or {}).get('title') or next((dbs[m][i]['title'] for m in ('re', 'pre-re') if i in dbs[m]), '')
            status, why = uaro_status(i, title, s['npcs'], rules)
            row = {'id': i, 'title': title, 'uaro': status, 'uaro_note': why, 'client': c, 'db': {m: dbs[m][i] for m in dbs if i in dbs[m]}, 'npcs': s['npcs'], 'items': s['items']}
            f.write(json.dumps(row, ensure_ascii=False) + '\n'); marked += status != 'unknown'
        extra = uaro_rows(a.uaro_data)
        for row in extra: f.write(json.dumps(row, ensure_ascii=False) + '\n')
    os.replace(tmp, a.out)
    asked = sum(1 for i in ids if any(x['relation'] in ('takes', 'checks') for x in scripts.get(i, {}).get('items', [])))
    print(f'{len(ids)} official quests ({marked} marked yes/no for uaRO) + {len(extra)} uaRO quests -> {a.out}: {len(client)} with client text, {len(dbs["pre-re"])} pre-re / {len(dbs["re"])} re in quest_db, {len(scripts)} found in NPC scripts, {asked} asking for items')
    return 0

if __name__ == '__main__':
    sys.exit(main())
