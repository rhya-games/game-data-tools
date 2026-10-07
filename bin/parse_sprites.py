#!/usr/bin/env python3
"""Parse saved sprite lists into index/sprites.jsonl (reads pages/, never modifies them).
  parse_sprites.py --index           rebuild index/sprites.jsonl and index/viewlist_img/<id>.gif
  parse_sprites.py <id|name>         look up an ID or name across all lists (npc and headgear view IDs are different spaces)
  parse_sprites.py --gaps            headgear view IDs missing from the ai4rei viewlist (the "white gaps")
"""
import base64, html, json, os, re, sys, urllib.parse
from pathlib import Path
ROOT = os.environ.get('GAME_DATA', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def die(msg): sys.exit(f'error: {msg}')

def rd(p):
    path = f'{ROOT}/pages/{p}'
    if not os.path.isfile(path): die(f'{path} not found. Run bin/fetch_sprites.sh (README, step 4).')
    return Path(path).read_text(encoding='utf-8', errors='replace')
IDX = f'{ROOT}/index/sprites.jsonl'

def ai4rei_npc():
    d = f'{ROOT}/pages/nn.ai4rei.net'
    if not os.path.isdir(d): die(f'{d} not found. Run bin/fetch_sprites.sh (README, step 4).')
    t = ''.join(rd(f'nn.ai4rei.net/{f}') for f in sorted(os.listdir(d)) if re.fullmatch(r'dev_npclist(_qq_\d+)?', f))
    seen = set()
    for m in re.finditer(r'<div class="npc"><img [^>]*alt="([^"]*)"[^>]*>(.*?)</div></div>', t, re.S):
        i = re.search(r'ID: (\d+)', m.group(2))
        note = re.search(r'i_note" title="([^"]*)"', m.group(2))
        if i and i.group(1) not in seen:
            seen.add(i.group(1))
            yield {'source': 'ai4rei npclist', 'space': 'npc', 'id': int(i.group(1)), 'name': m.group(1),
                         'note': html.unescape(note.group(1)) if note else ''}

def dotalux_npc():
    for i, n in re.findall(r"overlib\('(\d+) : ([^']*)'\)", rd('dotalux.com/ro_npclist')):
        yield {'source': 'dotalux npclist (2009)', 'space': 'npc', 'id': int(i), 'name': n, 'note': ''}

def ai4rei_view(save_imgs=False):
    t = rd('nn.ai4rei.net/dev_viewlist')
    for m in re.finditer(r'<td><a name="id(\d+)"></a>(.*?)</td>', t, re.S):
        i, cell = int(m.group(1)), m.group(2)
        img = re.search(r'<img src="([^"]*)" alt="([^"]*)">', cell)
        srv = re.search(r'icon_note.gif" alt="" title="([^"]*)"', cell)
        kr = re.search(r'<br>([^<]*)$', cell)
        data = img.group(1).startswith('data:image/gif;base64,') if img else False
        if save_imgs and data:
            os.makedirs(f'{ROOT}/index/viewlist_img', exist_ok=True)
            Path(f'{ROOT}/index/viewlist_img/{i}.gif').write_bytes(base64.b64decode(urllib.parse.unquote(img.group(1).split(',', 1)[1])))
        yield {'source': 'ai4rei viewlist', 'space': 'headgear_view', 'id': i, 'name': img.group(2) if img else '', 'has_image': data,
               'note': f'servers: {srv.group(1)}' if srv else '', 'kr': html.unescape(kr.group(1)).strip() if kr else ''}

def checked(name, it):
    n = 0
    for r in it: n += 1; yield r
    if n == 0: die(f'{name} produced no rows. The saved page is missing entries or the site layout changed.')

def rows(save_imgs=False):
    yield from checked('ai4rei npclist', ai4rei_npc())
    if os.path.isfile(f'{ROOT}/pages/dotalux.com/ro_npclist'): yield from checked('dotalux npclist', dotalux_npc())
    yield from checked('ai4rei viewlist', ai4rei_view(save_imgs))

def load_index():
    if not os.path.isfile(IDX): die(f'{IDX} not found. Run bin/parse_sprites.py --index first.')
    return [json.loads(l) for l in Path(IDX).read_text(encoding='utf-8').splitlines()]

if __name__ == '__main__':
    a = sys.argv[1:]
    if a == ['--index']:
        try: os.makedirs(f'{ROOT}/index', exist_ok=True)
        except OSError as e: die(f'cannot create {ROOT}/index: {e.strerror}. Check GAME_DATA.')
        n = 0
        tmp = IDX + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            for r in rows(True): f.write(json.dumps(r, ensure_ascii=False) + '\n'); n += 1
        os.replace(tmp, IDX)
        print(n, 'rows ->', IDX)
    elif a == ['--gaps']:
        ids = sorted(r['id'] for r in ai4rei_view())
        have = set(ids)
        noimg = sorted(r['id'] for r in ai4rei_view() if not r['has_image'])
        print('view IDs listed:', len(ids), 'range', ids[0], '-', ids[-1])
        print('listed but no preview image:', ', '.join(map(str, noimg)) or 'none')
        print('missing:', ', '.join(str(i) for i in range(ids[0], ids[-1] + 1) if i not in have) or 'none')
    elif not a: die('usage: parse_sprites.py --index | --gaps | <id|name>')
    else:
        k = a[0].lower()
        for r in load_index():
            if str(r['id']) == k or k in r['name'].lower() or k in r.get('kr', '').lower():
                print(f"{r['space']:14} {r['id']:>6}  {r['name']:30} [{r['source']}] {r['note']} {r.get('kr', '')}")
