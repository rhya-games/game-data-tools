#!/usr/bin/env python3
"""Drop lookup from Hercules and rAthena mob databases (official emulator values, never a server's custom changes).
  drops.py <item id|name>        which monsters drop the item, per source
  drops.py --mob <id|name>       a monster's drop table
Sources: Hercules pre-re/re mob_db.conf, rAthena pre-re/re mob_db.yml. Rates are shown as percent (db value / 100).
Drops are keyed by AegisName in the databases; item names are resolved through each project's item_db.
"""
import glob, os, re, sys
from pathlib import Path
import yaml
from common import ROOT, YAML_LOADER
H, R = f'{ROOT}/hercules/db', f'{ROOT}/rathena/db'

def blocks(path):
    t = Path(path).read_text(encoding='utf-8', errors='replace')
    return [m.group(1) for m in re.finditer(r'\n\{\n(.*?)\n\}', t, re.S)]

def herc_items(mode):
    """aegis -> (id, name)"""
    out = {}
    for b in blocks(f'{H}/{mode}/item_db.conf'):
        i = re.search(r'^\tId: (\d+)', b, re.M); a = re.search(r'^\tAegisName: "(.*?)"', b, re.M); n = re.search(r'^\tName: "(.*?)"', b, re.M)
        if i and a: out[a.group(1)] = (int(i.group(1)), n.group(1) if n else a.group(1))
    return out

def rath_items(mode):
    out = {}
    for f in glob.glob(f'{R}/{mode}/item_db_*.yml'):
        for d in yaml.load(Path(f).read_text(encoding='utf-8'), Loader=YAML_LOADER).get('Body', []):
            out[d['AegisName']] = (d['Id'], d.get('Name', d['AegisName']))
    return out

def herc_mobs(mode):
    """list of dicts: id, name, drops [(aegis, rate)], mvp [(aegis, rate)]"""
    out = []
    for b in blocks(f'{H}/{mode}/mob_db.conf'):
        i = re.search(r'^\tId: (\d+)', b, re.M); n = re.search(r'^\tName: "(.*?)"', b, re.M)
        if not i: continue
        def tbl(key):
            m = re.search(rf'^\t{key}: \{{\n(.*?)^\t\}}', b, re.S | re.M)
            return [(x, int(y)) for x, y in re.findall(r'^\t\t(\w+): (\d+)', m.group(1), re.M)] if m else []
        out.append({'id': int(i.group(1)), 'name': n.group(1) if n else '', 'drops': tbl('Drops'), 'mvp': tbl('MvpDrops')})
    return out

def rath_mobs(mode):
    out = []
    for d in yaml.load(Path(f'{R}/{mode}/mob_db.yml').read_text(encoding='utf-8'), Loader=YAML_LOADER).get('Body', []):
        out.append({'id': d['Id'], 'name': d.get('Name', ''), 'drops': [(x['Item'], x['Rate']) for x in d.get('Drops', [])],
                    'mvp': [(x['Item'], x['Rate']) for x in d.get('MvpDrops', [])]})
    return out

SOURCES = [('herc pre-re', herc_items, herc_mobs, 'pre-re'), ('herc re', herc_items, herc_mobs, 're'),
           ('rath pre-re', rath_items, rath_mobs, 'pre-re'), ('rath re', rath_items, rath_mobs, 're')]
pct = lambda r: f'{r / 100:g}%'

def by_item(key):
    for label, items_fn, mobs_fn, mode in SOURCES:
        items = items_fn(mode)
        hit = [a for a, (i, n) in items.items() if str(i) == key or n.lower() == key.lower() or a.lower() == key.lower()]
        print(f'\n== {label}' + (f' (item {items[hit[0]][0]} {items[hit[0]][1]}, aegis {hit[0]})' if hit else ': item not found'))
        for a in hit:
            rows = [(m['id'], m['name'], r, 'MVP' if kind else '') for m in mobs_fn(mode) for kind, lst in ((0, m['drops']), (1, m['mvp'])) for x, r in lst if x == a]
            for i, n, r, tag in sorted(rows, key=lambda x: -x[2]): print(f'   {i:>5} {n:28} {pct(r):>8} {tag}')
            if not rows: print('   no monster drops it')

def by_mob(key):
    for label, items_fn, mobs_fn, mode in SOURCES:
        items = items_fn(mode)
        ms = [m for m in mobs_fn(mode) if str(m['id']) == key or m['name'].lower() == key.lower()]
        print(f'\n== {label}' + ('' if ms else ': monster not found'))
        for m in ms:
            print(f"   {m['id']} {m['name']}")
            for tag, lst in (('', m['drops']), ('MVP ', m['mvp'])):
                for a, r in lst: print(f"     {tag}{items.get(a, (0, a))[1]:30} ({items.get(a, (0,))[0]}) {pct(r)}")

if __name__ == '__main__':
    a = sys.argv[1:]
    by_mob(a[1]) if a[:1] == ['--mob'] else by_item(a[0])
