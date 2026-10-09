#!/usr/bin/env python3
"""Look up quests and the items they use, from index/quests.jsonl (build it with build_quests.py).
  quests.py <id | part of a title>     one quest: client text, quest_db targets, NPCs, items asked for and given
  quests.py --item <id | name>         quests that ask for the item (add --gives for quests that reward it)
  quests.py --mob <name | part>        quests with a kill target or item drop from that monster
  quests.py --stats                    what the index contains
Add --uaro to any lookup to hide quests marked as not on uaRO (rules live in notes/quest-uaro.csv; see build_quests.py).
Item facts come from NPC scripts and are heuristic (see build_quests.py): check the NPC and file shown before relying on one."""
import json, os, sys
from pathlib import Path
ROOT = os.environ.get('GAME_DATA', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IDX = f'{ROOT}/index/quests.jsonl'

def die(msg): sys.exit(f'error: {msg}')

def load():
    if not os.path.isfile(IDX): die(f'{IDX} not found. Run bin/build_quests.py first.')
    return [json.loads(l) for l in Path(IDX).read_text(encoding='utf-8').splitlines()]

def asked(q):
    """Items the quest asks for, one row per (item, qty): relation 'takes' (delitem) and 'checks' (countitem) merged."""
    out = {}
    for i in q['items']:
        if i['relation'] not in ('takes', 'checks'): continue
        e = out.setdefault((i['item'], i['item_name'], i['qty']), {'item': i['item'], 'name': i['item_name'], 'qty': i['qty'], 'rel': set(), 'npc': i['npc'], 'file': i['file']})
        e['rel'].add(i['relation'])
    return list(out.values())

def given(q):
    out = {}
    for i in q['items']:
        if i['relation'] == 'gives': out.setdefault((i['item'], i['qty']), {'item': i['item'], 'name': i['item_name'], 'qty': i['qty'], 'npc': i['npc']})
    return list(out.values())

def show(q):
    print(f"Quest {q['id']}: {q['title']}" + (f"   [not on uaRO: {q['uaro_note']}]" if q.get('uaro') == 'no' else ''))
    c = q.get('client')
    if c:
        for l in c['description']: print('   ', l)
        if c['summary']: print('    Summary:', c['summary'])
    for mode, d in q['db'].items():
        bits = []
        if d['time_limit']: bits.append(f"time limit {d['time_limit']}s")
        bits += [f"kill {t.get('count', '?')} {t.get('mob')}" + (f" in {t['location']}" if t.get('location') else '') for t in d['targets']]
        bits += [f"drop {x['count']} {x['item_name']} from {x['mob'] or 'any monster'}" + (f" ({x['rate'] / 100:g}%)" if x['rate'] else '') for x in d['drops']]
        print(f"  quest_db ({mode}): " + ('; '.join(bits) or 'no targets'))
    if q['npcs']: print('  NPCs: ' + '; '.join(f"{n['name']} ({n['map'] or 'global'}, {n['mode']})" for n in q['npcs'][:6]) + (f" +{len(q['npcs']) - 6} more" if len(q['npcs']) > 6 else ''))
    for a in asked(q): print(f"  asks for {a['qty'] if a['qty'] is not None else '?'} x {a['name']} ({a['item']})  [{'+'.join(sorted(a['rel']))}, {a['npc']}, {a['file']}]")
    for g in given(q): print(f"  gives {g['qty'] if g['qty'] is not None else '?'} x {g['name']} ({g['item']})  [{g['npc']}]")

def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if not a: die('usage: quests.py <id|title> | --item <id|name> [--gives] | --mob <name> | --stats')
    rows = load(); only = '--uaro' in a; a = [x for x in a if x != '--uaro']
    if only: rows = [r for r in rows if r.get('uaro') != 'no']
    if not a: die('give a quest id, title, --item, --mob or --stats')
    if a == ['--stats']:
        print(f"{len(rows)} quests: {sum(bool(r['client']) for r in rows)} with client text, {sum(bool(r['db']) for r in rows)} in quest_db, {sum(bool(r['npcs']) for r in rows)} in NPC scripts, {sum(bool(asked(r)) for r in rows)} asking for items, {sum(bool(given(r)) for r in rows)} giving items, {sum(r.get('uaro') == 'no' for r in rows)} marked not on uaRO"); return 0
    if a[0] == '--item':
        if len(a) < 2: die('--item needs an item id or name')
        key, gives = a[1].lower(), '--gives' in a
        pick = given if gives else asked
        hits = [(r, g) for r in rows for g in pick(r) if str(g['item']) == key or key in (g['name'] or '').lower()]
        print(f"{len(hits)} quest(s) {'give' if gives else 'ask for'} {a[1]}:")
        for r, g in hits[:60]: print(f"  {r['id']:>6}  {r['title'][:46]:46} {g['qty'] if g['qty'] is not None else '?'} x {g['name']}  [{g['npc']}]" + ('  (not on uaRO)' if r.get('uaro') == 'no' else ''))
        if len(hits) > 60: print(f'  ... {len(hits) - 60} more')
        return 0
    if a[0] == '--mob':
        if len(a) < 2: die('--mob needs a monster name')
        key = a[1].lower()
        hits = [r for r in rows if any(key in str(t.get('mob', '')).lower() for d in r['db'].values() for t in d['targets']) or any(key in str(x['mob']).lower() for d in r['db'].values() for x in d['drops'])]
        print(f'{len(hits)} quest(s) target {a[1]}:')
        for r in hits[:60]: print(f"  {r['id']:>6}  {r['title']}")
        return 0
    key = ' '.join(a).lower()
    hits = [r for r in rows if str(r['id']) == key] or [r for r in rows if key in r['title'].lower()]
    if not hits: die(f'no quest matches {key!r}')
    for r in hits[:5]: show(r); print()
    if len(hits) > 5: print(f'{len(hits) - 5} more match; give an id.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
