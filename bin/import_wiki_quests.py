#!/usr/bin/env python3
"""Add what the uaRO wiki says about quests (NPC, location, level range, rewards) to data/uaro-quests.json.
  import_wiki_quests.py --wiki ~/Projects/uaro-docs/docs [--page repeatable-quests] [--data data/uaro-quests.json] [--overwrite] [--dry-run]
Each supported wiki page is parsed into quest rows. A row is matched to an existing record by name, else by a similar name (slots like [1] and
brackets ignored; listed so you can check), else by its ingredient list (item names and quantities); a row that matches nothing becomes a NEW record with source 'wiki'; a row that matches several records is listed in the report and
left alone. Matched records only get the fields they lack: a field you set by hand (or an earlier run set) is never overwritten, and a different
wiki value is reported as a difference (--overwrite takes the wiki's value instead). Records that came from the wiki and a re-run of
import_loot_sheet.py both stay: a record with a wiki link is a quest, whatever its ingredients say. Re-running changes nothing.
Pages: repeatable-quests (item turn-in and monster hunting quests), dimonka-headgear-quest (headgear for Poring Coins and loot),
king-frog-hat (one hat quest written as prose with an item table), expanded-class-weapons (a token recipe and the weapons it
buys)."""
import argparse, json, os, re, sys
from pathlib import Path
from import_loot_sheet import slug
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = 'https://wiki.uaro.net'
WIKI_FIELDS = ('npc', 'location', 'min_level', 'max_level', 'zeny', 'rewards', 'hunt', 'notes', 'wiki')

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

def repeatable_quests(text, page='repeatable-quests', read=None):
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

def img_id(cell):
    """The item id in an <img src=".../5747.gif"> (or 7539_1.png) of a table cell, else None (card.gif and the like)."""
    m = re.search(r'src="[^"]*?/(\d+)(?:_\d+)?\.(?:gif|png)"', cell)
    return int(m.group(1)) if m else None

def dimonka_headgear(text, page='dimonka-headgear-quest', read=None):
    """(rows, warnings) from dimonka-headgear-quest.md: one HTML table row per hat, with the materials as 'Name - qty' lines. Dimonka stands
    inside the Main Office; its /navi spot comes from main-office.md (the office entrance, so it is noted as that)."""
    rows, warn = [], []
    office = re.search(r'Main Office[^\n]*?`/navi\s+(\S+)\s+(\d+)/(\d+)`', (read or (lambda n: ''))('main-office') or '')
    if not office: warn.append("could not read the Main Office's /navi spot from main-office.md; location left out")
    for tr in re.findall(r'<tr>(.*?)</tr>', text, re.S):
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)
        if len(tds) < 2: continue                                   # the header row has <th> cells
        full = clean(tds[0])
        if not full: warn.append(f'a row without a headgear name: {tds[0][:60]!r}'); continue
        ings, bad = [], []
        for part in re.split(r'<br\s*/?>', tds[1]):
            m = re.match(r'^(.*?)\s+-\s+(\d[\d,]*)$', clean(part))
            if m: ing = {'item': m.group(1).strip(), 'qty': int(m.group(2).replace(',', ''))}; iid = img_id(part); ing.update(item_id=iid) if iid else None; ings.append(ing)
            elif clean(part): bad.append(f'{full}: could not read material {clean(part)!r}')
        m = re.match(r'^(.*?)\s*\(([^)]*)\)$', full)             # 'Crimson Rose (Scarlet Rose)': the second name is another name for it
        aliases = [m.group(1).strip(), m.group(2).strip()] if m else []
        row = {'name': full, 'aliases': aliases, 'npc': 'Dimonka', 'ingredients': ings, 'categories': ['Headgear Quest'], 'wiki': f'{SITE}/{page}/', 'page': page,
               'rewards': {'items': [{k: v for k, v in (('item_id', img_id(tds[0])), ('item', full), ('qty', 1)) if v is not None}]}}
        if office: row.update(location=f'{office.group(1)} {office.group(2)}/{office.group(3)}', notes="Dimonka is inside the Main Office; location is the office entrance")
        if not ings: warn.append(f'{full}: no materials read'); continue
        warn += bad
        rows.append(row)
    return rows, warn

def md_img_id(cell):
    """The item id in a markdown image ![x](img/5447.gif) of a table cell, else None."""
    m = re.search(r'!\[[^\]]*\]\([^)]*?/(\d+)(?:_\d+)?\.(?:gif|png)\)', cell)
    return int(m.group(1)) if m else None

def king_frog_hat(text, page='king-frog-hat', read=None):
    """(rows, warnings) from king-frog-hat.md: a prose page for one quest. The title names the quest, the first bold name before a /navi spot is the
    NPC, the table with Item and Quantity columns holds the materials, and 'reward you with **Item**' names the item given."""
    warn = []
    t = re.search(r'^#\s+(.+)$', text, re.M)
    if not t: return [], ['no title found']
    title = re.sub(r'^[^\w\[(]+', '', t.group(1)).strip()          # drops the emoji
    m = re.search(r'\*\*([^*\n]+)\*\*[^\n`]*?`/navi\s+(\S+)\s+(\d+)/(\d+)`', text)
    ings = []
    for _, head, trs in md_tables(text):
        if 'Item' not in head or 'Quantity' not in head: continue
        for tr in trs:
            name, qty = clean(tr.get('Item', '')), num(tr.get('Quantity', ''))
            if not name or qty is None: warn.append(f'{title}: could not read material row {tr}'); continue
            ing = {'item': name, 'qty': qty}; iid = md_img_id(tr.get('Item', ''))
            if iid: ing['item_id'] = iid
            ings.append(ing)
    if not ings: return [], warn + [f'{title}: no materials table found']
    row = {'name': title, 'aliases': [], 'ingredients': ings, 'categories': ['Headgear Quest'], 'wiki': f'{SITE}/{page}/', 'page': page}
    if title.endswith(' Quest'): row['aliases'].append(title[:-len(' Quest')])
    if m: row.update(npc=m.group(1).strip(), location=f'{m.group(2)} {m.group(3)}/{m.group(4)}')
    else: warn.append(f'{title}: no NPC and /navi spot found')
    r = re.search(r'reward you with\s+(?:the\s+)?(!\[[^\]]*\]\([^)]*\))?\s*\*\*([^*]+)\*\*', text)
    if r:
        row['aliases'].append(r.group(2).strip())
        row['rewards'] = {'items': [{k: v for k, v in (('item_id', md_img_id(r.group(1) or '')), ('item', r.group(2).strip()), ('qty', 1)) if v is not None}]}
    else: warn.append(f'{title}: no reward item found')
    return [row], warn

def expanded_class_weapons(text, page='expanded-class-weapons', read=None):
    """(rows, warnings) from expanded-class-weapons.md: one quest. Weapon tables under a class heading ('| Weapon | In-game command |', '@ii 32303')
    are what it gives (choose one); the bullets under 'Token Creation Requirements' are the cost (items and zeny); the first /navi spot after
    'NPC Location' is where the NPCs are (the page does not name them); the fragment drop is kept as a note."""
    warn = []
    t = re.search(r'^#\s+(.+)$', text, re.M)
    if not t: return [], ['no title found']
    title = re.sub(r'^[^\w\[(]+', '', t.group(1)).strip()
    weapons = []
    for heading, head, trs in md_tables(text):
        if 'Weapon' not in head or 'In-game command' not in head: continue
        for tr in trs:
            name, iid = clean(tr.get('Weapon', '')), num(tr.get('In-game command', ''))
            if not name or iid is None: warn.append(f'{heading}: could not read weapon row {tr}'); continue
            weapons.append({'item_id': iid, 'item': name, 'qty': 1, 'class': clean(heading)})
    sec = re.search(r'Token Creation Requirements(.*?)(?:\n#|\Z)', text, re.S)
    ings, zeny = [], None
    for line in (sec.group(1) if sec else '').splitlines():
        m = re.match(r'^\s*-\s+\*\*([\d,]+)\s*(?:[×x]\s*)?(.+?)\*\*', line)
        if not m: continue
        n, what = int(m.group(1).replace(',', '')), m.group(2).strip()
        if what.lower() == 'zeny': zeny = n
        else: ings.append({'item': what, 'qty': n})
    if not weapons: warn.append(f'{title}: no weapon tables found')
    if not ings: return [], warn + [f'{title}: no token requirements found']
    row = {'name': title, 'aliases': [], 'ingredients': ings, 'categories': ['Weapon Quest'], 'wiki': f'{SITE}/{page}/', 'page': page}
    if zeny is not None: row['zeny'] = zeny
    if weapons: row['rewards'] = {'items': weapons, 'choose_one': True}
    loc = re.search(r'NPC Location(.*?)`/navi\s+(\S+)\s+(\d+)/(\d+)`', text, re.S)
    if loc: row['location'] = f'{loc.group(2)} {loc.group(3)}/{loc.group(4)}'
    else: warn.append(f'{title}: no NPC /navi spot found')
    frag = re.search(r'Dropped by ([^\n]+?)\s*\n.*?Drop Rate:\*\*\s*([\d.]+%)', text, re.S)
    mobs = len(re.findall(r'^- .+\(@mi \d+\)', text, re.M))
    if frag: row['notes'] = f"{ings[0]['item']}: dropped by {frag.group(1).replace('**', '')} at {frag.group(2)}" + (f' ({mobs} monsters listed on the wiki page)' if mobs else '') + '. The NPCs are not named on the wiki page.'
    return [row], warn

PAGES = {'repeatable-quests': repeatable_quests, 'dimonka-headgear-quest': dimonka_headgear, 'king-frog-hat': king_frog_hat, 'expanded-class-weapons': expanded_class_weapons}

def ing_key(ings): return frozenset((norm(re.sub(r'\s*\[0\]$', '', i['item'])), i.get('qty')) for i in ings)   # the loot sheet writes 'Kitty Band [0]', the wiki 'Kitty Band'

def loose(s):
    """A name with slots '[1]' and brackets '(RWH)' dropped, for 'Alice Doll [1]' vs 'Alice Doll'."""
    return norm(re.sub(r'\[\d+\]|\([^)]*\)', '', s))

def set_field(rec, f, val, overwrite, rep, label=None, path=''):
    """Fill rec[f] if missing, merging dict fields key by key; report a different value instead of replacing it. True if rec changed."""
    label = label or rec['name']
    if f not in rec: rec[f] = val; return True
    if isinstance(val, dict) and isinstance(rec[f], dict):
        return any([set_field(rec[f], k, v, overwrite, rep, label, f'{path}{f}.') for k, v in val.items()])
    if rec[f] == val: return False
    if overwrite: rec[f] = val; return True
    rep['differs'].append(f"{label}: {path}{f} is {rec[f]!r}, wiki says {val!r}"); return False

def apply_rows(records, rows, overwrite=False):
    """Merge wiki rows into the record list (in place). Returns a report dict of lists."""
    rep = {k: [] for k in ('by_name', 'by_similar_name', 'by_ingredients', 'created', 'ambiguous', 'differs', 'ingredient_diffs', 'changed')}
    by_name = {norm(r['name']): r for r in records}; ids = {i['item']: i.get('item_id') for r in records for i in r['ingredients'] if i.get('item_id')}
    by_loose = {}
    for r in records: by_loose.setdefault(loose(r['name']), []).append(r)
    taken = {}                                                      # record id -> the wiki row that claimed it
    for row in rows:
        names = [row['name']] + row.get('aliases', []); rec, how = None, 'by_name'
        for n in names:
            if norm(n) in by_name: rec = by_name[norm(n)]; break
        if rec is None:
            tries = [loose(n) for n in names]; tries += [t[:-3] for t in tries if t.endswith('hat') and len(t) > 6]   # 'Glaris Doll Hat [1]' for the record 'Glaris Doll'
            hits = {id(r): r for t in tries for r in by_loose.get(t, [])}
            if len(hits) > 1: rep['ambiguous'].append(f"{row['name']}: similar names {', '.join(r['name'] for r in hits.values())}"); continue
            if hits: rec, how = next(iter(hits.values())), 'by_similar_name'
        if rec is None and row['ingredients']:
            hit = [r for r in records if r['ingredients'] and ing_key(r['ingredients']) == ing_key(row['ingredients'])]
            if len(hit) > 1: rep['ambiguous'].append(f"{row['name']}: ingredients match {', '.join(r['name'] for r in hit)}"); continue
            rec, how = (hit[0] if hit else None), 'by_ingredients'
        if rec is not None and rec['id'] in taken:
            rep['ambiguous'].append(f"{row['name']}: matches {rec['name']}, which {taken[rec['id']]} already matched"); continue
        if rec is None:
            rec = {'id': slug(row['name']), 'name': row['name'], 'categories': row['categories'], 'ingredients': [{k: v for k, v in (('item_id', i.get('item_id') or ids.get(i['item'])), ('item', i['item']), ('qty', i['qty'])) if v is not None} for i in row['ingredients']], 'is_quest': True, 'source': 'wiki'}
            records.append(rec); by_name[norm(rec['name'])] = rec; by_loose.setdefault(loose(rec['name']), []).append(rec); rep['created'].append(row['name']); rep['changed'].append(rec['id'])
        else:
            rep[how].append(f"{row['name']} -> {rec['name']}" if rec['name'] != row['name'] else row['name'])
            if row['ingredients'] and ing_key(rec['ingredients']) != ing_key(row['ingredients']):
                rep['ingredient_diffs'].append(f"{rec['name']}: wiki {sorted((i['qty'], i['item']) for i in row['ingredients'])}, record {sorted((i.get('qty') or 0, i['item']) for i in rec['ingredients'])}")
            if not rec.get('is_quest'): rec['is_quest'] = True; rep['changed'].append(rec['id'])
        taken[rec['id']] = row['name']
        if any([set_field(rec, f, row[f], overwrite, rep) for f in WIKI_FIELDS if f in row]) and rec['id'] not in rep['changed']: rep['changed'].append(rec['id'])
    return rep

def print_report(rep, warn, rows):
    print(f"{len(rows)} wiki quests read: {len(rep['by_name'])} matched by name, {len(rep['by_similar_name'])} by similar name, {len(rep['by_ingredients'])} by ingredients, {len(rep['created'])} new, {len(rep['ambiguous'])} ambiguous; {len(set(rep['changed']))} records changed")
    for title, key in (('matched by similar name (check these)', 'by_similar_name'), ('matched by ingredients (check these)', 'by_ingredients'), ('NEW records from the wiki', 'created'), ('AMBIGUOUS, not touched', 'ambiguous'), ('wiki and record disagree, kept the record (use --overwrite to take the wiki)', 'differs'), ('ingredients differ between wiki and loot sheet (not changed)', 'ingredient_diffs')):
        if rep[key]: print(f'\n{title}:'); [print('  ' + x) for x in rep[key]]
    if warn: print('\nwarnings:'); [print('  ' + w) for w in warn]

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--wiki', required=True, help='the wiki docs folder'); ap.add_argument('--data', default=f'{REPO}/data/uaro-quests.json')
    ap.add_argument('--page', action='append', choices=sorted(PAGES), help='page to import (default: all supported)')
    ap.add_argument('--overwrite', action='store_true', help="take the wiki's value where a record has a different one"); ap.add_argument('--dry-run', action='store_true', help='report only, write nothing')
    a = ap.parse_args(argv)
    if not os.path.isfile(a.data): die(f'{a.data} not found. Run import_loot_sheet.py first.')
    if not os.path.isdir(a.wiki): die(f'{a.wiki} is not a folder (give the wiki docs folder)')
    doc = json.loads(Path(a.data).read_text(encoding='utf-8')); rows, warn = [], []
    for page in a.page or sorted(PAGES):
        f = Path(a.wiki) / f'{page}.md'
        if not f.is_file():
            if a.page: die(f'{f} not found')
            warn.append(f'{f.name} not found in {a.wiki}, skipped'); continue
        r, w = PAGES[page](f.read_text(encoding='utf-8'), page, lambda n: (Path(a.wiki) / f'{n}.md').read_text(encoding='utf-8') if (Path(a.wiki) / f'{n}.md').is_file() else ''); rows += r; warn += w
    rep = apply_rows(doc['quests'], rows, a.overwrite); doc['quests'].sort(key=lambda r: r['name'].lower())
    print_report(rep, warn, rows)
    if not a.dry_run and rep['changed']:
        Path(a.data).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8'); print(f'\nwrote {a.data}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
