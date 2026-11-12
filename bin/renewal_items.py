#!/usr/bin/env python3
"""Official (rAthena renewal) drops for the renewal areas (dungeons, instances and fields) that uaRO added, with item data.
  renewal_items.py [--area NAME ...] [--out DIR]     build the files
  renewal_items.py --item <id|name|text>             look an item up (drops with 1x and uaRO rates, areas, effects, box contents)
  renewal_items.py --effects                         list every item with a chance-to-drop effect
Areas: the renewal areas on the uaRO wiki's Areas and Instances table (episodes 12-14.2) plus the Niflheim dungeon (nif_dun).
Mobs come from the rAthena renewal spawn scripts (maps) or instance scripts (monster/areamonster calls);
drops from re/mob_db.yml; item data from re/item_db_*.yml. Values are official iRO values, not uaRO's.
Find one item with `renewal_items.py --item <id|name>` (reads renewal-items.jsonl, which has every item in every area, including all of Endless Tower).', '', 'Each drop shows the official 1x rate and the uaRO rate (item drops x5 capped at 100%, MvP drops x3, cards x5, MvP/mini-boss cards x1).
Also lists box contents, combos, client descriptions, exchange NPC items, instance script rewards and quest rewards with a hunt target in the area.
Writes <out>/renewal-items.json (by area, complete), .jsonl (one line per item, all areas merged; what --item reads) and .md (summary for people) (default out: $GAME_DATA/notes/handoff).
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
    'Dimensional Gorge': ('npc/re/mobs/fields/morocc.txt', {'moc_fild21', 'moc_fild22'}, 'ep 12; moc_fild21, moc_fild22'),
    'Eclage Interior': ('npc/re/instances/EclageInterior.txt', None, 'ep 14.2; instance 1@ecl'),
    'Endless Tower': ('npc/instances/EndlessTower.txt', None, 'ep 12; instance 1@tower..6@tower'),
    'Sealed Shrine': ('npc/instances/SealedShrine.txt', None, 'ep 12; instance'),
    'Brasilis': ('npc/re/mobs/fields/brasilis.txt', None, 'ep 13.2; bra_fild01'),
    'Brasilis Dungeon': ('npc/re/mobs/dungeons/bra_dun.txt', None, 'ep 13.2; bra_dun01, bra_dun02'),
    'Manuk': ('npc/re/mobs/fields/manuk.txt', None, 'ep 13.2; man_fild01-03'),
    'Splendide': ('npc/re/mobs/fields/splendide.txt', None, 'ep 13.2; spl_fild01-03'),
    "Nidhogg's Dungeon": ('npc/re/mobs/dungeons/nyd_dun.txt', None, 'ep 13.2; nyd_dun01'),
    "Nidhoggur's Nest": ('npc/instances/NydhoggsNest.txt', None, 'ep 13.2; instance'),
    'El Dicastes Fields': ('npc/re/mobs/fields/dicastes.txt', None, 'ep 13.3; dic_fild01, dic_fild02'),
    'Biolabs 4': ('npc/re/mobs/dungeons/lhz_dun.txt', {'lhz_dun04'}, 'ep 14.1; lhz_dun04'),
    'Byalan Dungeon 6': ('npc/re/mobs/dungeons/iz_dun.txt', {'iz_dun05'}, 'ep 14.1; iz_dun05'),
    'Niflheim Dungeon': ('npc/re/mobs/dungeons/nif_dun.txt', None, 'nif_dun01, nif_dun02'),
}

# NPC scripts that sell or exchange items tied to an area (exchange shops, enchanters)
MERCHANTS = {
    'Horror Toy Factory': ['npc/re/merchants/HorrorToyFactory_merchants.txt'],
    'Old Glast Heim': ['npc/re/merchants/OldGlastHeim_merchants.txt'],
    'Biolabs 4': ['npc/re/merchants/bio4_reward.txt', 'npc/re/merchants/nightmare_biolab.txt'],
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


# Boxes the wiki and players ask about; always tracked with their full contents, whether or not a monster in the areas drops them
TRACKED_BOXES = ['Gift_Box', 'Old_Blue_Box', 'Old_Violet_Box', 'Accessory_Box']  # Accessory_Box is the Jewelry Box

def chest_items(script, iid, re_items):
    """Treasure chests that makeitem their prizes: [(item id, qty, chance %)]. `if (rand(1,N) > T)` before a makeitem gives (N-T)/N."""
    out = []; case = None
    lines = Path(f'{RA}/{script}').read_text(encoding='utf-8', errors='replace').splitlines()
    for i, line in enumerate(lines):
        cm = re.match(r'\s*case\s+(\d+)\s*:', line)
        if cm: case = int(cm.group(1))
        m = re.search(r'\bmakeitem\s+(\w+)\s*,\s*(\d+)', line)
        if not m: continue
        v = m.group(1); d = iid.get(int(v)) if v.isdigit() else re_items.get(v)
        if not d: continue
        chance = 100.0
        prev = lines[i - 1] if i else ''
        c = re.search(r'rand\(1,\s*(\d+)\)\s*>\s*(\d+)', prev) if 'if' in prev and 'makeitem' not in prev else None
        if c: chance = round((int(c.group(1)) - int(c.group(2))) / int(c.group(1)) * 100, 3)
        out.append((d['Id'], int(m.group(2)), chance, case))
    return out

def merchant_items(files, iid, pre_ids):
    """Item ids on setarray/getitem/shop lines of exchange NPC scripts (heuristic: includes currencies and requirements)."""
    out = {}
    for f in files:
        for line in Path(f'{RA}/{f}').read_text(encoding='utf-8', errors='replace').splitlines():
            code = line.split('//')[0]
            if not re.search(r'setarray|getitem|\bshop\b|sellitem|callshop|\.@\w*item', code): continue
            for n in re.findall(r'\b(\d{3,6})\b', code):
                d = iid.get(int(n))
                if d: out[d['Id']] = {'id': d['Id'], 'name': d.get('Name', n), 'renewal_only': d['Id'] not in pre_ids, 'file': f}
    return sorted(out.values(), key=lambda x: x['id'])

def combos(re_items):
    """aegis -> list of combos (partner aegis names, script) from item_combos.yml."""
    out = {}
    for blk in load(f'{RA}/db/re/item_combos.yml'):
        for c in blk.get('Combos', []):
            names = c.get('Combo', [])
            for n in names: out.setdefault(n, []).append({'with': [x for x in names if x != n], 'script': (blk.get('Script') or '').strip()})
    return out

def descriptions():
    p = Path(f'{ROOT}/index/iteminfo.jsonl')
    if not p.is_file(): return {}
    out = {}
    for l in p.read_text(encoding='utf-8').splitlines():
        r = json.loads(l); out[r['id']] = r.get('description') or []
    return out

def uaro_rate(rate, kind, is_card, boss, mvp=False):
    """(uaRO rate in db units, rule). Item drops x5 capped at 100%, MvP drops x3, cards x5, MvP/mini-boss cards x1.
    Normal (non-card) drops of an MvP monster are x3 too: the Scaraba Queen's drops on the wiki are 3x the official rates.
    Non-card drops of mini-bosses are x5 (confirmed by the maintainer)."""
    if kind == 'mvp': return min(rate * 3, 10000), 'MvP drop x3'
    if is_card and boss: return rate, 'boss card x1'
    if mvp and not is_card: return min(rate * 3, 10000), 'MvP monster drop x3'
    return min(rate * 5, 10000), 'card x5' if is_card else 'drop x5'

DROP_EFFECT = re.compile(r'bonus([23])\s+bAdd(MonsterId|Monster|Class)DropItem(Group)?\s*,([^;]*);', re.I)

def drop_effects(script, iid, re_items):
    """'Chance to drop X' bonuses in an item script. n is in 1/100 %: official pct = n/100; uaRO is x5, capped at 100%."""
    out = []
    for m in DROP_EFFECT.finditer(script or ''):
        args = [a.strip() for a in m.group(4).split(',')]
        try:
            if m.group(1) == '2': what, who, n = args[0], 'any monster', int(args[1])
            else: what, who, n = args[0], args[1], int(args[2])
        except (IndexError, ValueError): continue
        group = bool(m.group(3))
        if not group:
            d = iid.get(int(what)) if what.isdigit() else re_items.get(what)
            what = f"{d.get('Name', what)} ({d['Id']})" if d else what
        if m.group(2).lower() == 'monsterid': who = f'monster id {who}'
        elif m.group(2).lower() == 'class': who = f'class {who}'
        elif who != 'any monster': who = who.replace('RC_', '') + ' monsters'
        out.append({'drops': what, 'group': group, 'from': who, 'official_pct': n / 100, 'uaro_pct': min(n * 5, 10000) / 100})
    return out

def box_groups():
    out = {}
    for d in load(f'{RA}/db/re/item_group_db.yml'):
        out[d['Group'].lower()] = d
    return out

def box_contents(item, groups, re_items):
    m = re.search(r'get(?:rand)?groupitem\(IG_(\w+)', item.get('Script') or '', re.I)
    g = groups.get(m.group(1).lower()) if m else None
    if not g: return None
    rows = []
    for sg in g.get('SubGroups', []):
        lst = sg.get('List', [])
        total = sum(x.get('Rate', 0) for x in lst) or 1
        for x in lst:
            d = re_items.get(x['Item'])
            pct = 100.0 if sg.get('Algorithm') == 'All' else x.get('Rate', 0) / total * 100
            rows.append({'item': x['Item'], 'id': d['Id'] if d else None, 'name': d.get('Name', x['Item']) if d else x['Item'],
                         'amount': x.get('Amount', 1), 'pct': round(pct, 3), 'subgroup': sg.get('SubGroup'), 'algorithm': sg.get('Algorithm', 'SharedPool')})
    return rows

def script_rewards(script, iid, re_items):
    """Items given by getitem in an instance script: [(id, name, qty)]."""
    out = {}
    for m in re.finditer(r'\bgetitem\s+(\w+)\s*,\s*(\d+)', Path(f'{RA}/{script}').read_text(encoding='utf-8', errors='replace')):
        v = m.group(1)
        d = iid.get(int(v)) if v.isdigit() else re_items.get(v)
        if d: out[d['Id']] = (d['Id'], d.get('Name', v), int(m.group(2)))
    return sorted(out.values())

def quest_rewards(mob_aegis):
    """Quests (re db) with a hunt target in the area: [(quest id, title, [(item id, name, qty)])]."""
    out = []
    p = Path(f'{ROOT}/index/quests.jsonl')
    if not p.is_file(): return out
    for l in p.read_text(encoding='utf-8').splitlines():
        q = json.loads(l)
        if not any(t.get('mob') in mob_aegis for t in (q.get('db', {}).get('re', {}).get('targets') or [])): continue
        gives = {(i['item'], i['item_name'], i.get('qty')) for i in q.get('items', []) if i['relation'] == 'gives'}
        out.append({'quest': q['id'], 'title': q['title'], 'gives': sorted(gives, key=lambda g: g[0])})
    return out

def record_lines(r):
    """Text lines for one index record (what --item prints, and what compare_item.py and drops.py add)."""
    lines = [f"{r['id']} {r['name']} [{r['type']}, slots {r['slots']}{', renewal-only' if r['renewal_only'] else ''}]"]
    for ar in r['areas']:
        lines.append(f"  {ar['area']}: " + '; '.join(f"{d['name']} {d['rate_pct']:g}% -> {d['uaro_pct']:g}% ({d['rule']})" for d in ar['dropped_by']))
    for e in r['drop_effects']: lines.append(f"  effect: drops {e['drops']} from {e['from']} {e['official_pct']:g}% -> {e['uaro_pct']:g}%")
    for c in r.get('combos') or []: lines.append(f"  combo with {', '.join(c['with'])}: {' '.join(c['script'].split())}")
    if r.get('description'): lines.append('  description: ' + ' '.join(r['description']))
    if r['box']: lines.append('  box: ' + ', '.join(f"{c['name']} {c['pct']:g}%" for c in r['box'] if c.get('id')))
    return lines

def find_records(q, path=None):
    """Index records for an item id or name (exact id, or name containing q). [] when the index is missing or has no match."""
    path = path or Path(ROOT) / 'notes/handoff/renewal-items.jsonl'
    if not Path(path).is_file(): return []
    rows = [json.loads(l) for l in Path(path).read_text(encoding='utf-8').splitlines()]
    if q is None: return [r for r in rows if r['drop_effects']]
    ql = str(q).lower()
    return [r for r in rows if str(r['id']) == str(q) or ql == r['name'].lower()] or ([r for r in rows if ql in r['name'].lower()] if not str(q).isdigit() else [])

def rathena_commit():
    import subprocess
    try: return subprocess.run(['git', '-C', RA, 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError): return None

def stale_note(path=None):
    """A warning when the rAthena checkout is no longer the one the index was built from; '' when it matches or cannot be told."""
    meta = Path(path or Path(ROOT) / 'notes/handoff/renewal-items.meta')
    if not meta.is_file(): return ''
    built = dict(l.split(': ', 1) for l in meta.read_text(encoding='utf-8').splitlines() if ': ' in l)
    now = rathena_commit()
    if now and built.get('rathena_commit') and now != built['rathena_commit']:
        return f"warning: the renewal index was built from rAthena {built['rathena_commit'][:10]}, the checkout is now {now[:10]}: run bin/renewal_items.py to rebuild"
    return ''

def lookup(path, q):
    if not path.is_file(): sys.exit(f'error: {path} not found; run this script without --item first')
    hits = find_records(q, path)
    if not hits: sys.exit(f'no item matching {q!r} in the renewal data')
    if stale_note(): print(stale_note())
    for r in hits: print('\n'.join(record_lines(r)))

def build_index(result, combo_db=None, desc=None, re_items=None):
    """One record per item with every area it drops in."""
    idx = {}
    for area, res in result.items():
        for v in res['items'].values():
            if v.get('missing'): continue
            r = idx.setdefault(v['id'], {k: v[k] for k in ('id', 'name', 'type', 'slots', 'weight', 'buy', 'sell', 'attack', 'defense', 'location', 'jobs', 'level', 'script', 'renewal_only', 'box', 'drop_effects', 'aegis')} | {'areas': []})
            r['areas'].append({'area': area, 'dropped_by': v['dropped_by']})
            if combo_db is not None:
                r['combos'] = combo_db.get(v['aegis'], []); r['description'] = (desc or {}).get(v['id'], [])
    return sorted(idx.values(), key=lambda r: r['id'])

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--item'); ap.add_argument('--effects', action='store_true')
    ap.add_argument('--area', action='append', choices=list(AREAS)); ap.add_argument('--out', default=f'{ROOT}/notes/handoff')
    a = ap.parse_args()
    if a.item or a.effects: return lookup(Path(a.out) / 'renewal-items.jsonl', a.item)
    re_items, pre_items, re_mobs = items('re'), items('pre-re'), mobs('re')
    groups = box_groups(); combo_db = combos(re_items); desc = descriptions()
    aegis_to_id = {d['AegisName']: i for i, d in re_mobs.items()}
    iid = {d['Id']: d for d in re_items.values()}
    pre_ids = {d['Id'] for d in pre_items.values()}
    result = {}
    for area in a.area or AREAS:
        script, maps, note = AREAS[area]
        res = {'note': note, 'source': script, 'mobs': [], 'items': {}, 'rewards': [], 'quests': [], 'merchant_items': [], 'chests': []}
        aegis = set()
        for mid in mob_ids(script, maps, aegis_to_id):
            m = re_mobs.get(mid)
            if not m: res['mobs'].append({'id': mid, 'name': '?', 'drops': []}); continue
            aegis.add(m['AegisName']); boss = m.get('Class') == 'Boss' or bool(m.get('MvpExp')); mvp = bool(m.get('MvpExp') or m.get('MvpDrops'))
            drops = [(x['Item'], x['Rate'], 'drop') for x in m.get('Drops', [])] + [(x['Item'], x['Rate'], 'mvp') for x in m.get('MvpDrops', [])]
            res['mobs'].append({'id': mid, 'name': m.get('Name', m['AegisName']), 'drops': [{'item': i, 'rate': r, 'kind': k} for i, r, k in drops]})
            for i, r, k in drops:
                d = re_items.get(i)
                if not d: res['items'].setdefault(i, {'id': None, 'name': i, 'missing': True}); continue
                e = res['items'].setdefault(i, {'id': d['Id'], 'name': d.get('Name', i), 'type': d.get('Type', 'Etc'), 'slots': d.get('Slots', 0),
                    'weight': d.get('Weight', 0) / 10, 'buy': d.get('Buy'), 'sell': d.get('Sell'), 'attack': d.get('Attack'), 'defense': d.get('Defense'),
                    'location': d.get('Locations'), 'jobs': d.get('Jobs'), 'level': d.get('EquipLevelMin'), 'script': d.get('Script'),
                    'aegis': i, 'renewal_only': d['Id'] not in pre_ids, 'dropped_by': [], 'box': box_contents(d, groups, re_items), 'drop_effects': drop_effects(d.get('Script'), iid, re_items)})
                u, rule = uaro_rate(r, k, e['type'] == 'Card', boss, mvp)
                e['dropped_by'].append({'mob': mid, 'name': m.get('Name'), 'rate_pct': r / 100, 'uaro_pct': u / 100, 'rule': rule, 'kind': k})
        if script.startswith('npc/re/instances') or script.startswith('npc/instances'):
            res['rewards'] = [{'id': i, 'name': n, 'qty': q, 'renewal_only': i not in pre_ids} for i, n, q in script_rewards(script, iid, re_items)]
        res['quests'] = [] if len(res['items']) > 300 else [dict(q, gives=[{'id': i, 'name': n, 'qty': c, 'renewal_only': i not in pre_ids} for i, n, c in q['gives']]) for q in quest_rewards(aegis)]
        if script.startswith('npc/re/instances') or script.startswith('npc/instances'):
            res['chests'] = [{'id': i, 'name': iid[i].get('Name'), 'qty': q, 'chance_pct': c, 'renewal_only': i not in pre_ids, 'chest': ch} for i, q, c, ch in chest_items(script, iid, re_items)]
        res['merchant_items'] = merchant_items(MERCHANTS.get(area, []), iid, pre_ids)
        result[area] = res
    if not a.area:
        box_area = {'note': 'always tracked; contents come from item_group_db', 'source': 'db/re/item_group_db.yml', 'mobs': [], 'items': {}, 'rewards': [], 'quests': [], 'merchant_items': [], 'chests': []}
        for ae in TRACKED_BOXES:
            d = re_items.get(ae)
            if d: box_area['items'][ae] = {'id': d['Id'], 'name': d.get('Name', ae), 'type': d.get('Type', 'Etc'), 'slots': 0, 'weight': d.get('Weight', 0) / 10, 'buy': d.get('Buy'), 'sell': d.get('Sell'), 'attack': None, 'defense': None, 'location': None, 'jobs': None, 'level': None, 'script': d.get('Script'), 'aegis': ae, 'renewal_only': d['Id'] not in pre_ids, 'dropped_by': [], 'box': box_contents(d, groups, re_items), 'drop_effects': []}
        result['Tracked boxes'] = box_area
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / 'renewal-items.json').write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding='utf-8')
    pct = lambda x: f'{x:g}%'
    (out / 'renewal-items.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in build_index(result, combo_db, desc, re_items)) + '\n', encoding='utf-8')
    md = ['# Renewal drops (rAthena renewal, official iRO values)', '',
          'Each drop shows the official 1x base rate, then the uaRO rate after the server multiplier: item drops x5 (cap 100%), MvP drops x3, normal cards x5, MvP/mini-boss cards x1.',
          'Non-card drops of an MvP monster are x3 (confirmed on the Queen Scaraba table on the wiki, 3x the official rates). Non-card drops of mini-bosses are x5 (confirmed). Where the wiki shows a different rate for a specific item (for example the Queen's Wing at 35%), uaRO changed that drop; these figures stay as computed unless the wiki or a patch note shows otherwise. Chance-to-drop effects on cards and equipment (bAdd*DropItem) are shown the same way, x5. Box contents, instance rewards and quest rewards are not multiplied.', '']
    for area, res in result.items():
        its = res['items']; cards = [v for v in its.values() if v.get('type') == 'Card']
        md += [f'## {area} ({res["note"]})', f'Source: `{res["source"]}`. {len(res["mobs"])} monsters, {len(its)} items, {len(cards)} cards, {sum(1 for v in its.values() if v.get("renewal_only"))} items absent from the pre-renewal item db.', '']
        big = len(its) > 300  # Endless Tower reuses most of the old monsters: list only the renewal-only items, the json has all
        if big: md += ['Large list: only items absent from the pre-renewal item db are shown here. Use `--item` or the jsonl for the rest.', '']
        md += ['| ID | Item | Type | Slots | Renewal-only | Dropped by: 1x official -> uaRO |', '|---|---|---|---|---|---|']
        for v in sorted(its.values(), key=lambda v: (v.get('type') != 'Card', v.get('id') or 0)):
            if big and not v.get('renewal_only'): continue
            if v.get('missing'): md.append(f'| ? | {v["name"]} | not in item db | | | |'); continue
            md.append(f'| {v["id"]} | {v["name"]} | {v["type"]} | {v["slots"]} | {"yes" if v["renewal_only"] else ""} | ' + '; '.join(f'{d["name"]} {pct(d["rate_pct"])} -> {pct(d["uaro_pct"])}' + (' (MVP)' if d['kind'] == 'mvp' else '') for d in v['dropped_by']) + ' |')
        fx = [v for v in its.values() if v.get('drop_effects') and (not big or v.get('renewal_only'))]
        if fx:
            md += ['', '### Items that add a chance to drop something (official 1x -> uaRO x5, cap 100%)', '']
            for v in fx:
                md.append(f'- **{v["name"]}** ({v["id"]}): ' + '; '.join(f'{e["drops"]}{" (item group)" if e["group"] else ""} from {e["from"]} {pct(e["official_pct"])} -> {pct(e["uaro_pct"])}' for e in v['drop_effects']))
        boxes = [v for v in its.values() if v.get('box') and (not big or v.get('renewal_only') or area == 'Tracked boxes')]
        if boxes:
            md += ['', '### Box contents (item group; percent is the chance within its sub-group)', '']
            for v in boxes:
                md.append(f'- **{v["name"]}** ({v["id"]}): ' + ', '.join(f'{c["name"]}{" x" + str(c["amount"]) if c["amount"] != 1 else ""} {pct(c["pct"])}' for c in v['box'] if c.get('id')))
        if res.get('chests'):
            md += ['', '### Treasure chest prizes (makeitem in the instance script; chance per chest)', '']
            md += [f'- {c["name"]} ({c["id"]}) x{c["qty"]}: {pct(c["chance_pct"])}{" (chest " + str(c["chest"]) + ")" if c["chest"] else ""}{" (renewal-only)" if c["renewal_only"] else ""}' for c in res['chests']]
        if res['rewards']:
            md += ['', '### Instance script rewards (getitem)', '']
            md += [f'- {r["name"]} ({r["id"]}) x{r["qty"]}{" (renewal-only)" if r["renewal_only"] else ""}' for r in res['rewards']]
        mi = [m for m in res['merchant_items'] if m['renewal_only']]
        if mi:
            md += ['', '### Renewal-only items named in the area exchange/shop NPC scripts (heuristic; includes currencies and requirements)', '']
            md += ['- ' + ', '.join(f'{m["name"]} ({m["id"]})' for m in mi)]
        if res['quests']:
            md += ['', '### Quests with a hunt target in this area (rewards from NPC scripts, heuristic)', '']
            md += [f'- Quest {q["quest"]} {q["title"]}: ' + (', '.join(f'{g["name"]} ({g["id"]}) x{g["qty"] or 1}' for g in q['gives']) or 'no item reward found') for q in res['quests']]
        md.append('')
    (out / 'renewal-items.md').write_text('\n'.join(md), encoding='utf-8')
    from datetime import date
    (out / 'renewal-items.meta').write_text(f'rathena_commit: {rathena_commit()}\nbuilt: {date.today()}\n', encoding='utf-8')
    for area, res in result.items(): print(f'{area}: {len(res["mobs"])} mobs, {len(res["items"])} items')
    print(f'wrote {out}/renewal-items.{{json,md}}')

if __name__ == '__main__': main()
