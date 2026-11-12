"""Tests for the uaRO rate rules in bin/renewal_items.py."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin'))
import renewal_items as r

class Rates(unittest.TestCase):
    def test_normal_drop_x5(self): self.assertEqual(r.uaro_rate(100, 'drop', False, False), (500, 'drop x5'))
    def test_drop_capped_at_100_percent(self): self.assertEqual(r.uaro_rate(5000, 'drop', False, False)[0], 10000)
    def test_normal_card_x5(self): self.assertEqual(r.uaro_rate(1, 'drop', True, False), (5, 'card x5'))
    def test_boss_card_x1(self): self.assertEqual(r.uaro_rate(1, 'drop', True, True), (1, 'boss card x1'))
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
                      'jobs': None, 'level': None, 'script': '', 'renewal_only': True, 'box': None, 'drop_effects': [], 'dropped_by': []}
        idx = r.build_index({'X': {'items': {'a': it()}}, 'Y': {'items': {'a': it()}}})
        self.assertEqual([a['area'] for a in idx[0]['areas']], ['X', 'Y'])
