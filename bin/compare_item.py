#!/usr/bin/env python3
"""Compare one item across every source and flag disagreements.
  compare_item.py 1201 | compare_item.py "Knife"      (run from a repo with a docs/ folder, or set DOCS_DIR)
Sources: Hercules pre-re/re, rAthena pre-re/re, saved db.irowiki.org page, client iteminfo (index/iteminfo.jsonl; stats read from its description text), project docs + patch notes.
Emulator weights are shown divided by 10 (in-game units). Missing Sell = Buy // 2.
"""
import glob, os, re, sys
from pathlib import Path
import yaml
import common
from common import ROOT
FIELDS = ['Name', 'Type', 'Buy', 'Sell', 'Weight', 'Atk', 'Def', 'Slots', 'Level']

def herc_blocks(path):
    t = Path(path).read_text(encoding='utf-8', errors='replace')
    for m in re.finditer(r'\n\{\n(.*?)\n\}', t, re.S):
        yield m.group(1)

def herc_get(b, k):
    m = re.search(rf'^\t{k}: (.+)$', b, re.M)
    return m.group(1).strip().strip('"') if m else None

def from_herc(path, key):
    for b in herc_blocks(path):
        if (key.isdigit() and herc_get(b, 'Id') == key) or (not key.isdigit() and (herc_get(b, 'Name') or '').lower() == key.lower()):
            return {'Name': herc_get(b, 'Name'), 'Type': (herc_get(b, 'Type') or '').replace('IT_', ''), 'Buy': herc_get(b, 'Buy'),
                    'Sell': herc_get(b, 'Sell'), 'Weight': herc_get(b, 'Weight'), 'Atk': herc_get(b, 'Atk'), 'Def': herc_get(b, 'Def'),
                    'Slots': herc_get(b, 'Slots'), 'Level': herc_get(b, 'Level') or herc_get(b, 'EquipLv'), '_id': herc_get(b, 'Id')}

def from_rath(dirpath, key):
    for f in sorted(glob.glob(f'{dirpath}/item_db_*.yml')):
        t = Path(f).read_text(encoding='utf-8')
        for m in re.finditer(r'^  - Id: \d+\n.*?(?=^  - Id: |\Z)', t, re.S | re.M):
            blk = m.group(0)
            head = re.match(r'  - Id: (\d+)', blk).group(1)
            nm = re.search(r'^    Name: (.+)$', blk, re.M)
            nm = nm.group(1).strip().strip('"\'') if nm else ''
            if (key.isdigit() and head == key) or (not key.isdigit() and nm.lower() == key.lower()):
                d = yaml.safe_load(blk)[0]
                return {'Name': d.get('Name'), 'Type': d.get('Type'), 'Buy': d.get('Buy'), 'Sell': d.get('Sell'), 'Weight': d.get('Weight'),
                        'Atk': d.get('Attack'), 'Def': d.get('Defense'), 'Slots': d.get('Slots'), 'Level': (d.get('EquipLevelMin')), '_id': str(d['Id'])}

def norm(src, emulator=True):
    if not src: return None
    r = {k: (None if v is None else str(v)) for k, v in src.items()}
    if emulator and r.get('Weight') and r['Weight'].isdigit(): r['Weight'] = str(int(r['Weight']) / 10).rstrip('0').rstrip('.')
    if emulator and r.get('Sell') is None and r.get('Buy') and r['Buy'].isdigit(): r['Sell'] = str(int(r['Buy']) // 2)
    return r

def from_irowiki(item_id):
    sys.path.insert(0, f'{ROOT}/bin')
    import parse_irowiki_item as p
    try: d = p.load(item_id)
    except FileNotFoundError: return None
    f = d['fields']
    z = lambda s: (re.match(r'\d+', s.split('(')[0].replace(',', '').strip()) or [None])[0] if s else None
    return {'Name': d['name'], 'Type': f.get('Type'), 'Buy': z(f.get('Buying Price')), 'Sell': z(f.get('Selling Price')),
            'Weight': f.get('Weight'), 'Atk': f.get('Attack'), 'Def': f.get('Defense'), 'Slots': None, 'Level': f.get('Required Level')}, d['description']

def from_client(item_id):
    """Row from the client iteminfo index (parse_iteminfo.py --index). Stats come from the description text."""
    import json
    path = f'{ROOT}/index/iteminfo.jsonl'
    if not item_id or not os.path.exists(path): return None
    for l in Path(path).read_text(encoding='utf-8').splitlines():
        r = json.loads(l)
        if str(r['id']) == str(item_id):
            txt = '\n'.join(r['description'])
            g = lambda k: (re.search(rf'^{k}:\s*(\d+)', txt, re.M | re.I) or [None, None])[1]
            return {'Name': r['name'], 'Weight': g('Weight'), 'Atk': g('Attack'), 'Def': g('Defense'), 'Slots': str(r['slots']) if r['slots'] else None,
                    'Level': g('Required Level')}, r['description']

def doc_hits(item_id, name):
    base = re.sub(r'\s*\[\d\]$', '', name or '')
    idpat = re.compile(rf'(?<!\d){item_id}(?!\d)')
    namepat = re.compile(rf'(?<![A-Za-z]){re.escape(base)}(?![A-Za-z])') if base else None
    def hit(l):
        if idpat.search(l): return True
        for m in (namepat.finditer(l) if namepat else []):
            prev = re.search(r'([A-Za-z\']+) $', l[:m.start()])
            nxt = re.match(r" ([A-Za-z']+)", l[m.end():])
            if not (prev and prev.group(1)[0].isupper()) and not (nxt and nxt.group(1)[0].isupper()): return True  # skip "Venom Knife", "Knife Goblin"
        return False
    out = []
    DOCS = common.DOCS
    for f in sorted(glob.glob(f'{DOCS}/**/*.md', recursive=True)):
        base = os.path.relpath(f, DOCS)
        if base.startswith(('all-patch-notes', 'dev/')) or re.search(r'patch-notes/\d{4}/index', base): continue
        for n, l in enumerate(Path(f).read_text(encoding='utf-8', errors='replace').splitlines(), 1):
            if hit(l): out.append((base, n, l.strip()[:200]))
    return out

if __name__ == '__main__':
    key = sys.argv[1]
    srcs = {}
    for label, fn, path in [('herc pre-re', from_herc, f'{ROOT}/hercules/db/pre-re/item_db.conf'), ('herc re', from_herc, f'{ROOT}/hercules/db/re/item_db.conf'),
                            ('rath pre-re', from_rath, f'{ROOT}/rathena/db/pre-re'), ('rath re', from_rath, f'{ROOT}/rathena/db/re')]:
        srcs[label] = norm(fn(path, key))
    iid = key if key.isdigit() else next((s['_id'] for s in srcs.values() if s and s.get('_id')), None)
    ir = from_irowiki(iid) if iid else None
    srcs['irowiki'] = norm(ir[0], emulator=False) if ir else None
    cl = from_client(iid)
    info = common.client_file_info(ROOT)
    srcs[f'client ({common.client_label(ROOT)})'] = norm(cl[0], emulator=False) if cl else None
    if info['stale']: print(f'warning: {info["stale"]}', file=sys.stderr)
    print(f'Item {key} (id {iid})\n')
    w = max(len(k) for k in srcs)
    print(f'{"":{w}}  ' + '  '.join(f'{f:<10}' for f in FIELDS))
    for k, v in srcs.items():
        print(f'{k:{w}}  ' + ('  '.join(f'{(v.get(f) or "-")[:10]:<10}' for f in FIELDS) if v else '(not found / not saved)'))
    print('\nDisagreements:')
    found = {k: v for k, v in srcs.items() if v}
    diff = False
    for f in FIELDS[2:]:  # Type names differ per project, so it is shown but not compared
        vals = {k: v[f] for k, v in found.items() if v.get(f) not in (None, '')}
        if len({x.lower() for x in vals.values()}) > 1: diff = True; print(f'  {f}: ' + ', '.join(f'{k}={v}' for k, v in vals.items()))
    if not diff: print('  none')
    if ir and ir[1]: print(f'\nirowiki description: {ir[1]}')
    if cl:
        print(f'\nClient description (ROenglishRE iteminfo, {common.client_label(ROOT)}):')
        for l in cl[1]: print('   ', l)
    name = next((v['Name'] for v in found.values() if v.get('Name')), None)
    note = common.docs_missing_note()
    if note: print('\n' + note)
    hits = doc_hits(iid, name) if iid else []
    if not note: print(f'\nproject docs / patch notes ({len(hits)} lines mention it):')
    for b, n, l in hits[:25]: print(f'  {b}:{n}: {l}')
    if len(hits) > 25: print(f'  ... {len(hits) - 25} more')
    p = common.precedence_note()
    if p: print('\n' + p)
