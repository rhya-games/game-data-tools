#!/usr/bin/env python3
"""Clean up headgear/item sprites from the ai4rei viewlist and the item icon collection.
  sprite_clean.py SRC DST [--key K]       clean one GIF into a transparent PNG (K picks the fixes entry; default: SRC's file name without extension)
  sprite_clean.py --sheet ID [ID ...] [--out FILE]   before/after contact sheet on dark and light backdrops for viewlist sprites
  sprite_clean.py --grid ID [--out FILE]  one viewlist sprite at high zoom with pixel coordinates, before and after
The sources key transparency on palette entry 0 and the art's white pixels were mapped to it, so white inside the art shows
as see-through. The tool restores it: transparent pixels connected to the border stay transparent; an enclosed transparent
gap becomes white unless it looks like a real opening (a hood's face hole): at least 12 pixels and ringed by dark pixels.
That rule cannot tell every case (outline art whose white interior leaks to the outside, a gap that should stay open), so
exceptions live in data/sprite-fixes.json, keyed by sprite id, with a note saying which hat it is:
  holes        true: leave every enclosed gap transparent
  white        true: fill every enclosed gap white
  min_fill     N: gaps smaller than N pixels stay transparent
  strip        true: drop the light-grey outline pixels from the outer edge
  pixels       [[x, y], ...]: paint these pixels white
  flood        [{"seed": [x, y], "box": [x0, y0, x1, y1]}]: paint white the see-through pixels reachable from seed inside box
  solid        true: also fill whatever lies between a part's own pixels (aggressive; changes the shape)
Look at the pixel grid (--grid) before adding an exception; the cases that took several rounds were all guessed at a small zoom."""
import argparse, json, os, sys
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = os.environ.get('GAME_DATA', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXES_FILE = Path(ROOT) / 'data/sprite-fixes.json'
HOLE_LUM, HOLE_MIN = 150, 12
WHITE = (255, 255, 255, 255)
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))

def load_fixes(path=None):
    p = Path(path or FIXES_FILE)
    return json.loads(p.read_text()).get('sprites', {}) if p.exists() else {}

def _flood_outside(px, w, h):
    seen, st = set(), [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]
    while st:
        x, y = st.pop()
        if (x, y) in seen or not (0 <= x < w and 0 <= y < h) or px[x, y][3]: continue
        seen.add((x, y)); st += [(x + dx, y + dy) for dx, dy in N4]
    return seen

def clean_image(src, dst, key=None, fixes=None):
    """GIF -> RGBA PNG at dst (parent folders made). `fixes` is the sprite's entry from sprite-fixes.json (default: looked up by key)."""
    key = key or Path(src).stem
    fx = (fixes if fixes is not None else load_fixes().get(key, {}))
    im = Image.open(src).convert('RGBA'); w, h = im.size; px = im.load()
    border = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]
    if any(px[p] == WHITE for p in border):  # a few sprites have an opaque white backdrop with transparent corners
        vis, st = set(), list(border)
        while st:
            x, y = st.pop()
            if (x, y) in vis or not (0 <= x < w and 0 <= y < h) or not (px[x, y] == WHITE or px[x, y][3] == 0): continue
            vis.add((x, y)); st += [(x + dx, y + dy) for dx, dy in N4]
        for p in vis: px[p] = (0, 0, 0, 0)
    outside = _flood_outside(px, w, h); done = set(outside)
    for y0 in range(h):
        for x0 in range(w):
            if px[x0, y0][3] or (x0, y0) in done: continue
            reg, st, ring = [], [(x0, y0)], []
            while st:
                x, y = st.pop()
                if (x, y) in done: continue
                if px[x, y][3]: ring.append(px[x, y]); continue
                done.add((x, y)); reg.append((x, y)); st += [(x + dx, y + dy) for dx, dy in N4]
            lum = sum(.3 * r + .59 * g + .11 * b for r, g, b, _ in ring) / max(len(ring), 1)
            hole = len(reg) >= HOLE_MIN and lum < HOLE_LUM
            if len(reg) < fx.get('min_fill', 0): hole = True
            if fx.get('holes'): hole = True
            if fx.get('white'): hole = False
            if not hole:
                for p in reg: px[p] = WHITE
    for f in fx.get('flood', []):
        bx0, by0, bx1, by1 = f['box']; st = [tuple(f['seed'])]
        while st:
            x, y = st.pop()
            if not (bx0 <= x <= bx1 and by0 <= y <= by1) or px[x, y][3]: continue
            px[x, y] = WHITE; st += [(x + dx, y + dy) for dx, dy in N4]
    for x, y in fx.get('pixels', []): px[x, y] = WHITE
    if fx.get('solid'): _solid(px, w, h)
    if fx.get('strip'):
        light = lambda p: .3 * p[0] + .59 * p[1] + .11 * p[2] > 205 and max(p[:3]) - min(p[:3]) < 30
        edge = [(x, y) for y in range(h) for x in range(w) if px[x, y][3] and any(
            not (0 <= x + dx < w and 0 <= y + dy < h) or (x + dx, y + dy) in outside for dx, dy in N4)]
        for e in edge:
            if light(px[e]): px[e] = (0, 0, 0, 0)
    Path(dst).parent.mkdir(parents=True, exist_ok=True); im.save(dst)
    return im

def _solid(px, w, h):
    rest, parts = {(x, y) for y in range(h) for x in range(w) if px[x, y][3]}, []
    while rest:
        comp, st = set(), [next(iter(rest))]
        while st:
            q = st.pop()
            if q in comp or q not in rest: continue
            comp.add(q); st += [(q[0] + dx, q[1] + dy) for dx in range(-2, 3) for dy in range(-2, 3)]
        rest -= comp; parts.append(comp)
    for comp in parts:
        rows, cols = {}, {}
        for x, y in comp: rows.setdefault(y, []).append(x); cols.setdefault(x, []).append(y)
        for y, xs in rows.items():
            for x in range(min(xs), max(xs) + 1):
                if not px[x, y][3] and min(cols.get(x, [h])) < y < max(cols.get(x, [-1])): px[x, y] = WHITE

def _view(i): return Path(ROOT) / f'index/viewlist_img/{i}.gif'
def _paste(canvas, im, xy, scale):
    b = im.resize((im.width * scale, im.height * scale), Image.NEAREST); canvas.paste(b, xy, b); return b.size

def sheet(ids, out, scale=4):
    """Original on dark, cleaned on dark, cleaned on light: one row per sprite, with the id and any exception written beside it."""
    fixes = load_fixes(); rows = []
    for i in ids:
        o = Image.open(_view(i)).convert('RGBA'); c = clean_image(_view(i), Path(out).parent / '.sheet-tmp.png', str(i)); rows.append((i, o, c))
    (Path(out).parent / '.sheet-tmp.png').unlink(missing_ok=True)
    cw = max(r[1].width for r in rows) * scale + 12; rh = max(r[1].height for r in rows) * scale + 22
    img = Image.new('RGB', (cw * 3, rh * len(rows)), (40, 44, 50)); d = ImageDraw.Draw(img)
    for n, (i, o, c) in enumerate(rows):
        y = n * rh; d.rectangle([2 * cw, y, 3 * cw, y + rh], fill=(235, 235, 235))
        _paste(img, o, (0, y + 4), scale); _paste(img, c, (cw, y + 4), scale); _paste(img, c, (2 * cw, y + 4), scale)
        note = ', '.join(k for k in fixes.get(str(i), {}) if k != 'note') or 'automatic'
        d.text((8, y + rh - 16), f'{i}: {note}', fill=(255, 255, 0))
    img.save(out); return out

def grid(i, out, scale=20):
    """One sprite at high zoom with x/y pixel coordinates; original on the left, cleaned on the right."""
    o = Image.open(_view(i)).convert('RGBA'); c = clean_image(_view(i), Path(out).parent / '.grid-tmp.png', str(i))
    (Path(out).parent / '.grid-tmp.png').unlink(missing_ok=True)
    w, h = o.size; img = Image.new('RGB', (2 * (w * scale + 34) + 10, h * scale + 24), (40, 44, 50)); d = ImageDraw.Draw(img)
    for n, im in enumerate((o, c)):
        ox = n * (w * scale + 44) + 30
        _paste(img, im, (ox, 20), scale)
        for x in range(w + 1): d.line([(ox + x * scale, 20), (ox + x * scale, 20 + h * scale)], fill=(70, 74, 80))
        for y in range(h + 1): d.line([(ox, 20 + y * scale), (ox + w * scale, 20 + y * scale)], fill=(70, 74, 80))
        for x in range(w): d.text((ox + x * scale + 3, 4), str(x), fill=(255, 255, 0))
        for y in range(h): d.text((ox - 26, 20 + y * scale + 4), str(y), fill=(255, 255, 0))
    img.save(out); return out

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0]); ap.add_argument('paths', nargs='*')
    ap.add_argument('--key'); ap.add_argument('--sheet', nargs='+', type=int); ap.add_argument('--grid', type=int); ap.add_argument('--out')
    a = ap.parse_args()
    if a.sheet: print(sheet(a.sheet, a.out or 'sprite-sheet.png'))
    elif a.grid is not None: print(grid(a.grid, a.out or f'sprite-grid-{a.grid}.png'))
    elif len(a.paths) == 2: clean_image(a.paths[0], a.paths[1], a.key); print(a.paths[1])
    else: ap.error('give SRC DST, --sheet IDS or --grid ID')

if __name__ == '__main__': main()
