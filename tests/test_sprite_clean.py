"""Tests for bin/sprite_clean.py on small synthetic sprites (no game data needed)."""
import os, sys, tempfile, unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin'))
import sprite_clean as sc

RED, DARK, GREY = (200, 40, 40, 255), (20, 10, 10, 255), (230, 230, 230, 255)

def ring(size, inner, colour=RED):
    """A gif-style image: transparent background, a closed ring of `colour`, `inner` transparent pixels square inside."""
    n = size + 2 + inner; im = Image.new('RGBA', (n + 4, n + 4), (0, 0, 0, 0)); px = im.load()
    for i in range(inner + 2):
        for a, b in ((2 + i, 2), (2 + i, 3 + inner), (2, 2 + i), (3 + inner, 2 + i)): px[a, b] = colour
    return im

class CleanTests(unittest.TestCase):
    def run_clean(self, im, key='x', fixes=None):
        d = Path(tempfile.mkdtemp()); src = d / f'{key}.png'; im.save(src)
        return sc.clean_image(src, d / 'out.png', key, fixes=fixes if fixes is not None else {})

    def test_small_enclosed_gap_becomes_white_and_outside_stays_clear(self):
        out = self.run_clean(ring(0, 1)); px = out.load()
        self.assertEqual(px[3, 3], sc.WHITE); self.assertEqual(px[0, 0][3], 0)

    def test_large_gap_ringed_by_dark_stays_open(self):
        out = self.run_clean(ring(0, 5, DARK)); self.assertEqual(out.load()[5, 5][3], 0)

    def test_large_gap_ringed_by_light_is_filled(self):
        out = self.run_clean(ring(0, 5, (240, 220, 200, 255))); self.assertEqual(out.load()[5, 5], sc.WHITE)

    def test_holes_and_white_force_the_call(self):
        self.assertEqual(self.run_clean(ring(0, 1), fixes={'holes': True}).load()[3, 3][3], 0)
        self.assertEqual(self.run_clean(ring(0, 5, DARK), fixes={'white': True}).load()[5, 5], sc.WHITE)

    def test_min_fill_keeps_small_gaps_open(self):
        self.assertEqual(self.run_clean(ring(0, 2), fixes={'min_fill': 10}).load()[3, 3][3], 0)
        self.assertEqual(self.run_clean(ring(0, 2), fixes={'min_fill': 4}).load()[3, 3], sc.WHITE)

    def test_pixels_and_flood(self):
        px = self.run_clean(ring(0, 1), fixes={'holes': True, 'pixels': [[3, 3]]}).load(); self.assertEqual(px[3, 3], sc.WHITE)
        # an open pocket: a U of pixels, flooded only inside the box
        im = Image.new('RGBA', (7, 7), (0, 0, 0, 0)); p = im.load()
        for y in range(2, 5): p[1, y] = p[4, y] = RED
        for x in range(1, 5): p[x, 5] = RED
        out = self.run_clean(im, fixes={'flood': [{'seed': [2, 3], 'box': [1, 2, 4, 4]}]}).load()
        self.assertEqual(out[2, 3], sc.WHITE); self.assertEqual(out[2, 1][3], 0)

    def test_strip_removes_light_outline_from_the_outer_edge_only(self):
        im = Image.new('RGBA', (5, 5), (0, 0, 0, 0)); p = im.load()
        for y in range(1, 4):
            for x in range(1, 4): p[x, y] = GREY if (x in (1, 3) or y in (1, 3)) else RED
        out = self.run_clean(im, fixes={'strip': True}).load()
        self.assertEqual(out[1, 1][3], 0); self.assertEqual(out[2, 2], RED)

    def test_opaque_white_backdrop_is_cleared(self):
        im = Image.new('RGBA', (6, 6), sc.WHITE); p = im.load(); p[0, 0] = (0, 0, 0, 0); p[2, 2] = p[3, 3] = RED
        self.assertEqual(self.run_clean(im).load()[5, 5][3], 0)

    def test_fixes_file_lookup_by_key(self):
        self.assertIn('165', sc.load_fixes())
        self.assertEqual(sc.load_fixes('/nonexistent.json'), {})

if __name__ == '__main__': unittest.main()
