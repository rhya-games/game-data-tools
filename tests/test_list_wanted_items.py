"""Tests for bin/list_wanted_items.py and the --aliases option of build_item_images.py."""
import contextlib, csv, io, json, os, sys, tempfile, unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin'))
import build_item_images as b, list_wanted_items as w

def pic(path, size=(24, 24), fmt='GIF'):
    Path(path).parent.mkdir(parents=True, exist_ok=True); Image.new('RGB', size, (50, 60, 70)).save(path, fmt)

class Wanted(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); t = self.t = self.tmp.name; self.docs = f'{t}/docs'
        for n in (501, 502): pic(f'{self.docs}/img/{n}.gif')
        pic(f'{self.docs}/img/2083.gif', (60, 80))                    # a monster picture
        pic(f'{self.docs}/img/Sub/777.png', (24, 24), 'PNG'); pic(f'{self.docs}/img/Ext/830001.png', (24, 24), 'PNG'); pic(f'{self.docs}/img/13749.gif')
        Path(f'{self.docs}/a.md').write_text(
            '| ![501](img/501.gif) Red Potion | `502` |\n'
            '| ![2083](img/2083.gif) Scaraba | `@mi 2083` |\n'
            '| ![x](img/Ext/830001.png) Bolt Revolver | @ii 35658 |\n'
            '| ![13749](img/13749.gif) Potion Box | @ii 13755 |\n'
            '| ![a](img/501.gif) ![b](img/Sub/777.png) Two pictures | @ii 800 |\n')
        Path(f'{self.docs}/dev').mkdir(); Path(f'{self.docs}/dev/x.md').write_text('![9](img/9999.gif) @ii 9999\n')
        Path(f'{t}/loot.json').write_text(json.dumps([{'itemId': 2083, 'name': 'Loot item'}, {'itemId': 501, 'name': 'Red Potion'}, {'itemId': 13749, 'name': 'Other Box'}]))
        Path(f'{t}/client.lub').write_text('tbl = {\n\t[502] = {\n\t\tidentifiedDisplayName = "Orange Potion",\n\t},\n}\n')
    def tearDown(self): self.tmp.cleanup()
    def run_list(self):
        out = f'{self.t}/notes/item-images.csv'
        with contextlib.redirect_stdout(io.StringIO()): w.main(['--docs', self.docs, '--loot', f'{self.t}/loot.json', '--client', f'{self.t}/client.lub', '--out', out])
        with open(out, encoding='utf-8') as f: return {int(r['item_id']): r for r in csv.DictReader(f)}

    def test_wiki_and_loot_items_and_monster_pictures(self):
        items = self.run_list()
        self.assertEqual(sorted(items), [501, 502, 777, 800, 2083, 13749, 13755, 35658])
        self.assertEqual((items[501]['in_wiki'], items[501]['in_loot_sheet']), ('1', '1')); self.assertEqual(items[502]['name'], 'Orange Potion')
        self.assertEqual(items[2083]['in_wiki'], '0')   # a monster in the docs, but the loot sheet lists the id as an item
        self.assertNotIn(9999, items)                  # docs/dev is ignored

    def test_a_picture_filed_under_another_name_is_not_an_item_id(self):
        self.assertNotIn(830001, self.run_list())

    def test_monster_picture_alone_is_not_an_item(self):
        Path(f'{self.t}/loot.json').write_text('[]'); self.assertNotIn(2083, self.run_list())

    def test_aliases_need_one_item_one_picture_and_an_unclaimed_picture(self):
        self.run_list()
        with open(f'{self.t}/notes/item-image-aliases.csv', encoding='utf-8') as f: rows = list(csv.DictReader(f))
        self.assertEqual([(r['item_id'], os.path.basename(r['image'])) for r in rows], [('35658', '830001.png')])   # 13755 skipped: 13749 is another item; 800 skipped: two pictures

    def test_builder_uses_aliases_but_never_replaces_an_icon(self):
        self.run_list(); out = f'{self.t}/out'
        with contextlib.redirect_stdout(io.StringIO()): b.main(['--source', f'{self.docs}/img', '--out', out, '--aliases', f'{self.t}/notes/item-image-aliases.csv'])
        self.assertTrue(os.path.exists(f'{out}/items/item35658.gif'))
        with open(f'{out}/items/manifest.csv', encoding='utf-8') as f: self.assertIn('icon filed under another name', f.read())
        Path(f'{out}/items/item35658.gif').write_bytes(b'mine')
        with contextlib.redirect_stdout(io.StringIO()): b.main(['--source', f'{self.docs}/img', '--out', out, '--aliases', f'{self.t}/notes/item-image-aliases.csv'])
        self.assertEqual(Path(f'{out}/items/item35658.gif').read_bytes(), b'mine')

    def test_bad_input_exits(self):
        with self.assertRaises(SystemExit): w.main(['--docs', f'{self.t}/none', '--loot', f'{self.t}/loot.json'])

if __name__ == '__main__':
    unittest.main()
