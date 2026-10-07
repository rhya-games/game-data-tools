#!/usr/bin/env python3
"""Parse the client iteminfo Lua (ROenglishRE itemInfo.lua, saved at pages/downloads/itemInfo.lua by setup.sh) into index/iteminfo.jsonl.
  parse_iteminfo.py --index        rebuild the index
  parse_iteminfo.py <id|name>      show one item or all items matching a name (description, slots, view ID)
  parse_iteminfo.py --view N       items whose ClassNum (headgear/weapon view ID) is N
  parse_iteminfo.py --check-herc   compare ClassNum with Hercules ViewSprite (pre-re) and list mismatches
ClassNum is the view/sprite ID, the same number space as the ai4rei headgear list.
The file mixes servers: the `server` field says which one wrote the entry (server codes such as iRO, jRO). Missing means unknown.
"""
import datetime, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
from pathlib import Path
ROOT = os.environ.get('GAME_DATA', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = f'{ROOT}/pages/downloads/itemInfo.lua'
IDX = f'{ROOT}/index/iteminfo.jsonl'
clean = lambda s: re.sub(r'\^[0-9A-Fa-f]{6}', '', s)

def lua_str(s): return s.replace('\\"', '"').replace('\\\\', '\\')

def die(msg): sys.exit(f'error: {msg}')

def load_index():
    if not os.path.isfile(IDX): die(f'{IDX} not found. Run bin/parse_iteminfo.py --index first.')
    return [json.loads(l) for l in Path(IDX).read_text(encoding='utf-8').splitlines()]

def entries():
    if not os.path.isfile(SRC): die(f'{SRC} not found. Run setup.sh or see README, step 3.')
    t = Path(SRC).read_text(encoding='utf-8', errors='replace')
    for m in re.finditer(r'^\t\[(\d+)\] = \{\n(.*?)^\t\},?$', t, re.S | re.M):
        b = m.group(2)
        g = lambda k: (re.search(rf'^\t\t{k} = (.+?),?$', b, re.M) or [None, None])[1]
        name = re.search(r'^\t\tidentifiedDisplayName = "(.*?)",\n', b, re.M)
        dm = re.search(r'^\t\tidentifiedDescriptionName = \{(.*?)\n\t\t\}', b, re.S | re.M)
        lines = [lua_str(x) for x in re.findall(r'"((?:[^"\\]|\\.)*)"', dm.group(1))] if dm else []
        srv = re.search(r'Server = "(\w+)"', b)
        yield {'id': int(m.group(1)), 'name': lua_str(name.group(1)) if name else '', 'description': [clean(x) for x in lines],
               'description_raw': lines, 'slots': int(g('slotCount') or 0), 'view': int(g('ClassNum') or 0),
               'costume': g('costume') == 'true', 'server': srv.group(1) if srv else None}

META = f'{ROOT}/index/iteminfo.meta'

def write_meta():
    """Record which download the index was built from (variant and commit come from fetch_iteminfo.sh's sidecar)."""
    f = common.read_kv(f'{SRC}.meta')
    lines = [f'{k}: {f.get(k, "unknown")}' for k in ('variant', 'commit', 'sha256')] + [f'built: {datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}']
    Path(META).write_text('\n'.join(lines) + '\n', encoding='utf-8')

def banner():
    """One line saying which client file the results come from, plus a warning if the index is out of date."""
    info = common.client_file_info(ROOT)
    print(f'[client item file: {common.client_label(ROOT)}]')
    if info['stale']: print(f'[warning: {info["stale"]}]', file=sys.stderr)

def show(r):
    print(f"{r['id']}  {r['name']}  [slots {r['slots']}, view {r['view']}{', costume' if r['costume'] else ''}, server {r['server'] or 'unknown'}]")
    for l in r['description']: print('   ', l)

def herc_views():
    if not os.path.isfile(f'{ROOT}/hercules/db/pre-re/item_db.conf'): die('hercules/ not found. Run setup.sh.')
    t = Path(f'{ROOT}/hercules/db/pre-re/item_db.conf').read_text(encoding='utf-8', errors='replace')
    out = {}
    for m in re.finditer(r'\n\{\n(.*?)\n\}', t, re.S):
        i = re.search(r'^\tId: (\d+)', m.group(1), re.M); v = re.search(r'^\tViewSprite: (\d+)', m.group(1), re.M)
        if i and v: out[int(i.group(1))] = int(v.group(1))
    return out

if __name__ == '__main__':
    a = sys.argv[1:]
    if a == ['--index']:
        try: os.makedirs(f'{ROOT}/index', exist_ok=True)
        except OSError as e: die(f'cannot create {ROOT}/index: {e.strerror}. Check GAME_DATA.')
        n = 0
        tmp = IDX + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            for r in entries(): f.write(json.dumps(r, ensure_ascii=False) + '\n'); n += 1
        if n == 0: os.remove(tmp); die(f'no items parsed from {SRC}. The file format may have changed.')
        os.replace(tmp, IDX)
        write_meta()
        print(n, 'items ->', IDX, f'({common.client_label(ROOT)})')
    elif a == ['--check-herc']:
        banner(); hv = herc_views(); ii = {r['id']: r for r in load_index()}
        print('(Hercules pre-re ViewSprite is compared; a Renewal client file legitimately differs for items renewal changed.)')
        bad = [(i, v, ii[i]['view'], ii[i]['name']) for i, v in sorted(hv.items()) if i in ii and ii[i]['view'] != v]
        print(len(hv), 'Hercules items with ViewSprite;', len(bad), 'differ from iteminfo ClassNum')
        for i, v, c, n in bad[:40]: print(f'  {i} {n}: Hercules {v}, iteminfo {c}')
    elif a[:1] == ['--view']:
        banner()
        for r in load_index():
            if r['view'] == int(a[1]): show(r)
    elif not a: die('usage: parse_iteminfo.py --index | --view N | --check-herc | <id|name>')
    else:
        banner()
        k = a[0].lower()
        for r in load_index():
            if str(r['id']) == k or k == r['name'].lower(): show(r)
