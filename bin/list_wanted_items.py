#!/usr/bin/env python3
"""List the items your projects need an icon for.
  list_wanted_items.py --docs ~/Projects/uaro-docs/docs --loot ~/Projects/uaro-loot-sheet/src/data/loot.json [--client itemInfo_pro.lub] [--out CSV]
Wiki items are ids that the docs show with an item icon, write as `@ii <id>`, or give in backticks when the id is a real item in the
client item file. An id whose only wiki pictures are bigger than an icon is a monster picture (the wiki's convention), so it is left out,
unless the docs call it with @ii. (The loot sheet may still list the same id as an item; then it is wanted, but not counted as a wiki item.) Loot sheet items come from its itemId fields.
Writes <out> (item_id, name, in_wiki, in_loot_sheet) and, next to it, item-image-aliases.csv for items whose 24x24 icon is filed under
another name (a docs line with one `@ii <id>` and one image, named differently), which build_item_images.py --aliases uses."""
import argparse, csv, json, os, re, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.environ.get('GAME_DATA', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMG_REF = re.compile(r'img/((?:[A-Za-z0-9_\-]+/)*(\d{3,7})(?:[_-]\d+)?\.(?:gif|png|webp))')
II, TICK = re.compile(r'@ii\s+(\d{3,7})'), re.compile(r'`(\d{3,7})`')
ANY_IMG = re.compile(r'img/((?:[A-Za-z0-9_\-]+/)*[A-Za-z0-9_\-]+\.(?:gif|png))')

def die(msg): sys.exit(f'error: {msg}')

def scan_docs(docs):
    """(ids shown as images, ids from @ii, ids in backticks, alias candidates {id: [image paths]})"""
    img, ii, tick, alias = set(), set(), set(), {}
    for f in sorted(Path(docs).rglob('*.md')):
        rel = f.relative_to(docs).as_posix()
        if rel.startswith(('all-patch-notes', 'dev/')): continue
        for line in f.read_text(encoding='utf-8', errors='replace').splitlines():
            ids = {int(x) for x in II.findall(line)}; ii |= ids
            tick |= {int(x) for x in TICK.findall(line)}
            pics = ANY_IMG.findall(line)
            if len(ids) == 1 and len(pics) == 1:   # one item, one picture on the line: the picture is that item's icon
                (i,) = ids
                if not re.fullmatch(rf'(?:.*/)?{i}(?:[_-]\d+)?\.(?:gif|png)', pics[0]):
                    alias.setdefault(i, []).append(pics[0]); continue   # filed under another name: its number is not an item id
            for m in IMG_REF.finditer(line): img.add(int(m.group(2)))
    return img, ii, tick, alias

def icon_sized_ids(images):
    import build_item_images as b
    found = b.candidates(Path(images))
    return {i for i, cs in found.items() if any(c['size'] == b.ICON for c in cs)}, set(found)

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--docs', required=True); ap.add_argument('--loot', required=True)
    ap.add_argument('--images', help='image folder (default <docs>/img)'); ap.add_argument('--client', help='client item file for names and real-item checks')
    ap.add_argument('--out', default=f'{ROOT}/notes/item-images.csv')
    a = ap.parse_args(argv)
    for p in (a.docs, a.loot):
        if not os.path.exists(p): die(f'{p} not found')
    images = a.images or str(Path(a.docs) / 'img')
    if not os.path.isdir(images): die(f'{images} is not a folder')
    names = {}
    if a.client:
        import parse_iteminfo as p
        p.SRC = a.client; names = {r['id']: r['name'] for r in p.entries()}
    img, ii, tick, alias = scan_docs(a.docs)
    loot = {x['itemId']: x['name'] for x in json.loads(Path(a.loot).read_text(encoding='utf-8')) if x.get('itemId')}
    has_icon, has_any = icon_sized_ids(images)
    wiki = {i for i in img if i in has_icon or i not in has_any or i in ii} | ii | {i for i in tick if i in names}
    allids = sorted(wiki | set(loot))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['item_id', 'name', 'in_wiki', 'in_loot_sheet'])
        for i in allids: w.writerow([i, loot.get(i) or names.get(i, ''), int(i in wiki), int(i in loot)])
    aliases = Path(a.out).with_name('item-image-aliases.csv')
    with open(aliases, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['item_id', 'image'])
        for i in sorted(alias):
            if i in has_icon: continue
            for im in dict.fromkeys(alias[i]):
                stem = re.match(r'(\d+)', Path(im).stem)
                if stem and (int(stem.group(1)) in names or int(stem.group(1)) in loot): continue   # the picture belongs to another item (a copy-paste in the docs)
                w.writerow([i, str(Path(images) / im)])
    print(f'{len(allids)} items: wiki {len(wiki)}, loot sheet {len(loot)}, both {len(wiki & set(loot))} -> {a.out}')
    print(f'excluded as monster pictures: {len(img - wiki)}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
