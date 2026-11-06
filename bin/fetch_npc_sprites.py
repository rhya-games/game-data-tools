#!/usr/bin/env python3
"""Download NPC sprite thumbnails (the images on the ai4rei npclist) by sprite name.
  fetch_npc_sprites.py 4_F_SISTER [NAME ...]   save images/npcs/<NAME>.gif for each name (see parse_sprites.py for names and IDs)
  fetch_npc_sprites.py --force NAME            download again even when the file exists
Names are the ones in index/sprites.jsonl (ai4rei npclist), for example 4_F_SISTER.
"""
import os, sys, urllib.request
ROOT = os.environ.get('GAME_DATA', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = f'{ROOT}/images/npcs'
BASE = 'https://nn.ai4rei.net/dev/npclist/'
HDR = {'User-Agent': 'Mozilla/5.0', 'Referer': BASE + '?qq=0'}


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=60) as r: return r.read()
    except OSError as e: sys.exit(f'error: {url}: {e}')


def main(names, force):
    os.makedirs(OUT, exist_ok=True)
    for n in names:
        dst = f'{OUT}/{n}.gif'
        if os.path.isfile(dst) and not force: print('exists', n); continue
        data = get(f'{BASE}i/{n}.gif')
        if not data.startswith(b'GIF8'): sys.exit(f'error: {n}: the site did not return a GIF')
        open(dst, 'wb').write(data); print('downloaded', n)


if __name__ == '__main__':
    a = sys.argv[1:]
    force = '--force' in a
    names = [x for x in a if x != '--force']
    if not names: sys.exit(__doc__)
    main(names, force)
