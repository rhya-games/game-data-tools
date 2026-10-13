#!/usr/bin/env python3
"""Download monster pictures into the collection as mob<ID>.gif (animated, in the format the sites serve).
  fetch_mob_sprites.py [ID ...] [--ids-file FILE] [--wiki DOCS_DIR] [--endless-tower] [--out DIR] [--delay SECONDS] [--limit N] [--dry-run]
Where the IDs come from (all given sources are combined):
  ID ...            monster ids on the command line
  --ids-file FILE   one id per line
  --wiki DIR        monsters a wiki docs folder mentions: `@mi <id>`, prose such as `Frilldora (`1119`)` where the name is that id's
                    monster, and the ID column of any table whose header has a Monster column. Item ids that look the same are ignored
                    because the name has to match the monster database (--mob-db). all-patch-notes and dev/ pages are skipped.
  --endless-tower   every monster the Endless Tower script spawns (rAthena npc/instances/EndlessTower.txt; --tower-script to point
                    at another copy). rAthena and Hercules spawn the same 327 monsters. These are the emulator's values, not
                    confirmed for uaRO.
Pictures already in the collection (mob<ID>.gif or mob<ID>.png) are never replaced. Each id is tried on the sources in order,
RateMyServer first (the wiki's pictures came from there) and Divine Pride second (it has newer and custom ids); a 404 moves on to
the next source. Requests are sequential with a pause between them (default 1 second) and a User-Agent naming this tool. Anything
else wrong (blocked, rate limited, server errors) is retried with a longer pause, then stops the run so you can re-run it later:
finished pictures are kept. Sources are recorded in <out>/manifest.csv and ids no source has in <out>/not-found.txt.
Output default: <data folder>/images/mobs/ (set GAME_DATA to keep the data elsewhere)."""
import argparse, csv, glob, io, os, re, sys, time, urllib.error, urllib.request
from pathlib import Path
ROOT = os.environ.get('GAME_DATA', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCES = ['https://file5s.ratemyserver.net/mobs/{}.gif',
           'https://www.divine-pride.net/Tools/SpriteGif?monsterId={}&actionIndex=0']
UA = 'game-data-tools (monster picture fetch; github.com/rhya-games/game-data-tools)'
TOWER = 'rathena/npc/instances/EndlessTower.txt'
MOB_DBS = ['rathena/db/pre-re/mob_db.yml', 'rathena/db/re/mob_db.yml']
SPAWN = re.compile(r'^\s*(?:areamonster|monster)\b(.*);', re.M)
SPAWN_ID = re.compile(r'"[^"]*"\s*,\s*(\d+)\s*,')
MI = re.compile(r'@mi\s*(\d{3,6})')
PROSE = re.compile(r"((?:[A-Za-z][A-Za-z'\-]*\s+){0,4}[A-Za-z][A-Za-z'\-]*)\s*\(`(\d{3,6})`")
TICK = re.compile(r'`(\d{3,6})`')

def die(msg): sys.exit(f'error: {msg}')

def fetch(url, timeout=30):
    """(status, body). HTTP errors return their status; network errors raise OSError."""
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, r.read()
    except urllib.error.HTTPError as e: return e.code, b''
    except urllib.error.URLError as e:
        if 'CERTIFICATE_VERIFY_FAILED' in str(e.reason): die('Python cannot verify HTTPS certificates. On macOS run "Install Certificates.command" from /Applications/Python 3.x/.')
        raise OSError(str(e.reason)) from None

def picture(body):
    """(width, height, frames) of a GIF, or None when the body is not a GIF."""
    from PIL import Image
    try:
        with Image.open(io.BytesIO(body)) as im:
            return (im.size[0], im.size[1], getattr(im, 'n_frames', 1)) if im.format == 'GIF' else None
    except Exception: return None

def have(out, i): return any((out / f'mob{i}.{e}').exists() for e in ('gif', 'png'))

def mob_names(paths):
    """{monster id: name} from rAthena mob_db.yml files; later files win."""
    import yaml
    loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader); names = {}
    for p in paths:
        data = yaml.load(Path(p).read_text(encoding='utf-8'), Loader=loader)
        names.update({x['Id']: str(x.get('Name') or x.get('AegisName') or '') for x in data.get('Body', [])})
    return names

def tower_ids(script, names):
    """Monster ids the Endless Tower script spawns."""
    if not os.path.isfile(script): die(f'{script} not found (--tower-script points at the Endless Tower script)')
    ids = {int(m.group(1)) for line in SPAWN.finditer(Path(script).read_text(encoding='utf-8', errors='replace'))
           for m in SPAWN_ID.finditer(line.group(1))}
    if not ids: die(f'no monster spawns found in {script}')
    return {i for i in ids if i in names}

def _norm(s):
    """Lower case words with plural endings removed, so "Orc Ladies" matches "Orc Lady"."""
    out = []
    for w in re.findall(r"[a-z0-9']+", s.lower()):
        w = w[:-3] + 'y' if w.endswith('ies') else w[:-1] if w.endswith('s') and not w.endswith('ss') else w
        out.append(w)
    return out

def _cells(line): return [c.strip() for c in line.strip().strip('|').split('|')]

def wiki_ids(docs, names):
    """Monster ids the wiki mentions (see the module doc for the three ways)."""
    if not os.path.isdir(docs): die(f'{docs} is not a folder')
    ids = set()
    for f in sorted(Path(docs).rglob('*.md')):
        if f.relative_to(docs).as_posix().startswith(('all-patch-notes', 'dev/')): continue
        id_col = None
        for line in f.read_text(encoding='utf-8', errors='replace').splitlines():
            ids |= {int(x) for x in MI.findall(line)}
            for m in PROSE.finditer(line):
                i, words = int(m.group(2)), _norm(m.group(1))
                if i in names and (n := _norm(names[i])) and words[-len(n):] == n: ids.add(i)
            if line.lstrip().startswith('|'):
                cells = _cells(line)
                low = [c.lower() for c in cells]
                if 'monster' in low and 'id' in low: id_col = low.index('id'); continue
                if id_col is not None and id_col < len(cells): ids |= {int(x) for x in TICK.findall(cells[id_col]) if int(x) in names}
            else: id_col = None
    return ids

def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('ids', nargs='*', type=int, help='monster ids')
    ap.add_argument('--ids-file'); ap.add_argument('--wiki'); ap.add_argument('--endless-tower', action='store_true')
    ap.add_argument('--tower-script', default=f'{ROOT}/{TOWER}'); ap.add_argument('--mob-db', action='append')
    ap.add_argument('--out', default=f'{ROOT}/images/mobs')
    ap.add_argument('--source', action='append', help='URL template with {} for the id; repeat for fallbacks (default: RateMyServer, then Divine Pride)')
    ap.add_argument('--delay', type=float, default=1.0); ap.add_argument('--limit', type=int)
    ap.add_argument('--dry-run', action='store_true')
    return ap.parse_args(argv)

def main(argv=None, sleep=time.sleep):
    a = parse_args(argv)
    if not (a.ids or a.ids_file or a.wiki or a.endless_tower): die('give ids, --ids-file, --wiki or --endless-tower')
    try: import PIL  # noqa: F401
    except ImportError: die('Pillow is required: pip install -r requirements.txt')
    ids = set(a.ids)
    if a.ids_file:
        if not os.path.isfile(a.ids_file): die(f'{a.ids_file} not found')
        ids |= {int(x) for x in Path(a.ids_file).read_text().split()}
    if a.wiki or a.endless_tower:
        dbs = a.mob_db or [p for p in (f'{ROOT}/{d}' for d in MOB_DBS) if os.path.isfile(p)]
        if not dbs: die('no monster database found (rathena/db/*/mob_db.yml); run setup.sh or pass --mob-db')
        try: import yaml  # noqa: F401
        except ImportError: die('PyYAML is required: pip install -r requirements.txt')
        names = mob_names(dbs)
        found = {}
        if a.wiki: found['wiki'] = wiki_ids(a.wiki, names)
        if a.endless_tower: found['Endless Tower'] = tower_ids(a.tower_script, names)
        for k, v in found.items(): print(f'{k}: {len(v)} monsters'); ids |= v
    out = Path(a.out); ids = sorted(ids)
    todo = [i for i in ids if not have(out, i)]
    print(f'{len(ids)} ids, {len(ids) - len(todo)} already in the collection, {len(todo)} to fetch' + (' (dry run)' if a.dry_run else ''))
    if a.limit: todo = todo[:a.limit]
    if a.dry_run: print(' '.join(map(str, todo))); return 0
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / 'manifest.csv'; new = not manifest.exists()
    sources = a.source or SOURCES
    got, missing, bad = 0, [], 0
    with open(manifest, 'a', newline='', encoding='utf-8') as mf:
        w = csv.writer(mf)
        if new: w.writerow(['id', 'file', 'source', 'size', 'notes'])
        for n, i in enumerate(todo, 1):
            saved = False
            for tmpl in sources:
                url = tmpl.format(i)
                for attempt in range(1, 5):
                    try: status, body = fetch(url)
                    except OSError as e: status, body = f'network: {e}', b''
                    if status in (200, 404): break
                    if attempt == 4:
                        print(f'stopping after {got} pictures: {url} kept failing ({status}). Re-run later; finished pictures are kept.', file=sys.stderr)
                        (out / 'not-found.txt').write_text('\n'.join(map(str, missing)) + '\n'); return 1
                    sleep(a.delay * 5 * attempt)
                sleep(a.delay)
                if status == 404: continue
                if not (pic := picture(body)): bad += 1; print(f'rejected {i} from {url}: not a GIF', file=sys.stderr); continue
                (out / f'mob{i}.gif').write_bytes(body)
                w.writerow([i, f'mob{i}.gif', url, f'{pic[0]}x{pic[1]}', 'downloaded' + (f'; animated, {pic[2]} frames' if pic[2] > 1 else '')]); mf.flush()
                got += 1; saved = True; break
            if not saved: missing.append(i)
            if n % 50 == 0: print(f'  {n}/{len(todo)}: saved {got}, not on the sites {len(missing)}', flush=True)
    (out / 'not-found.txt').write_text('\n'.join(map(str, missing)) + '\n')
    print(f'saved {got}; not on the sites {len(missing)}; rejected {bad}')
    if missing: print('not found: ' + ' '.join(map(str, missing)))
    return 0

if __name__ == '__main__':
    sys.exit(main())
