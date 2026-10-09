#!/usr/bin/env python3
"""Download missing item icons (24x24) into the collection as item<ID>.gif; RateMyServer by default.
  fetch_item_icons.py [--ids FILE] [--out DIR] [--delay SECONDS] [--limit N] [--dry-run]
IDs come from --ids (one per line; default <out>/missing.txt written by build_item_images.py --wanted). Icons already in the
collection are never replaced. Requests are sequential with a pause between them (default 1 second) and a User-Agent naming this
tool. Each icon must be 24x24; a PNG (Divine Pride) is converted to GIF keeping transparency. Anything else is rejected.
  e.g. --base-url https://static.divine-pride.net/images/items/item/{}.png A 404 is recorded as "not on the site". Anything else wrong (blocked,
rate limited, server errors) is retried with a longer pause, then stops the run so you can re-run it later: finished icons are kept.
RateMyServer answers 200 with a "No Image" picture for ids it does not have, so the run first asks for an impossible id and treats any
icon identical to that answer as "not on the site". Sources are recorded in <out>/manifest.csv, and ids the site does not have in <out>/not-found.txt."""
import argparse, csv, io, os, sys, time, urllib.error, urllib.request
from pathlib import Path
ROOT = os.environ.get('GAME_DATA', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = 'https://file5s.ratemyserver.net/items/small/{}.gif'
UA = 'game-data-tools (item icon fetch; github.com/rhya-games/game-data-tools)'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_item_images import png_to_gif

def die(msg): sys.exit(f'error: {msg}')

def fetch(url, timeout=20):
    """(status, body). HTTP errors return their status; network errors raise OSError."""
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, r.read()
    except urllib.error.HTTPError as e: return e.code, b''
    except urllib.error.URLError as e:
        if 'CERTIFICATE_VERIFY_FAILED' in str(e.reason): die('Python cannot verify HTTPS certificates. On macOS run "Install Certificates.command" from /Applications/Python 3.x/.')
        raise OSError(str(e.reason)) from None

def valid_icon(body):
    """'gif' or 'png' for a 24x24 image of that kind, else None."""
    from PIL import Image
    try:
        with Image.open(io.BytesIO(body)) as im: return im.format.lower() if im.format in ('GIF', 'PNG') and im.size == (24, 24) else None
    except Exception: return None

def main(argv=None, sleep=time.sleep):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=f'{ROOT}/images/items'); ap.add_argument('--ids')
    ap.add_argument('--base-url', default=BASE, help='URL template with {} for the id')
    ap.add_argument('--delay', type=float, default=1.0); ap.add_argument('--limit', type=int)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--sentinel', type=int, default=99999999, help='an id the site cannot have, to learn its "no image" picture')
    a = ap.parse_args(argv)
    ids_file = a.ids or f'{a.out}/missing.txt'
    if not os.path.isfile(ids_file): die(f'{ids_file} not found. Run build_item_images.py --wanted first, or pass --ids.')
    try: import PIL  # noqa: F401
    except ImportError: die('Pillow is required: pip install -r requirements.txt')
    out = Path(a.out)
    ids = [int(x) for x in Path(ids_file).read_text().split()]
    todo = [i for i in ids if not (out / f'item{i}.gif').exists()]
    if a.limit: todo = todo[:a.limit]
    print(f'{len(ids)} ids, {len(ids) - len([i for i in ids if not (out / f"item{i}.gif").exists()])} already in the collection, {len(todo)} to fetch' + (' (dry run)' if a.dry_run else ''))
    if a.dry_run: return 0
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / 'manifest.csv'; new = not manifest.exists()
    got, missing, bad = 0, [], 0
    try: placeholder = fetch(a.base_url.format(a.sentinel))[1]
    except OSError: placeholder = b''
    print('site placeholder for unknown ids:', 'detected' if placeholder else 'none (sentinel id returned nothing usable)')
    with open(manifest, 'a', newline='', encoding='utf-8') as mf:
        w = csv.writer(mf)
        if new: w.writerow(['id', 'file', 'source', 'size', 'notes'])
        for n, i in enumerate(todo, 1):
            url = a.base_url.format(i)
            for attempt in range(1, 5):
                try: status, body = fetch(url)
                except OSError as e: status, body = f'network: {e}', b''
                if status == 200 or status == 404: break
                if attempt == 4: print(f'stopping after {got} icons: {url} kept failing ({status}). Re-run later; finished icons are kept.', file=sys.stderr); (out / 'not-found.txt').write_text('\n'.join(map(str, missing)) + '\n'); return 1
                sleep(a.delay * 5 * attempt)
            if status == 404 or (placeholder and body == placeholder): missing.append(i)
            elif not (kind := valid_icon(body)): bad += 1; print(f'rejected {i}: not a 24x24 GIF or PNG', file=sys.stderr)
            else:
                dst = out / f'item{i}.gif'
                if kind == 'png': png_to_gif(body, dst)
                else: dst.write_bytes(body)
                w.writerow([i, dst.name, url, '24x24', 'downloaded' + ('; converted from png' if kind == 'png' else '')]); mf.flush(); got += 1
            if n % 50 == 0: print(f'  {n}/{len(todo)}: saved {got}, not on site {len(missing)}', flush=True)
            sleep(a.delay)
    (out / 'not-found.txt').write_text('\n'.join(map(str, missing)) + '\n')
    print(f'saved {got}; not on the site {len(missing)}; rejected {bad}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
