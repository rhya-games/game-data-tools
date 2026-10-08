"""Tests for bin/build_item_images.py with tiny generated images."""
import contextlib, csv, io, os, sys, tempfile, unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin'))
import build_item_images as b

def gif(path, size=(24, 24), color=(200, 30, 30)):
    Path(path).parent.mkdir(parents=True, exist_ok=True); Image.new('RGB', size, color).save(path, 'GIF')

def png(path, size=(24, 24), color=(30, 30, 200, 255), hole=None):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    im = Image.new('RGBA', size, color)
    if hole: im.putpixel(hole, (0, 0, 0, 0))
    im.save(path, 'PNG')

MOBS = 'Body:\n  - Id: 1002\n    Name: Poring\n  - Id: 1005\n    Name: Familiar\n'

class BuildTests(unittest.TestCase):
    def setUp(self): self.tmp = tempfile.TemporaryDirectory(); self.t = self.tmp.name
    def tearDown(self): self.tmp.cleanup()
    def run_build(self, *extra, mobs=MOBS):
        db = f'{self.t}/mob_db.yml'; Path(db).write_text(mobs)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf): b.main(['--source', f'{self.t}/src', '--out', f'{self.t}/out', '--mob-db', db, *extra])
        return buf.getvalue()
    def manifest(self, kind):
        with open(f'{self.t}/out/{kind}/manifest.csv', encoding='utf-8') as f: return {int(r['id']): r for r in csv.DictReader(f)}

    def test_gif_icon_is_copied_byte_for_byte(self):
        gif(f'{self.t}/src/501.gif'); self.run_build()
        self.assertEqual(Path(f'{self.t}/out/items/item501.gif').read_bytes(), Path(f'{self.t}/src/501.gif').read_bytes())

    def test_png_becomes_gif_and_keeps_transparency(self):
        png(f'{self.t}/src/616.png', hole=(3, 4)); self.run_build()
        with Image.open(f'{self.t}/out/items/item616.gif') as g: self.assertEqual(g.size, (24, 24)); rgba = g.convert('RGBA')
        self.assertEqual(rgba.getpixel((3, 4))[3], 0); self.assertEqual(rgba.getpixel((0, 0))[3], 255)
        self.assertLess(sum(abs(a - c) for a, c in zip(rgba.getpixel((0, 0))[:3], (30, 30, 200))), 24)
        self.assertIn('converted from png', self.manifest('items')[616]['notes'])

    def test_preference_order(self):
        gif(f'{self.t}/src/Sub/700.gif')   # sub-folder copy
        png(f'{self.t}/src/700.png'); gif(f'{self.t}/src/700.gif', color=(1, 2, 3)); gif(f'{self.t}/src/700_1.gif')
        self.run_build()
        self.assertTrue(self.manifest('items')[700]['source'].endswith('src/700.gif'))
        gif(f'{self.t}/src2/701.gif', size=(40, 40)); png(f'{self.t}/src2/701.png')    # icon-sized beats a bigger gif
        c = b.candidates(Path(f'{self.t}/src2'))[701]; self.assertEqual(b.choose(c)['ext'], 'png')

    def test_monster_pictures_and_item_art_are_separated_by_id(self):
        gif(f'{self.t}/src/1005.gif', size=(56, 40))            # a monster id, not icon-sized -> mobs
        gif(f'{self.t}/src/2476.gif', size=(237, 188))          # not a monster -> item-art
        gif(f'{self.t}/src/1002.gif')                           # a monster id that is also an item icon -> items
        out = self.run_build()
        self.assertTrue(os.path.exists(f'{self.t}/out/mobs/mob1005.gif')); self.assertTrue(os.path.exists(f'{self.t}/out/item-art/item2476.gif'))
        self.assertTrue(os.path.exists(f'{self.t}/out/items/item1002.gif')); self.assertFalse(os.path.exists(f'{self.t}/out/items/item1005.gif'))
        self.assertIn('mobs: 1 images', out)

    def test_without_a_mob_db_everything_non_icon_is_item_art(self):
        gif(f'{self.t}/src/1005.gif', size=(56, 40))
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            b.main(['--source', f'{self.t}/src', '--out', f'{self.t}/out', '--mob-db', f'{self.t}/none.yml'])
        self.assertTrue(os.path.exists(f'{self.t}/out/item-art/item1005.gif')); self.assertIn('not found', err.getvalue())

    def test_wanted_reports_missing(self):
        gif(f'{self.t}/src/501.gif')
        Path(f'{self.t}/want.csv').write_text('item_id,name\n501,A\n502,B\n503,C\n')
        out = self.run_build('--wanted', f'{self.t}/want.csv')
        self.assertIn('have 1, missing 2', out); self.assertEqual(Path(f'{self.t}/out/items/missing.txt').read_text().split(), ['502', '503'])

    def test_dry_run_writes_nothing_and_bad_input_exits(self):
        gif(f'{self.t}/src/501.gif'); self.run_build('--dry-run'); self.assertFalse(os.path.exists(f'{self.t}/out'))
        with self.assertRaises(SystemExit): b.main(['--source', f'{self.t}/missing'])
        os.makedirs(f'{self.t}/empty')
        with self.assertRaises(SystemExit) as cm: b.main(['--source', f'{self.t}/empty'])
        self.assertIn('no <id>', str(cm.exception))

    def test_non_image_files_with_id_names_are_ignored(self):
        Path(f'{self.t}/src').mkdir(); Path(f'{self.t}/src/501.gif').write_bytes(b'not an image'); gif(f'{self.t}/src/502.gif'); self.run_build()
        self.assertFalse(os.path.exists(f'{self.t}/out/items/item501.gif')); self.assertTrue(os.path.exists(f'{self.t}/out/items/item502.gif'))

if __name__ == '__main__':
    unittest.main()
