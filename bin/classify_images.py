#!/usr/bin/env python3
"""Decide whether each wiki image named by an id is an item icon or a monster picture, and say why. One row per image file: the
same id can have an item icon and a monster picture (2465 is Dance Shoes and also the Corrupted Monk).
  classify_images.py --docs DIR [--images DIR] [--client itemInfo.lub] [--item-db DB ...] [--mob-db DB ...] [--loot loot.json] [--out CSV]
Evidence per id (one point scale, item vs monster):
  size      24x24 is an icon (item +2); anything bigger is a monster picture, the wiki's convention (monster +2)
  docs      the lines that show the picture: `@ii` means item (+3), `@mi` means monster (+3)
  ids       known only as an item (client file, emulator item db, loot sheet): item +1; known only as a monster: monster +1; both: 0
A verdict needs a lead of 2 points; a smaller lead is "unsure", and conflicting evidence (for example an icon-sized picture on an
@mi line) is always "unsure". --item-db / --mob-db take rAthena db folders (item_db_*.yml / mob_db.yml), repeatable.
Writes <out> (default notes/image-classes.csv) with the evidence and a reasons column, and prints the unsure ones."""
import argparse, csv, glob, json, os, re, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_item_images as b
ROOT = os.environ.get('GAME_DATA', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMG_REF = re.compile(r'img/((?:[A-Za-z0-9_\-]+/)*(\d{3,7})(?:[_-]\d+)?\.(?:gif|png|webp))')

def die(msg): sys.exit(f'error: {msg}')

def doc_context(docs):
    """{image path under img/ (lower case): {'mi': lines with @mi, 'ii': lines with @ii, 'pages': set}}"""
    ctx = {}
    for f in sorted(Path(docs).rglob('*.md')):
        rel = f.relative_to(docs).as_posix()
        if rel.startswith(('all-patch-notes', 'dev/')): continue
        for line in f.read_text(encoding='utf-8', errors='replace').splitlines():
            mi, ii = bool(re.search(r'@mi\b', line)), bool(re.search(r'@ii\b', line))
            for m in IMG_REF.finditer(line):
                c = ctx.setdefault(m.group(1).lower(), {'mi': 0, 'ii': 0, 'pages': set()})
                c['mi'] += mi; c['ii'] += ii; c['pages'].add(rel.removesuffix('.md'))
    return ctx

def emulator_ids(dirs, pattern, key):
    import yaml
    loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader); out = set()
    for d in dirs:
        for f in glob.glob(f'{d}/{pattern}'):
            out |= {x['Id'] for x in yaml.load(Path(f).read_text(encoding='utf-8'), Loader=loader).get(key, [])}
    return out

def verdict(size_icon, mi, ii, item_known, mob_known):
    """(verdict, confidence, item points, monster points, reasons)"""
    item = mob = 0; why = []
    if size_icon: item += 2; why.append('icon-sized (24x24)')
    else: mob += 2; why.append('bigger than an icon')
    if ii: item += 3; why.append(f'@ii on {ii} line(s)')
    if mi: mob += 3; why.append(f'@mi on {mi} line(s)')
    if item_known and not mob_known: item += 1; why.append('id is only an item')
    elif mob_known and not item_known: mob += 1; why.append('id is only a monster')
    elif item_known and mob_known: why.append('id is both an item and a monster')
    conflict = (size_icon and mi and not ii) or (not size_icon and ii and not mi) or (mi and ii)
    lead = item - mob
    if conflict or abs(lead) < 2: return 'unsure', 'low', item, mob, '; '.join(why + (['evidence conflicts'] if conflict else []))
    return ('item' if lead > 0 else 'monster'), ('high' if abs(lead) >= 4 else 'medium'), item, mob, '; '.join(why)

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--docs', required=True); ap.add_argument('--images'); ap.add_argument('--client'); ap.add_argument('--loot')
    ap.add_argument('--item-db', action='append', default=[]); ap.add_argument('--mob-db', action='append', default=[])
    ap.add_argument('--out', default=f'{ROOT}/notes/image-classes.csv')
    a = ap.parse_args(argv)
    if not os.path.isdir(a.docs): die(f'{a.docs} is not a folder')
    images = Path(a.images or Path(a.docs) / 'img')
    if not images.is_dir(): die(f'{images} is not a folder')
    cands = b.candidates(images)
    if not cands: die(f'no <id>.gif or <id>.png images in {images}')
    items = set()
    if a.client:
        import parse_iteminfo as p
        p.SRC = a.client; items |= {r['id'] for r in p.entries()}
    items |= emulator_ids(a.item_db, 'item_db_*.yml', 'Body')
    loot = set()
    if a.loot: loot = {x['itemId'] for x in json.loads(Path(a.loot).read_text(encoding='utf-8')) if x.get('itemId')}
    mobs = emulator_ids(a.mob_db, 'mob_db.yml', 'Body')
    ctx = doc_context(a.docs); rows = []
    for i in sorted(cands):
        for x in sorted(cands[i], key=lambda x: str(x['path'])):
            rel = x['path'].relative_to(images).as_posix()
            c = ctx.get(rel.lower(), {'mi': 0, 'ii': 0, 'pages': set()})
            v, conf, ip, mp, why = verdict(x['size'] == b.ICON, c['mi'], c['ii'], i in items or i in loot, i in mobs)
            rows.append([i, rel, v, conf, ip, mp, f'{x["size"][0]}x{x["size"][1]}', int(i in items), int(i in loot), int(i in mobs), c['ii'], c['mi'], ' '.join(sorted(c['pages']))[:80], why])
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['id', 'file', 'verdict', 'confidence', 'item_points', 'monster_points', 'size', 'item_id_known', 'in_loot_sheet', 'monster_id_known', 'ii_lines', 'mi_lines', 'pages', 'reasons']); w.writerows(rows)
    counts = {k: sum(r[2] == k for r in rows) for k in ('item', 'monster', 'unsure')}
    both = len({r[0] for r in rows if r[2] == 'item'} & {r[0] for r in rows if r[2] == 'monster'})
    print(f'{len(rows)} image files ({len({r[0] for r in rows})} ids): item {counts["item"]}, monster {counts["monster"]}, unsure {counts["unsure"]} -> {a.out}')
    print('by confidence: ' + ', '.join(f'{k} {sum(r[3] == k for r in rows)}' for k in ('high', 'medium', 'low')) + f'; ids with both an item icon and a monster picture: {both}')
    for r in rows:
        if r[2] == 'unsure': print(f'  unsure {r[1]}: {r[13]}  [{r[12]}]')
    return 0

if __name__ == '__main__':
    sys.exit(main())
