#!/usr/bin/env python3
"""Add what the uaRO wiki says about quests (NPC, location, level range, rewards) to data/uaro-quests.json.
  import_wiki_quests.py --wiki ~/Projects/uaro-docs/docs [--page repeatable-quests] [--data data/uaro-quests.json] [--overwrite] [--dry-run]
Each supported wiki page is parsed into quest rows. A row is matched to an existing record by name, else by its ingredient list (item names and
quantities); a row that matches nothing becomes a NEW record with source 'wiki'; a row that matches several records is listed in the report and
left alone. Matched records only get the fields they lack: a field you set by hand (or an earlier run set) is never overwritten, and a different
wiki value is reported as a difference (--overwrite takes the wiki's value instead). Records that came from the wiki and a re-run of
import_loot_sheet.py both stay: a record with a wiki link is a quest, whatever its ingredients say. Re-running changes nothing.
Pages: repeatable-quests (item turn-in and monster hunting quests)."""
import argparse, json, os, re, sys
from pathlib import Path
from import_loot_sheet import slug
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = 'https://wiki.uaro.net'
WIKI_FIELDS = ('npc', 'location', 'min_level', 'max_level', 'rewards', 'hunt', 'wiki')

def die(msg): sys.exit(f'error: {msg}')

def norm(s): return re.sub(r'[^a-z0-9]+', '', s.lower())

def clean(cell): return re.sub(r'\s+', ' ', re.sub(r'!\[[^\]]*\]\([^)]*\)|<[^>]+>|\*\*|`', ' ', cell)).strip()

def num(cell):
    m = re.search(r'\d[\d,]*', cell)
    return int(m.group().replace(',', '')) if m else None

def navi(cell):
    m = re.search(r'/navi\s+(\S+)\s+(\d+)/(\d+)', cell)
    return f'{m.group(1)} {m.group(2)}/{m.group(3)}' if m else None

def md_tables(text):
    """[(nearest heading above, [header names], [{header: raw cell}])] for every pipe table in a markdown page."""
    out, heading, lines, i = [], '', text.splitlines(), 0
    while i < len(lines):
        l = lines[i]
        if l.startswith('#'): heading = l.lstrip('#').strip()
        if l.lstrip().startswith('|') and i + 1 < len(lines) and re.match(r'^\s*\|[\s:|-]+\|\s*$', lines[i + 1]):
            cells = lambda s: [c.strip() for c in s.strip().strip('|').split('|')]
            head = [clean(c) for c in cells(l)]; rows = []; i += 2
            while i < len(lines) and lines[i].lstrip().startswith('|'):
                row = cells(lines[i]); rows.append(dict(zip(head, row))); i += 1
            out.append((heading, head, rows)); continue
        i += 1
    return out

def repeatable_quests(text, page='repeatable-quests'):
    """(rows, warnings) from repeatable-quests.md: the item turn-in table and the monster hunting table. Rows say 'npc' and the quest name,
    levels, location, rewards (what the wiki lists for the quest as written), plus 'ingredients' (turn-ins) or 'hunt' (monster and kill counts)."""
    rows, warn = [], []
    m = re.search(r'choice of how many monsters[^\n]*?options of ([^.\n]*)', text)
    counts = [int(x) for x in re.findall(r'\*\*(\d+)\*\*', m.group(1))] if m else []
    if not counts: warn.append('hunting kill counts (50/100/150) not found in the page text; hunt.counts left out')
    for heading, head, trs in md_tables(text):
        item_table, hunt_table = 'Items' in head, 'Monster' in head
        if not (item_table or hunt_table) or 'NPC' not in head: continue
        for tr in trs:
            npc = clean(tr.get('NPC', ''))
            row = {'npc': npc, 'location': navi(tr.get('Location', '')), 'min_level': num(tr.get('Min Level', '')), 'max_level': num(tr.get('Max Level', '')),
                   'rewards': {'base_exp': num(tr.get('Base EXP', '')), 'job_exp': num(tr.get('Job EXP', ''))}, 'wiki': f'{SITE}/{page}/', 'page': page}
            if not npc or None in (row['location'], row['min_level'], row['max_level'], *row['rewards'].values()):
                warn.append(f'{heading}: could not read row {npc or tr}'); continue
            if item_table:
                m = re.match(r'^(\d[\d,]*)\s+(.+)$', clean(tr.get('Items', '')))
                if not m: warn.append(f'{heading}: could not read the item of {npc}: {tr.get("Items")!r}'); continue
                row.update(name=f'{npc} Repeatable Quest', ingredients=[{'item': m.group(2), 'qty': int(m.group(1).replace(',', ''))}], categories=['Repeatable Quest'])
            else:
                mob = clean(tr.get('Monster', ''))
                row.update(name=f'{npc} Hunting Quest', ingredients=[], categories=['Repeatable Quest', 'Hunting Quest'],
                           hunt={'monster': mob.rstrip('*').strip(), 'quest_access': mob.endswith('*'), **({'counts': counts, 'rewards_for': counts[0]} if counts else {})})
            rows.append(row)
    return rows, warn

PAGES = {'repeatable-quests': repeatable_quests}

def ing_key(ings): return frozenset((norm(i['item']), i.get('qty')) for i in ings)

def apply_rows(records, rows, overwrite=False):
    """Merge wiki rows into the record list (in place). Returns a report dict of lists."""
    rep = {k: [] for k in ('by_name', 'by_ingredients', 'created', 'ambiguous', 'differs', 'ingredient_diffs', 'changed')}
    by_name = {norm(r['name']): r for r in records}; ids = {i['item']: i.get('item_id') for r in records for i in r['ingredients'] if i.get('item_id')}
    for row in rows:
        rec = by_name.get(norm(row['name'])); how = 'by_name'
        if rec is None and row['ingredients']:
            hit = [r for r in records if r['ingredients'] and ing_key(r['ingredients']) == ing_key(row['ingredients'])]
            if len(hit) > 1: rep['ambiguous'].append(f"{row['name']}: ingredients match {', '.join(r['name'] for r in hit)}"); continue
            rec, how = (hit[0] if hit else None), 'by_ingredients'
        if rec is None:
            rec = {'id': slug(row['name']), 'name': row['name'], 'categories': row['categories'], 'ingredients': [{k: v for k, v in (('item_id', ids.get(i['item'])), ('item', i['item']), ('qty', i['qty'])) if v is not None} for i in row['ingredients']], 'is_quest': True, 'source': 'wiki'}
            records.append(rec); by_name[norm(rec['name'])] = rec; rep['created'].append(row['name']); rep['changed'].append(rec['id'])
        else:
            rep[how].append(f"{row['name']} -> {rec['name']}" if rec['name'] != row['name'] else row['name'])
            if row['ingredients'] and ing_key(rec['ingredients']) != ing_key(row['ingredients']):
                rep['ingredient_diffs'].append(f"{rec['name']}: wiki {[(i['qty'], i['item']) for i in row['ingredients']]}, record {[(i.get('qty'), i['item']) for i in rec['ingredients']]}")
            if not rec.get('is_quest'): rec['is_quest'] = True; rep['changed'].append(rec['id'])
        for f in WIKI_FIELDS:
            if f not in row: continue
            if f not in rec: rec[f] = row[f]
            elif rec[f] != row[f]:
                if overwrite: rec[f] = row[f]
                else: rep['differs'].append(f"{rec['name']}: {f} is {rec[f]!r}, wiki says {row[f]!r}"); continue
            else: continue
            if rec['id'] not in rep['changed']: rep['changed'].append(rec['id'])
    return rep

def print_report(rep, warn, rows):
    print(f"{len(rows)} wiki quests read: {len(rep['by_name'])} matched by name, {len(rep['by_ingredients'])} by ingredients, {len(rep['created'])} new, {len(rep['ambiguous'])} ambiguous; {len(set(rep['changed']))} records changed")
    for title, key in (('matched by ingredients (check these)', 'by_ingredients'), ('NEW records from the wiki', 'created'), ('AMBIGUOUS, not touched', 'ambiguous'), ('wiki and record disagree, kept the record (use --overwrite to take the wiki)', 'differs'), ('ingredients differ between wiki and loot sheet (not changed)', 'ingredient_diffs')):
        if rep[key]: print(f'\n{title}:'); [print('  ' + x) for x in rep[key]]
    if warn: print('\nwarnings:'); [print('  ' + w) for w in warn]

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--wiki', required=True, help='the wiki docs folder'); ap.add_argument('--data', default=f'{REPO}/data/uaro-quests.json')
    ap.add_argument('--page', action='append', choices=sorted(PAGES), help='page to import (default: all supported)')
    ap.add_argument('--overwrite', action='store_true', help="take the wiki's value where a record has a different one"); ap.add_argument('--dry-run', action='store_true', help='report only, write nothing')
    a = ap.parse_args(argv)
    if not os.path.isfile(a.data): die(f'{a.data} not found. Run import_loot_sheet.py first.')
    doc = json.loads(Path(a.data).read_text(encoding='utf-8')); rows, warn = [], []
    for page in a.page or sorted(PAGES):
        f = Path(a.wiki) / f'{page}.md'
        if not f.is_file(): die(f'{f} not found')
        r, w = PAGES[page](f.read_text(encoding='utf-8'), page); rows += r; warn += w
    rep = apply_rows(doc['quests'], rows, a.overwrite); doc['quests'].sort(key=lambda r: r['name'].lower())
    print_report(rep, warn, rows)
    if not a.dry_run and rep['changed']:
        Path(a.data).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8'); print(f'\nwrote {a.data}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
