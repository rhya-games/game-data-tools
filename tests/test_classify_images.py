"""Tests for bin/classify_images.py."""
import contextlib, csv, io, json, os, sys, tempfile, unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin'))
import classify_images as c

def pic(path, size=(24, 24)):
    Path(path).parent.mkdir(parents=True, exist_ok=True); Image.new('RGB', size, (50, 60, 70)).save(path, 'GIF')

class Verdict(unittest.TestCase):
    def test_size_alone_decides_with_a_lead_of_two(self):
        self.assertEqual(c.verdict(True, 0, 0, False, False)[:2], ('item', 'medium'))
        self.assertEqual(c.verdict(False, 0, 0, False, False)[:2], ('monster', 'medium'))

    def test_agreeing_evidence_is_high_confidence(self):
        self.assertEqual(c.verdict(True, 0, 2, True, False)[:2], ('item', 'high'))
        self.assertEqual(c.verdict(False, 3, 0, False, True)[:2], ('monster', 'high'))

    def test_conflicts_are_unsure(self):
        v = c.verdict(True, 2, 0, True, True); self.assertEqual(v[:2], ('unsure', 'low')); self.assertIn('conflict', v[4])   # icon-sized on an @mi line
        self.assertEqual(c.verdict(False, 0, 1, True, False)[0], 'unsure')                                             # big picture on an @ii line
        self.assertEqual(c.verdict(True, 1, 1, False, False)[0], 'unsure')

    def test_a_shared_id_adds_nothing(self):
        self.assertEqual(c.verdict(True, 0, 0, True, True)[2:4], (2, 0)); self.assertIn('both', c.verdict(True, 0, 0, True, True)[4])

class Classify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); t = self.t = self.tmp.name; d = self.docs = f'{t}/docs'
        pic(f'{d}/img/501.gif'); pic(f'{d}/img/1005.gif', (56, 40)); pic(f'{d}/img/2465.gif'); pic(f'{d}/img/OGH/2465.gif', (96, 124)); pic(f'{d}/img/9000.gif')
        Path(f'{d}/a.md').write_text('| ![501](img/501.gif) Red Potion | @ii 501 |\n| ![1005](img/1005.gif) Familiar | @mi 1005 |\n'
                                     '| ![2465](img/OGH/2465.gif) Corrupted Monk | @mi 2465 |\n| ![9000](img/9000.gif) Thing | @mi 9000 |\n')
        Path(f'{d}/dev').mkdir(); Path(f'{d}/dev/x.md').write_text('![501](img/501.gif) @mi 501\n')
        Path(f'{t}/db').mkdir(); Path(f'{t}/db/item_db_etc.yml').write_text('Body:\n  - Id: 501\n  - Id: 2465\n'); Path(f'{t}/db/mob_db.yml').write_text('Body:\n  - Id: 1005\n  - Id: 2465\n')
    def tearDown(self): self.tmp.cleanup()
    def run_classify(self, *extra):
        out = f'{self.t}/notes/classes.csv'; buf = io.StringIO()
        with contextlib.redirect_stdout(buf): c.main(['--docs', self.docs, '--item-db', f'{self.t}/db', '--mob-db', f'{self.t}/db', '--out', out, *extra])
        with open(out, encoding='utf-8') as f: return {r['file']: r for r in csv.DictReader(f)}, buf.getvalue()

    def test_verdicts_per_file(self):
        rows, text = self.run_classify()
        self.assertEqual(rows['501.gif']['verdict'], 'item'); self.assertEqual(rows['501.gif']['confidence'], 'high')   # dev/ pages are ignored
        self.assertEqual(rows['1005.gif']['verdict'], 'monster'); self.assertEqual(rows['9000.gif']['verdict'], 'unsure')
        self.assertIn('unsure 9000.gif', text)

    def test_one_id_can_be_an_item_icon_and_a_monster_picture(self):
        rows, text = self.run_classify()
        self.assertEqual((rows['2465.gif']['verdict'], rows['OGH/2465.gif']['verdict']), ('item', 'monster'))
        self.assertIn('ids with both an item icon and a monster picture: 1', text)

    def test_loot_sheet_counts_as_an_item_id(self):
        Path(f'{self.t}/loot.json').write_text(json.dumps([{'itemId': 1005}]))
        rows, _ = self.run_classify('--loot', f'{self.t}/loot.json'); self.assertEqual(rows['1005.gif']['monster_points'], '5')   # big (2) + @mi (3); id is both so no extra point

    def test_bad_input_exits(self):
        with self.assertRaises(SystemExit): c.main(['--docs', f'{self.t}/none'])
        os.makedirs(f'{self.t}/empty/img')
        with self.assertRaises(SystemExit): c.main(['--docs', f'{self.t}/empty'])

if __name__ == '__main__':
    unittest.main()
