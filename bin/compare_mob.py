#!/usr/bin/env python3
"""Compare one monster across Hercules pre-re/re and rAthena pre-re/re, plus project docs and patch notes.
  compare_mob.py 1002 | compare_mob.py "Poring"   (run from a repo with a docs/ folder, or set DOCS_DIR)
A name that matches several IDs prints one block per ID (up to 6): pick the one you mean.
Missing Def and Mdef count as 0. Other missing fields (including stats a database leaves at its default) are shown as - and not compared.
Atk is min-max in pre-re but ATK/MATK in renewal, so only compare Atk within the same mode.
"""
import os, re, sys
from pathlib import Path
import yaml
from common import *
FIELDS = ['Name', 'Level', 'Hp', 'Exp', 'JExp', 'Atk', 'Def', 'Mdef', 'Str', 'Agi', 'Vit', 'Int', 'Dex', 'Luk', 'Size', 'Race', 'Element', 'Speed']

def herc(mode):
    out = {}
    for b in herc_blocks(f'{ROOT}/hercules/db/{mode}/mob_db.conf'):
        d = herc_parse(b)
        if 'Id' not in d: continue
        st = d.get('Stats', {})
        atk = re.findall(r'\d+', str(d.get('Attack', '')))
        el = re.findall(r'"?(\w+)"?', str(d.get('Element', '')).replace('Ele_', ''))
        out[d['Id']] = {'Name': d.get('Name'), 'Level': d.get('Lv'), 'Hp': d.get('Hp'), 'Exp': d.get('Exp'), 'JExp': d.get('JExp'),
            'Atk': ('-' if mode == 'pre-re' else '/').join(atk) if atk else None, 'Def': d.get('Def', 0), 'Mdef': d.get('Mdef', 0), **{k: st.get(k) for k in ('Str', 'Agi', 'Vit', 'Int', 'Dex', 'Luk')},
            'Size': strip_prefix(d.get('Size')), 'Race': strip_prefix(d.get('Race')), 'Element': ' '.join(el), 'Speed': d.get('MoveSpeed')}
    return out

def rath(mode):
    out = {}
    for d in yaml.load(Path(f'{ROOT}/rathena/db/{mode}/mob_db.yml').read_text(encoding='utf-8'), Loader=YAML_LOADER).get('Body', []):
        a, a2 = d.get('Attack'), d.get('Attack2')
        out[d['Id']] = {'Name': d.get('Name'), 'Level': d.get('Level'), 'Hp': d.get('Hp'), 'Exp': d.get('BaseExp'), 'JExp': d.get('JobExp'),
            'Atk': f"{a}{'-' if mode == 'pre-re' else '/'}{a2}" if a is not None and a2 is not None else (str(a) if a is not None else None), 'Def': d.get('Defense', 0), 'Mdef': d.get('MagicDefense', 0),
            **{k: d.get(k) for k in ('Str', 'Agi', 'Vit', 'Int', 'Dex', 'Luk')}, 'Size': d.get('Size'), 'Race': d.get('Race'),
            'Element': f"{d.get('Element', '')} {d.get('ElementLevel', '')}".strip(), 'Speed': d.get('WalkSpeed')}
    return out

if __name__ == '__main__':
    key = sys.argv[1]
    data = {'herc pre-re': herc('pre-re'), 'herc re': herc('re'), 'rath pre-re': rath('pre-re'), 'rath re': rath('re')}
    ids = sorted({i for d in data.values() for i, v in d.items() if str(i) == key or (v['Name'] or '').lower() == key.lower()})
    if not ids:
        names = {(i, v['Name']) for d in data.values() for i, v in d.items() if v.get('Name')}
        print_suggestions(key, sorted(names, key=str)); sys.exit(f'No monster matches {key!r} in any source.')
    for i in ids[:6]:
        print(f'\n===== Monster {i} =====')
        print_table({k: d.get(i) for k, d in data.items()}, FIELDS, 9)
        print('  Note: Atk is min-max in pre-re and ATK/MATK in renewal; the Atk disagreement across modes is expected.')
    if len(ids) > 6: print(f'\n{len(ids) - 6} more IDs match this name; use an ID.')
    names = {v[i]['Name'] for v in data.values() for i in ids if i in v and v[i]['Name']}
    doc_hits(names, re.compile(r'[`(](?:%s)[`)]' % '|'.join(map(str, ids))))
