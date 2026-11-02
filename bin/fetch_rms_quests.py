#!/usr/bin/env python3
"""Find the RateMyServer quest page(s) for items, from each item's RateMyServer page.
  fetch_rms_quests.py ID [ID ...] | --ids FILE   [--delay SECONDS] [--refresh]
The item page lists the quests that make or use the item as links to quest_db.php?type=T&qid=Q. Pages are saved unmodified under
pages/ratemyserver.net/ (an existing page is reused unless --refresh), one request per --delay seconds (default 1), and the links are
written to index/rms-quests.json as {item id: [{qid, type, role, title, url}]}; an item with no quest gets an empty list. Official iRO quests
only: RateMyServer knows nothing of uaRO's own quests."""
import argparse, html, json, os, re, subprocess, sys, time
from pathlib import Path
ROOT = os.environ.get('GAME_DATA', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ITEM_URL = 'https://ratemyserver.net/index.php?page=item_db&item_id={}'
QUEST_URL = 'https://ratemyserver.net/quest_db.php?type={}&qid={}'
LINK = re.compile(r"""<a\s+href\s*=\s*['"]quest_db\.php\?type=(\d+)&(?:amp;)?qid=(\d+)['"][^>]*>(.*?)</a>""", re.S)

def slug(url): return re.sub(r'[^A-Za-z0-9._-]+', '_', re.sub(r'^[a-z]+://[^/]+/?', '', url)).strip('_')

def parse_quests(page):
    """Quest links on an item page, de-duplicated by qid, in page order. 'role' is the row they sit in:
    'makes' (Obtainable From: the quest gives the item) or 'uses' (Required For: the quest takes it as a material)."""
    out, seen = [], set()
    for m in LINK.finditer(page):
        t, q, title = m.groups()
        if q in seen: continue
        seen.add(q); th = re.findall(r'<th[^>]*>([^<]*)</th>', page[:m.start()])
        out.append({'qid': int(q), 'type': int(t), 'role': 'makes' if th and th[-1].strip() == 'Obtainable From' else 'uses',
                    'title': html.unescape(re.sub(r'<[^>]+>', '', title)).strip(), 'url': QUEST_URL.format(t, q)})
    return out

def page_for(item, refresh):
    url = ITEM_URL.format(item); f = Path(ROOT) / 'pages/ratemyserver.net' / slug(url)
    if refresh or not f.exists():
        r = subprocess.run([str(Path(__file__).with_name('save_page.sh')), url], env={**os.environ, 'GAME_DATA': ROOT}, capture_output=True, text=True)
        if r.returncode: return None
        return f.read_text(encoding='utf-8', errors='replace'), True
    return f.read_text(encoding='utf-8', errors='replace'), False

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0]); ap.add_argument('ids', nargs='*', type=int); ap.add_argument('--ids', dest='file')
    ap.add_argument('--delay', type=float, default=1.0); ap.add_argument('--refresh', action='store_true'); a = ap.parse_args()
    ids = a.ids + ([int(x) for x in Path(a.file).read_text().split()] if a.file else [])
    if not ids: sys.exit('error: give item ids or --ids FILE')
    out_f = Path(ROOT) / 'index/rms-quests.json'; out_f.parent.mkdir(exist_ok=True)
    data = json.loads(out_f.read_text()) if out_f.exists() else {}
    failed = []
    for n, i in enumerate(ids, 1):
        got = page_for(i, a.refresh)
        if got is None: failed.append(i); print(f'  {i}: not fetched'); continue
        page, fetched = got; data[str(i)] = parse_quests(page)
        if fetched: time.sleep(a.delay)
        if n % 20 == 0: print(f'  {n}/{len(ids)}')
    out_f.write_text(json.dumps(data, indent=1))
    print(f'{sum(1 for i in ids if data.get(str(i)))} of {len(ids)} items have an RMS quest; wrote {out_f}' + (f'; failed: {failed}' if failed else ''))

if __name__ == '__main__': main()
