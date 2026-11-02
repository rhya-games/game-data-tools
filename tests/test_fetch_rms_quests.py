"""Tests for the quest-link parser in bin/fetch_rms_quests.py (no network)."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin'))
import fetch_rms_quests as f

PAGE = ("<th class='lmd'>Obtainable From</th><td><a href = 'quest_db.php?type=10000&qid=10034' target = '_blank' class='gen_m'>Bao Bao, Cresent Hairpin &amp; Heart Hairpin</a><br></td>"
        "<a href='quest_db.php?type=10000&qid=10034'>again</a><th>Required For</th><a href = \"quest_db.php?type=2&amp;qid=7\"><b>Other</b></a><a href='item_db.php'>no</a>")

class ParseTests(unittest.TestCase):
    def test_links(self):
        q = f.parse_quests(PAGE)
        self.assertEqual([x['qid'] for x in q], [10034, 7])
        self.assertEqual(q[0]['title'], 'Bao Bao, Cresent Hairpin & Heart Hairpin')
        self.assertEqual(q[0]['url'], 'https://ratemyserver.net/quest_db.php?type=10000&qid=10034')
        self.assertEqual(q[1]['title'], 'Other')
        self.assertEqual([x['role'] for x in q], ['makes', 'uses'])
    def test_none(self): self.assertEqual(f.parse_quests('<html>nothing</html>'), [])
    def test_slug_matches_save_page(self):
        self.assertEqual(f.slug(f.ITEM_URL.format(5048)), 'index.php_page_item_db_item_id_5048')
if __name__ == '__main__': unittest.main()
