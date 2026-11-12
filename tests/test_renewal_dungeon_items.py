"""Tests for the uaRO rate rules in bin/renewal_dungeon_items.py."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin'))
import renewal_dungeon_items as r

class Rates(unittest.TestCase):
    def test_normal_drop_x5(self): self.assertEqual(r.uaro_rate(100, 'drop', False, False), (500, 'drop x5'))
    def test_drop_capped_at_100_percent(self): self.assertEqual(r.uaro_rate(5000, 'drop', False, False)[0], 10000)
    def test_normal_card_x5(self): self.assertEqual(r.uaro_rate(1, 'drop', True, False), (5, 'card x5'))
    def test_boss_card_x1(self): self.assertEqual(r.uaro_rate(1, 'drop', True, True), (1, 'boss card x1'))
    def test_mvp_slot_x3(self): self.assertEqual(r.uaro_rate(1000, 'mvp', False, True), (3000, 'MvP drop x3'))

if __name__ == '__main__': unittest.main()
