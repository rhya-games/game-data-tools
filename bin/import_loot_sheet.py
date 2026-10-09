#!/usr/bin/env python3
"""Import what the loot sheet says items are used for into data/uaro-quests.json, the uaRO quest data this repo owns.
  import_loot_sheet.py --loot ~/Projects/uaro-loot-sheet/src/data/loot.json [--out data/uaro-quests.json]
Each loot item has "uses": {for, qty, note}. Inverting them gives one record per target (a hat, weapon, pet evolution, recipe or quest) with its
ingredients and quantities. A record's categories are those of its ingredient items (Official Hat Quest, Server Hat Quest, Other Quest,
Dungeon Quest, Cooking, ...). Records with a quest category are quests; the rest are recipes and skills kept for reference.
The file is curated here: a re-import refreshes ingredients, categories and use notes but keeps every other field you added (npc, location,
wiki, notes, ...), and removes nothing by hand. Ids are 'uaro-<slug of the name>'."""
import argparse, json, os, re, sys
from pathlib import Path
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEST_CATEGORIES = ('Official Hat Quest', 'Server Hat Quest', 'Other Quest', 'Dungeon Quest')
REFRESHED = ('ingredients', 'categories', 'is_quest')

def die(msg): sys.exit(f'error: {msg}')

def slug(name): return 'uaro-' + re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

def invert(loot):
    """{target name: record} from the loot sheet's items."""
    out = {}
    for item in loot:
        for u in item.get('uses', []):
            r = out.setdefault(u['for'], {'id': slug(u['for']), 'name': u['for'], 'categories': set(), 'ingredients': []})
            ing = {'item_id': item.get('itemId'), 'item': item['name'], 'qty': u.get('qty')}
            if u.get('note'): ing['note'] = u['note']
            if ing not in r['ingredients']: r['ingredients'].append(ing)
            r['categories'] |= {c for c in item.get('categories', []) if c not in ('Not Reviewed', 'No Use', 'uaRO')}
    for r in out.values():
        r['categories'] = sorted(r['categories']); r['is_quest'] = any(c in QUEST_CATEGORIES for c in r['categories'])
        r['ingredients'].sort(key=lambda i: (i['item'].lower(), i.get('qty') or 0))
    return out

def merge(existing, fresh):
    """Update records from fresh, keep hand-added fields and records that only exist in the file."""
    by_id = {r['id']: r for r in existing}
    for name in sorted(fresh, key=str.lower):
        new = fresh[name]
        old = by_id.get(new['id'])
        if old is None: by_id[new['id']] = new
        else: old.update({k: new[k] for k in REFRESHED})
    return sorted(by_id.values(), key=lambda r: r['name'].lower())

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--loot', required=True); ap.add_argument('--out', default=f'{REPO}/data/uaro-quests.json')
    a = ap.parse_args(argv)
    if not os.path.isfile(a.loot): die(f'{a.loot} not found')
    try: loot = json.loads(Path(a.loot).read_text(encoding='utf-8'))
    except ValueError as e: die(f'{a.loot} is not valid JSON ({e})')
    if not isinstance(loot, list) or not loot or 'uses' not in loot[0] and not any('uses' in x for x in loot): die(f'{a.loot} does not look like the loot sheet (a list of items with "uses")')
    fresh = invert(loot)
    old = []
    if os.path.isfile(a.out): old = json.loads(Path(a.out).read_text(encoding='utf-8')).get('quests', [])
    records = merge(old, fresh)
    doc = {'about': 'uaRO quests, hats, weapons, pet evolutions and recipes with the items each one needs. Imported from the loot sheet by bin/import_loot_sheet.py; curated here (add npc, location, wiki and notes fields by hand and a re-import keeps them).', 'quests': records}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True); Path(a.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'{len(records)} records ({sum(r["is_quest"] for r in records)} quests) from {sum(len(r["ingredients"]) for r in records)} ingredient rows -> {a.out}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
