#!/usr/bin/env python3
"""Build a collection of item icons named item<ID>.gif from the image folders of your projects.
  build_item_images.py --source ~/Projects/uaro-docs/docs/img [--source DIR ...] [--out DIR] [--wanted LIST.csv] [--dry-run]
Looks for files named <id>.gif / <id>.png (also <id>_1.png and files in sub-folders). When one item has several, it picks the
icon-sized one (24x24) first, then .gif over .png, then the top-level file over a sub-folder copy. GIFs are copied byte for byte;
PNGs are converted to GIF with their transparency. Anything that is not 24x24 goes to mobs/ (a monster picture), not items/.
Output (default <data folder>/images/):
  items/item<ID>.gif     24x24 item icons
  mobs/mob<ID>.gif       every other image: in the wiki's image folders anything that is not icon-sized is a monster picture
  each folder has manifest.csv saying which file each image came from. Items and monsters share IDs, hence the prefixes.
Cards share one picture: a source file named Card.gif is copied to items/card.gif, and with --cards-from (a rAthena db/ folder, for example
rathena/db/pre-re) every item of type Card counts as covered by it instead of being listed as missing.
--aliases takes a CSV (item_id, image) from list_wanted_items.py for icons filed under another name; they fill ids that have no icon of their own.
--wanted takes a CSV with an item_id column (for example notes/item-images.csv) and reports which of those items still have no image.
Mobs can share an ID with an item, so mob images go in their own folder as mob<ID>.gif."""
import argparse, csv, io, os, re, shutil, sys
from pathlib import Path
ROOT = os.environ.get('GAME_DATA', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NAME = re.compile(r'(\d{3,7})([_-]\d+)?\.(gif|png)', re.I)
ICON = (24, 24)

def die(msg): sys.exit(f'error: {msg}')

def candidates(source):
    """{item id: [candidate dicts]} for every <id>.gif/.png under source."""
    from PIL import Image
    out = {}
    for dp, _, fn in os.walk(source):
        for f in sorted(fn):
            m = NAME.fullmatch(f)
            if not m: continue
            p = Path(dp) / f
            try:
                with Image.open(p) as im: size, frames = im.size, getattr(im, 'n_frames', 1)
            except Exception: continue   # unreadable image: skip
            depth = len(p.relative_to(source).parts) - 1
            out.setdefault(int(m.group(1)), []).append({'path': p, 'ext': m.group(3).lower(), 'suffix': bool(m.group(2)), 'depth': depth, 'size': size, 'frames': frames})
    return out

def rank(c): return (c['size'] != ICON, c['ext'] != 'gif', c['suffix'], c['depth'], str(c['path']))

def choose(cands): return min(cands, key=rank)

def png_to_gif(src, dst):
    """Save a PNG as a GIF keeping transparent pixels transparent. Returns True if colours had to be reduced (more than 255)."""
    from PIL import Image
    with Image.open(io.BytesIO(src) if isinstance(src, bytes) else src) as im:
        rgba = im.convert('RGBA')
        colors = rgba.getcolors(maxcolors=1 << 20) or []
        reduced = len({c[:3] for _, c in colors if c[3] >= 128}) > 255
        alpha = rgba.getchannel('A')
        pal = rgba.convert('RGB').convert('P', palette=Image.ADAPTIVE, colors=255)
        mask = alpha.point(lambda a: 255 if a < 128 else 0)
        pal.paste(255, mask=mask)           # index 255 = transparent
        pal.save(dst, format='GIF', transparency=255, optimize=False)
    return reduced

def find_card_icon(sources):
    """A 24x24 file named Card.gif in the source folders (top level first)."""
    from PIL import Image
    hits = sorted((Path(dp) / f for src in sources for dp, _, fn in os.walk(src) for f in fn if f.lower() == 'card.gif'), key=lambda p: len(p.parts))
    for p in hits:
        try:
            with Image.open(p) as im:
                if im.size == ICON: return p
        except Exception: continue
    return None

def card_ids(db_dir):
    """Ids of every item of type Card in a rAthena db folder (item_db_*.yml)."""
    import glob, yaml
    loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader); out = set()
    for f in glob.glob(f'{db_dir}/item_db_*.yml'):
        out |= {d['Id'] for d in yaml.load(Path(f).read_text(encoding='utf-8'), Loader=loader).get('Body', []) if d.get('Type') == 'Card'}
    return out

def write(c, dst, dry):
    """Copy a gif or convert a png; returns (note list)."""
    notes = []
    if c['ext'] == 'png':
        notes.append('converted from png')
        if not dry and png_to_gif(c['path'], dst): notes.append('colours reduced to 255')
    elif not dry: shutil.copyfile(c['path'], dst)
    return notes

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--source', action='append', required=True, help='folder to search (repeat)')
    ap.add_argument('--out', default=f'{ROOT}/images', help='collection root: items/ and mobs/ go under it')
    ap.add_argument('--aliases', help='CSV of item_id,image for icons filed under another name')
    ap.add_argument('--wanted'); ap.add_argument('--cards-from', action='append', default=[], help='rAthena db folder (repeat for pre-re and re); items of type Card are covered by items/card.gif')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args(argv)
    try: import PIL  # noqa: F401
    except ImportError: die('Pillow is required: pip install -r requirements.txt')
    found = {}
    for src in a.source:
        if not os.path.isdir(src): die(f'{src} is not a folder')
        for i, cs in candidates(Path(src)).items(): found.setdefault(i, []).extend(cs)
    if not found: die('no <id>.gif or <id>.png images found in the source folders')
    out = {'items': [], 'mobs': []}
    for i in sorted(found):
        icons = [c for c in found[i] if c['size'] == ICON]
        others = [c for c in found[i] if c['size'] != ICON]
        if icons: out['items'].append((i, choose(icons), 'item'))
        if others: out['mobs'].append((i, choose(others), 'mob'))
    if a.aliases:
        from PIL import Image
        have_ids = {i for i, _, _ in out['items']}
        with open(a.aliases, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                i, p = int(r['item_id']), Path(r['image'])
                if i in have_ids or not p.is_file() or (Path(a.out) / 'items' / f'item{i}.gif').exists(): continue   # never replace an icon we already have
                with Image.open(p) as im: size = im.size
                if size != ICON: continue
                out['items'].append((i, {'path': p, 'ext': p.suffix.lstrip('.').lower(), 'size': size, 'alias': True}, 'item')); have_ids.add(i)
    for kind, entries in out.items():
        folder = Path(a.out) / kind
        if not a.dry_run: folder.mkdir(parents=True, exist_ok=True)
        rows = []
        old = {}
        if not a.dry_run and (folder / 'manifest.csv').exists():
            with open(folder / 'manifest.csv', encoding='utf-8', newline='') as f: old = {r['file']: r for r in csv.DictReader(f)}
        for i, c, prefix in entries:
            dst = folder / f'{prefix}{i}.gif'
            rows.append([i, dst.name, str(c['path']), f'{c["size"][0]}x{c["size"][1]}', '; '.join(write(c, dst, a.dry_run) + (['icon filed under another name'] if c.get('alias') else []))])
        made = {r[1] for r in rows}
        keep = [[r['id'], r['file'], r['source'], r['size'], r['notes']] for r in old.values() if r['file'] not in made and (folder / r['file']).exists()]
        rows += keep   # icons added by other means (downloads) stay in the collection and the manifest
        if not a.dry_run:
            with open(folder / 'manifest.csv', 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f); w.writerow(['id', 'file', 'source', 'size', 'notes']); w.writerows(rows)
        conv = sum('converted' in r[4] for r in rows)
        print(f'{kind}: {len(rows)} images' + (' (dry run)' if a.dry_run else f' -> {folder}') + f' ({conv} converted from png)')
    card = find_card_icon(a.source)
    if card:
        if not a.dry_run: shutil.copyfile(card, Path(a.out) / 'items' / 'card.gif')
        print(f'card.gif: shared card icon from {card}')
    if a.wanted:
        with open(a.wanted, encoding='utf-8') as f: want = [int(r['item_id']) for r in csv.DictReader(f)]
        have = {i for i, _, _ in out['items']} | {int(p.name[4:-4]) for p in (Path(a.out) / 'items').glob('item*.gif') if p.name[4:-4].isdigit()}
        cards = set().union(*(card_ids(d) for d in a.cards_from)) if a.cards_from and card else set()
        by_card = [i for i in want if i not in have and i in cards]
        missing = [i for i in want if i not in have and i not in cards]
        print(f'wanted {len(want)} item icons: have {len(want) - len(missing) - len(by_card)}' + (f', {len(by_card)} cards use card.gif' if by_card else '') + f', missing {len(missing)}')
        if not a.dry_run: (Path(a.out) / 'items' / 'missing.txt').write_text('\n'.join(map(str, missing)) + '\n')
    return 0

if __name__ == '__main__':
    sys.exit(main())
