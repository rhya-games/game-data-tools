"""Tests for the uaRO rate rules in bin/renewal_items.py."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin'))
import renewal_items as r

class Rates(unittest.TestCase):
    def test_normal_drop_x5(self): self.assertEqual(r.uaro_rate(100, 'drop', False, False), (500, 'drop x5'))
    def test_drop_capped_at_100_percent(self): self.assertEqual(r.uaro_rate(5000, 'drop', False, False)[0], 10000)
    def test_normal_card_x5(self): self.assertEqual(r.uaro_rate(1, 'drop', True, False), (5, 'card x5'))
    def test_boss_card_x1(self): self.assertEqual(r.uaro_rate(1, 'drop', True, True), (1, 'boss card x1'))
    def test_mvp_monster_normal_drop_x3(self): self.assertEqual(r.uaro_rate(500, 'drop', False, True, True), (1500, 'MvP monster drop x3'))
    def test_miniboss_normal_drop_x5(self): self.assertEqual(r.uaro_rate(500, 'drop', False, True, False), (2500, 'drop x5'))
    def test_mvp_slot_x3(self): self.assertEqual(r.uaro_rate(1000, 'mvp', False, True), (3000, 'MvP drop x3'))

if __name__ == '__main__': unittest.main()

class Effects(unittest.TestCase):
    def test_race_drop_x5(self):
        e = r.drop_effects('bonus3 bAddMonsterDropItem,12031,RC_Fish,100;', {}, {})[0]
        self.assertEqual((e['official_pct'], e['uaro_pct'], e['from']), (1.0, 5.0, 'Fish monsters'))
    def test_any_monster_and_cap(self):
        e = r.drop_effects('bonus2 bAddMonsterDropItem,501,3000;', {}, {})[0]
        self.assertEqual((e['official_pct'], e['uaro_pct'], e['from']), (30.0, 100.0, 'any monster'))

class Index(unittest.TestCase):
    def test_merges_areas(self):
        it = lambda: {'id': 1, 'name': 'A', 'type': 'Card', 'slots': 0, 'weight': 1, 'buy': None, 'sell': None, 'attack': None, 'defense': None, 'location': None,
                      'jobs': None, 'level': None, 'script': '', 'renewal_only': True, 'box': None, 'drop_effects': [], 'dropped_by': [], 'aegis': 'A'}
        idx = r.build_index({'X': {'items': {'a': it()}}, 'Y': {'items': {'a': it()}}})
        self.assertEqual([a['area'] for a in idx[0]['areas']], ['X', 'Y'])

class Stale(unittest.TestCase):
    def test_no_meta_no_warning(self): self.assertEqual(r.stale_note('/nonexistent/renewal-items.meta'), '')
    def test_different_commit_warns(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            m = os.path.join(d, 'm.meta'); open(m, 'w').write('rathena_commit: 0000000000000000\n')
            real = r.rathena_commit; r.rathena_commit = lambda: 'ffffffffffffffff'
            try: self.assertIn('rebuild', r.stale_note(m))
            finally: r.rathena_commit = real

class Lookup(unittest.TestCase):
    def test_record_lines_show_both_rates(self):
        rec = {'id': 1, 'name': 'A Card', 'type': 'Card', 'slots': 0, 'renewal_only': True, 'box': None, 'combos': [], 'description': [],
               'areas': [{'area': 'X', 'dropped_by': [{'name': 'M', 'rate_pct': 0.01, 'uaro_pct': 0.05, 'rule': 'card x5'}]}],
               'drop_effects': [{'drops': 'Fish (1)', 'from': 'Fish monsters', 'official_pct': 1.0, 'uaro_pct': 5.0}]}
        text = '\n'.join(r.record_lines(rec))
        self.assertIn('0.01% -> 0.05%', text); self.assertIn('1% -> 5%', text)

class Chests(unittest.TestCase):
    def test_chest_chance_from_rand_condition(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(f'{d}/s'); open(f'{d}/s/i.txt', 'w').write(
                'case 1:\n\tmakeitem 7642,1, map, 1, 1;\n\tif (rand(1,1000) > 150)\n\t\tmakeitem 644,1, map,1,1;// Gift_Box\n\tbreak;\n')
            old, r.RA = r.RA, d
            try: out = r.chest_items('s/i.txt', {7642: {'Id': 7642}, 644: {'Id': 644}}, {})
            finally: r.RA = old
        self.assertEqual(out, [(7642, 1, 100.0, 1), (644, 1, 85.0, 1)])
