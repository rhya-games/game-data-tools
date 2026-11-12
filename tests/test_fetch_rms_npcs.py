"""Tests for the quest NPC parser in bin/fetch_rms_npcs.py (no network)."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin'))
import fetch_rms_npcs as f

def block(head, who, products):
    return (f"<td class = 'bborder' valign = 'top' align = 'center'><b>{head}</b></td></tr><tr><td>{who}"
            "<b>Ingredient(s)</b></td><td><b>Product(s)</b></td></tr><tr><td>stuff</td><td>"
            + ''.join(f"<a href='x' onclick=\"return popItem({i},1,1)\">n</a> " for i in products) + "</td></tr>")
NEW = "<span style='color:#ff6600'>Zic</span><br>alberta,120,53\n</td><td><img src = 'https://x/minimaps/m1_0.jpg'>\n<br>South Alberta\n</td>"
SAME = "<span style='color:#ff6600'><b>Same NPC as above</b></span><br>"
OLD = "<span style='color:#ff6600'>Zhenbolt</span><br>Yuno (300,188)</td><td><img src = 'https://x/minimaps/m2_0.jpg'><br>Yuno Center East</td>"

class NpcTests(unittest.TestCase):
    def test_same_npc_inherits(self):
        r = f.parse_npcs(block('Alberta - A', NEW, [1]) + block('Alberta - B Quest', SAME, [2]))
        self.assertEqual(r[1]['navi'], '/navi alberta 120/53'); self.assertEqual(r[2]['npc'], 'Zic'); self.assertEqual(r[1]['note'], 'South Alberta')
    def test_ingredients_are_not_products(self):
        self.assertEqual(list(f.parse_npcs(block('T - A', NEW, [1]).replace('<td>stuff</td>', "<td><a onclick=\"return popItem(99,1,1)\">m</a></td>"))), [1])
    def test_place_name_layout(self):
        self.assertEqual(f.parse_npcs(block('Hot-Blooded Headband', OLD, [5070]))[5070]['navi'], '/navi yuno 300/188')
    def test_none(self): self.assertEqual(f.parse_npcs('<html>nothing</html>'), {})
if __name__ == '__main__': unittest.main()
