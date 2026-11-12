#!/usr/bin/env python3
"""Quest NPC and location for items, from RateMyServer quest pages (official iRO quests).
  fetch_rms_npcs.py [--delay SECONDS] [--refresh]
Reads index/rms-quests.json (bin/fetch_rms_quests.py), saves each 'makes' quest page unmodified under pages/ratemyserver.net/, and writes
index/rms-quest-npcs.json as {item id: {qid, town, npc, map, x, y, note, navi}}. A page holds one block per NPC and per quest; a block that
says 'Same NPC as above' uses the NPC of the block before it. 'navi' is the '/navi map x/y' text. Official iRO values, not checked against uaRO."""
import argparse, html, json, os, re, subprocess, sys, time
from pathlib import Path
ROOT = os.environ.get('GAME_DATA', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
QUEST_URL = 'https://ratemyserver.net/quest_db.php?type={}&qid={}'
BLOCK = re.compile(r"<td class = 'bborder'[^>]*><b>(?P<head>.*?)</b></td></tr>(?P<body>.*?)(?=<td class = 'bborder'[^>]*><b>[^<]*</b></td></tr>|\Z)", re.S)
NPC = re.compile(r"color:#ff6600'>(?P<npc>[^<]+)</span><br>(?P<map>[a-z0-9_@]+),(?P<x>\d+),(?P<y>\d+)")
NPC2 = re.compile(r"color:#ff6600'>(?P<npc>[^<]+)</span><br>(?P<name>[A-Za-z][A-Za-z ]*?) \((?P<x>\d+),(?P<y>\d+)\)")  # older layout: 'Prontera (157,187)', a place name
NOTE = re.compile(r"minimaps/[^>]*>\s*<br>\s*(?P<note>[^<]*)", re.S)
PRODUCT = re.compile(r"popItem\((\d+)")

def slug(url): return re.sub(r'[^A-Za-z0-9._-]+', '_', re.sub(r'^[a-z]+://[^/]+/?', '', url)).strip('_')

def map_ids():
    f = Path(ROOT) / 'rathena/db/map_index.txt'
    return {l.split()[0] for l in f.read_text().splitlines() if l.strip() and not l.startswith('//')} if f.exists() else set()

MAPS = None
def parse_npcs(page):
    global MAPS
    if MAPS is None: MAPS = map_ids()
    """{item id: {town, npc, map, x, y, note, navi}} for every product of every block on a quest page."""
    out, cur = {}, None
    for b in BLOCK.finditer(page):
        head = html.unescape(re.sub(r'<[^>]+>', '', b['head'])).strip(); body = b['body']
        town = head.split(' - ')[0].strip()
        m = NPC.search(body)
        if not m:  # place name instead of a map id: use it only when it is a map id once lowercased (Prontera, Yuno), else skip
            m2 = NPC2.search(body); mid = m2 and m2['name'].strip().lower().replace(' ', '_')
            m = {'npc': m2['npc'], 'map': mid, 'x': m2['x'], 'y': m2['y']} if m2 and mid in MAPS else None
        if m:
            n = NOTE.search(body)
            cur = {'town': town, 'npc': html.unescape(m['npc']).strip(), 'map': m['map'], 'x': int(m['x']), 'y': int(m['y']),
                   'note': html.unescape(n['note']).strip() if n else ''}
        if not cur or 'Product(s)' not in body: continue
        prod = body.split('Product(s)', 1)[1]
        cells = re.split(r"</td>\s*<td", prod)
        products = PRODUCT.findall(cells[1] if len(cells) > 1 else prod)  # second cell: what the quest gives
        for i in products: out.setdefault(int(i), {**cur, 'navi': f"/navi {cur['map']} {cur['x']}/{cur['y']}"})
    return out

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0]); ap.add_argument('--delay', type=float, default=1.0); ap.add_argument('--refresh', action='store_true'); a = ap.parse_args()
    rms = json.loads((Path(ROOT) / 'index/rms-quests.json').read_text())
    quests = sorted({(x['type'], x['qid']) for v in rms.values() for x in v if x['role'] == 'makes'})
    data, failed = {}, []
    for n, (t, q) in enumerate(quests, 1):
        url = QUEST_URL.format(t, q); f = Path(ROOT) / 'pages/ratemyserver.net' / slug(url)
        if a.refresh or not f.exists():
            r = subprocess.run([str(Path(__file__).with_name('save_page.sh')), url], env={**os.environ, 'GAME_DATA': ROOT}, capture_output=True, text=True)
            if r.returncode: failed.append(q); print(f'  {q}: not fetched'); continue
            time.sleep(a.delay)
        for i, v in parse_npcs(f.read_text(encoding='utf-8', errors='replace')).items(): data.setdefault(str(i), {'qid': q, **v})
    out = Path(ROOT) / 'index/rms-quest-npcs.json'; out.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f'{len(data)} items with an NPC from {len(quests)} quest pages; wrote {out}' + (f'; failed: {failed}' if failed else ''))

if __name__ == '__main__': main()
