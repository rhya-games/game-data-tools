#!/usr/bin/env python3
"""Official (rAthena renewal) drops for renewal dungeons that uaRO added, with item data.
  renewal_dungeon_items.py [--area NAME ...] [--out DIR]
Areas: Horror Toy Factory, Old Glast Heim, Scaraba Hole, Niflheim Dungeon (nif_dun).
Mobs come from the rAthena renewal spawn scripts (maps) or instance scripts (monster/areamonster calls);
drops from re/mob_db.yml; item data from re/item_db_*.yml. Values are official iRO values, not uaRO's.
Writes <out>/renewal-dungeon-items.json and .md (default out: $GAME_DATA/notes/handoff).
"""
import argparse, glob, json, re, sys
from pathlib import Path
import yaml
from common import ROOT, YAML_LOADER

RA = f'{ROOT}/rathena'
# area -> (spawn script, map names to keep or None, note)
AREAS = {
    'Horror Toy Factory': ('npc/re/instances/HorrorToyFactory.txt', None, 'instance 1@xm_d'),
    'Old Glast Heim': ('npc/re/instances/OldGlastHeim.txt', None, 'instance 1@gl_k / 2@gl_k'),
    'Scaraba Hole': ('npc/re/mobs/dungeons/dic_dun.txt', {'dic_dun01', 'dic_dun02'}, 'dic_dun01, dic_dun02'),
    'Scaraba Hole (Nightmare)': ('npc/re/mobs/dungeons/dic_dun.txt', {'dic_dun03'}, 'dic_dun03; not on the wiki page'),
    'Niflheim Dungeon': ('npc/re/mobs/dungeons/nif_dun.txt', None, 'nif_dun01, nif_dun02'),
}

def load(path):
    return yaml.load(Path(path).read_text(encoding='utf-8'), Loader=YAML_LOADER).get('Body', [])

def items(mode):
    out = {}
    for f in glob.glob(f'{RA}/db/{mode}/item_db_*.yml'):
        for d in load(f): out[d['AegisName']] = d
    return out

def mobs(mode):
    return {d['Id']: d for d in load(f'{RA}/db/{mode}/mob_db.yml')}

def mob_ids(script, maps, aegis_to_id):
    """Mob ids in a spawn script: 'map,x,y<TAB>monster<TAB>name<TAB>id,count' lines, and monster()/areamonster() calls."""
    ids = {}
    for line in Path(f'{RA}/{script}').read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.split('//')[0]
        m = re.match(r'^(\w+)[^\t]*\t(?:boss_)?monster\t[^\t]*\t(\w+)', line)
        if m and (maps is None or m.group(1) in maps):
            ids[aegis_to_id.get(m.group(2)) or int(m.group(2)) if m.group(2).isdigit() or m.group(2) in aegis_to_id else None] = 1
            continue
        for c in re.finditer(r'(?:area)?monster\s+[^;]*?"[^"]*"\s*,\s*(\w+)\s*,', line):
            v = c.group(1)
            ids[int(v) if v.isdigit() else aegis_to_id.get(v)] = 1
    ids.pop(None, None)
    return sorted(ids)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--area', action='append', choices=list(AREAS)); ap.add_argument('--out', default=f'{ROOT}/notes/handoff')
    a = ap.parse_args()
    re_items, pre_items, re_mobs = items('re'), items('pre-re'), mobs('re')
    aegis_to_id = {d['AegisName']: i for i, d in re_mobs.items()}
    iid = {d['Id']: d for d in re_items.values()}
    pre_ids = {d['Id'] for d in pre_items.values()}
    result = {}
    for area in a.area or AREAS:
        script, maps, note = AREAS[area]
        res = {'note': note, 'source': script, 'mobs': [], 'items': {}}
        for mid in mob_ids(script, maps, aegis_to_id):
            m = re_mobs.get(mid)
            if not m: res['mobs'].append({'id': mid, 'name': '?', 'drops': []}); continue
            drops = [(x['Item'], x['Rate'], 'drop') for x in m.get('Drops', [])] + [(x['Item'], x['Rate'], 'mvp') for x in m.get('MvpDrops', [])]
            res['mobs'].append({'id': mid, 'name': m.get('Name', m['AegisName']), 'drops': [{'item': i, 'rate': r, 'kind': k} for i, r, k in drops]})
            for i, r, k in drops:
                d = re_items.get(i)
                if not d: res['items'].setdefault(i, {'id': None, 'name': i, 'missing': True}); continue
                e = res['items'].setdefault(i, {'id': d['Id'], 'name': d.get('Name', i), 'type': d.get('Type', 'Etc'), 'slots': d.get('Slots', 0),
                    'weight': d.get('Weight', 0) / 10, 'buy': d.get('Buy'), 'sell': d.get('Sell'), 'attack': d.get('Attack'), 'defense': d.get('Defense'),
                    'location': d.get('Locations'), 'jobs': d.get('Jobs'), 'level': d.get('EquipLevelMin'), 'script': d.get('Script'),
                    'renewal_only': d['Id'] not in pre_ids, 'dropped_by': []})
                e['dropped_by'].append({'mob': mid, 'name': m.get('Name'), 'rate_pct': r / 100, 'kind': k})
        result[area] = res
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / 'renewal-dungeon-items.json').write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding='utf-8')
    md = ['# Renewal dungeon drops (rAthena renewal, official iRO values)', '',
          'Base drop rates; uaRO multiplies item drops x5 (cap 100%), MvP drops x3, cards x5 (MvP/mini-boss cards x1).', '']
    for area, res in result.items():
        its = res['items']; cards = [v for v in its.values() if v.get('type') == 'Card']
        md += [f'## {area} ({res["note"]})', f'Source: `{res["source"]}`. {len(res["mobs"])} monsters, {len(its)} items, {len(cards)} cards, {sum(1 for v in its.values() if v.get("renewal_only"))} items absent from the pre-renewal item db.', '',
               '| ID | Item | Type | Slots | Renewal-only | Dropped by (base %) |', '|---|---|---|---|---|---|']
        for v in sorted(its.values(), key=lambda v: (v.get('type') != 'Card', v.get('id') or 0)):
            if v.get('missing'): md.append(f'| ? | {v["name"]} | not in item db | | | |'); continue
            md.append(f'| {v["id"]} | {v["name"]} | {v["type"]} | {v["slots"]} | {"yes" if v["renewal_only"] else ""} | ' + '; '.join(f'{d["name"]} {d["rate_pct"]:g}%' + (' (MVP)' if d['kind'] == 'mvp' else '') for d in v['dropped_by']) + ' |')
        md.append('')
    (out / 'renewal-dungeon-items.md').write_text('\n'.join(md), encoding='utf-8')
    for area, res in result.items(): print(f'{area}: {len(res["mobs"])} mobs, {len(res["items"])} items')
    print(f'wrote {out}/renewal-dungeon-items.{{json,md}}')

if __name__ == '__main__': main()
