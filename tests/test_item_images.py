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

class BuildTests(unittest.TestCase):
    def setUp(self): self.tmp = tempfile.TemporaryDirectory(); self.t = self.tmp.name
    def tearDown(self): self.tmp.cleanup()
    def run_build(self, *extra):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf): b.main(['--source', f'{self.t}/src', '--out', f'{self.t}/out', *extra])
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

    def test_non_icon_images_are_monster_pictures(self):
        gif(f'{self.t}/src/1005.gif', size=(56, 40)); gif(f'{self.t}/src/2476.gif', size=(237, 188))
        gif(f'{self.t}/src/1002.gif'); gif(f'{self.t}/src/Mobs/1002.gif', size=(30, 30))   # an id used by an item icon and a monster picture
        out = self.run_build()
        for n in ('mobs/mob1005.gif', 'mobs/mob2476.gif', 'mobs/mob1002.gif', 'items/item1002.gif'): self.assertTrue(os.path.exists(f'{self.t}/out/{n}'), n)
        self.assertFalse(os.path.exists(f'{self.t}/out/items/item1005.gif')); self.assertIn('mobs: 3 images', out)

    def test_classes_csv_overrides_size(self):
        gif(f'{self.t}/src/501.gif'); gif(f'{self.t}/src/900.gif'); gif(f'{self.t}/src/901.gif', size=(60, 80)); gif(f'{self.t}/src/902.gif', size=(60, 80)); gif(f'{self.t}/src/Sub/501.gif', size=(96, 124))
        Path(f'{self.t}/classes.csv').write_text('id,file,verdict\n501,501.gif,item\n501,Sub/501.gif,monster\n900,900.gif,monster\n901,901.gif,item\n902,902.gif,unsure\n')
        err = io.StringIO()
        with contextlib.redirect_stderr(err): self.run_build('--classes', f'{self.t}/classes.csv')
        o = lambda n: os.path.exists(f'{self.t}/out/{n}')
        self.assertTrue(o('items/item501.gif') and o('mobs/mob501.gif') and o('mobs/mob900.gif') and o('items/item901.gif'))   # a 24x24 monster and a big item follow the verdict
        self.assertFalse(o('items/item900.gif') or o('mobs/mob902.gif') or o('items/item902.gif'))
        self.assertIn('skipped as unsure', err.getvalue()); self.assertIn('902\t902.gif\tunsure', Path(f'{self.t}/out/unsure.txt').read_text())

    def test_files_missing_from_the_classes_csv_are_skipped_not_guessed(self):
        gif(f'{self.t}/src/501.gif'); gif(f'{self.t}/src/502.gif'); Path(f'{self.t}/classes.csv').write_text('id,file,verdict\n501,501.gif,item\n')
        with contextlib.redirect_stderr(io.StringIO()): self.run_build('--classes', f'{self.t}/classes.csv')
        self.assertFalse(os.path.exists(f'{self.t}/out/items/item502.gif')); self.assertIn('not in the classes file', Path(f'{self.t}/out/unsure.txt').read_text())

    def test_wanted_reports_missing(self):
        gif(f'{self.t}/src/501.gif')
        Path(f'{self.t}/want.csv').write_text('item_id,name\n501,A\n502,B\n503,C\n')
        out = self.run_build('--wanted', f'{self.t}/want.csv')
        self.assertIn('have 1, missing 2', out); self.assertEqual(Path(f'{self.t}/out/items/missing.txt').read_text().split(), ['502', '503'])

    def test_rebuilding_keeps_icons_added_by_other_means(self):
        gif(f'{self.t}/src/501.gif'); self.run_build()
        gif(f'{self.t}/out/items/item999.gif')                        # an icon added later, e.g. downloaded
        with open(f'{self.t}/out/items/manifest.csv', 'a', encoding='utf-8') as fh: fh.write('999,item999.gif,https://example/999.gif,24x24,downloaded\n')
        Path(f'{self.t}/want.csv').write_text('item_id\n501\n999\n1000\n')
        out = self.run_build('--wanted', f'{self.t}/want.csv')
        self.assertIn('have 2, missing 1', out); self.assertIn('downloaded', self.manifest('items')[999]['notes']); self.assertEqual(len(self.manifest('items')), 2)

    def test_cards_share_one_icon_and_are_not_missing(self):
        gif(f'{self.t}/src/Card.gif', color=(10, 20, 30)); gif(f'{self.t}/src/501.gif')
        Path(f'{self.t}/db').mkdir(); Path(f'{self.t}/db/item_db_etc.yml').write_text('Body:\n  - Id: 4001\n    Type: Card\n  - Id: 4002\n    Type: Card\n  - Id: 901\n    Type: Etc\n')
        Path(f'{self.t}/want.csv').write_text('item_id\n501\n4001\n4002\n901\n')
        out = self.run_build('--wanted', f'{self.t}/want.csv', '--cards-from', f'{self.t}/db')
        self.assertEqual(Path(f'{self.t}/out/items/card.gif').read_bytes(), Path(f'{self.t}/src/Card.gif').read_bytes())
        self.assertIn('have 1, 2 cards use card.gif, missing 1', out); self.assertEqual(Path(f'{self.t}/out/items/missing.txt').read_text().split(), ['901'])

    def test_cards_are_still_missing_without_a_card_icon(self):
        gif(f'{self.t}/src/501.gif'); Path(f'{self.t}/db').mkdir(); Path(f'{self.t}/db/item_db_etc.yml').write_text('Body:\n  - Id: 4001\n    Type: Card\n')
        Path(f'{self.t}/want.csv').write_text('item_id\n4001\n')
        self.assertIn('missing 1', self.run_build('--wanted', f'{self.t}/want.csv', '--cards-from', f'{self.t}/db'))

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
