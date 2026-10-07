"""Fixture-based tests for the parsers and comparison helpers. Run: python3 -m unittest discover -s tests"""
import contextlib, io, json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin'))
import common, compare_item, parse_iteminfo, parse_sprites

HERC = '''item_db: (
{
\tId: 501
\tName: "Red_Potion"
\tType: "IT_HEALING"
\tBuy: 50
\tWeight: 70
},
{
\tId: 1201
\tName: "Knife"
\tType: "IT_WEAPON"
\tBuy: 50
\tSell: 10
\tWeight: 400
\tAtk: 17
\tSlots: 3
}
)
'''
HERC_MOB = '''{
\tId: 1002
\tName: "Poring"
\tStats: {
\t\tStr: 6
\t\tLuk: 30
\t}
\tElement: ("Ele_Water", 1)
}'''
RATH = '''Header:
  Type: ITEM_DB
Body:
  - Id: 501
    AegisName: Red_Potion
    Name: Red Potion
    Type: Healing
    Buy: 10
    Weight: 70
  - Id: 1201
    AegisName: Knife
    Name: Knife
    Type: Weapon
    Buy: 50
    Sell: 10
    Weight: 400
    Attack: 17
    Slots: 3
'''
LUA = '''tbl = {
\t[501] = {
\t\tidentifiedDisplayName = "Red Potion",
\t\tidentifiedDescriptionName = {
\t\t\t"^777777A potion.^000000",
\t\t\t"Weight: ^0000007"
\t\t},
\t\tslotCount = 0,
\t\tClassNum = 0,
\t\tcostume = false
\t},
\t[2201] = {
\t\tServer = "iRO",
\t\tidentifiedDisplayName = "Sunglasses \\"X\\"",
\t\tidentifiedDescriptionName = {
\t\t\t"Shades."
\t\t},
\t\tslotCount = 1,
\t\tClassNum = 5,
\t\tcostume = true
\t},
}
'''

def tmp_file(dirpath, name, text, enc='utf-8'):
    path = os.path.join(dirpath, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding=enc) as f: f.write(text)
    return path

class Common(unittest.TestCase):
    def test_val(self):
        v = common._val
        self.assertEqual((v('"x",'), v('true'), v('1_000'), v('0x10'), v('Ele_Water')), ('x', True, 1000, 16, 'Ele_Water'))

    def test_herc_parse_nested(self):
        d = common.herc_parse(HERC_MOB.strip('{}\n'))
        self.assertEqual((d['Id'], d['Name'], d['Stats']), (1002, 'Poring', {'Str': 6, 'Luk': 30}))
        self.assertEqual(d['Element'], '("Ele_Water", 1)')

    def test_herc_blocks_and_strip_prefix(self):
        with tempfile.TemporaryDirectory() as t:
            blocks = common.herc_blocks(tmp_file(t, 'db.conf', HERC))
        self.assertEqual(len(blocks), 2)
        self.assertEqual((common.strip_prefix('Ele_Water'), common.strip_prefix('Size_Small'), common.strip_prefix(None)), ('Water', 'Small', None))

    def run_table(self, srcs):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf): common.print_table(srcs, ['Buy', 'Name'])
        return buf.getvalue()

    def test_print_table_flags_disagreement(self):
        out = self.run_table({'a': {'Buy': 50, 'Name': 'X'}, 'b': {'Buy': 10, 'Name': 'x'}, 'c': None})
        self.assertIn('Buy: a=50, b=10', out)
        self.assertNotIn('Name:', out.split('Disagreements:')[1])  # case-insensitive match
        self.assertIn('(not found)', out)

    def test_print_table_no_disagreement(self):
        self.assertIn('none', self.run_table({'a': {'Buy': 5, 'Name': 'X'}, 'b': {'Buy': 5, 'Name': 'X'}}).split('Disagreements:')[1])

    def test_doc_hits_skips_longer_names(self):
        with tempfile.TemporaryDirectory() as t:
            tmp_file(t, 'a.md', 'Poring drops Jellopy\nPoring Card is rare\nsee `501`\n')
            old, common.DOCS = common.DOCS, t
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf): common.doc_hits({'Poring'}, __import__('re').compile(r'`501`'))
            finally: common.DOCS = old
        out = buf.getvalue()
        self.assertIn('a.md:1', out); self.assertIn('a.md:3', out); self.assertNotIn('a.md:2', out)

class CompareItem(unittest.TestCase):
    def test_from_herc_by_id_and_name(self):
        with tempfile.TemporaryDirectory() as t:
            p = tmp_file(t, 'item_db.conf', HERC)
            self.assertEqual(compare_item.from_herc(p, '1201')['Name'], 'Knife')
            r = compare_item.from_herc(p, 'red_potion')
            self.assertEqual((r['_id'], r['Type'], r['Buy']), ('501', 'HEALING', '50'))
            self.assertIsNone(compare_item.from_herc(p, '9999'))

    def test_from_rath(self):
        with tempfile.TemporaryDirectory() as t:
            tmp_file(t, 'item_db_usable.yml', RATH)
            r = compare_item.from_rath(t, '1201')
            self.assertEqual((r['Name'], r['Atk'], r['Slots']), ('Knife', 17, 3))
            self.assertEqual(compare_item.from_rath(t, 'red potion')['Buy'], 10)
            self.assertIsNone(compare_item.from_rath(t, '42'))

    def test_norm_weight_and_sell(self):
        r = compare_item.norm({'Weight': 70, 'Buy': 50, 'Sell': None})
        self.assertEqual((r['Weight'], r['Sell']), ('7', '25'))
        r = compare_item.norm({'Weight': 405, 'Buy': 50, 'Sell': 10})
        self.assertEqual((r['Weight'], r['Sell']), ('40.5', '10'))
        self.assertEqual(compare_item.norm({'Weight': 70}, emulator=False)['Weight'], '70')
        self.assertIsNone(compare_item.norm(None))

class IteminfoParser(unittest.TestCase):
    def parse(self, text, enc='utf-8'):
        with tempfile.TemporaryDirectory() as t:
            old, parse_iteminfo.SRC = parse_iteminfo.SRC, tmp_file(t, 'itemInfo.lua', text, enc)
            try: return list(parse_iteminfo.entries())
            finally: parse_iteminfo.SRC = old

    def test_entries(self):
        a, b = self.parse(LUA)
        self.assertEqual((a['id'], a['name'], a['description'], a['slots'], a['server']), (501, 'Red Potion', ['A potion.', 'Weight: 7'], 0, None))
        self.assertEqual((b['id'], b['name'], b['view'], b['costume'], b['server']), (2201, 'Sunglasses "X"', 5, True, 'iRO'))
        self.assertEqual(a['description_raw'][0], '^777777A potion.^000000')

    def test_non_ascii_utf8(self):
        self.assertEqual(self.parse(LUA.replace('Shades.', 'Café'))[1]['description'], ['Café'])

    def test_garbage_yields_nothing(self):
        self.assertEqual(self.parse('this is not lua'), [])

    def test_missing_source_exits_with_message(self):
        old, parse_iteminfo.SRC = parse_iteminfo.SRC, '/nonexistent/itemInfo.lua'
        try:
            with self.assertRaises(SystemExit) as cm: list(parse_iteminfo.entries())
        finally: parse_iteminfo.SRC = old
        self.assertIn('not found', str(cm.exception))

VIEW = ('<table><tr><td><a name="id7"></a><img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" alt="Angel Wing">'
        '<img src="x/icon_note.gif" alt="" title="iRO, kRO"><br>엔젤윙</td></tr>'
        '<tr><td><a name="id9"></a>no image here</td></tr></table>')
NPC = ('<div class="npc"><img src="a.gif" alt="PORING"><span>ID: 1002</span><img class="i_note" title="a &amp; b"></div></div>'
       '<div class="npc"><img src="b.gif" alt="DUP"><span>ID: 1002</span></div></div>')

class SpriteParser(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = parse_sprites.ROOT, parse_sprites.IDX
        parse_sprites.ROOT = self.tmp.name
        parse_sprites.IDX = f'{self.tmp.name}/index/sprites.jsonl'

    def tearDown(self):
        parse_sprites.ROOT, parse_sprites.IDX = self.old
        self.tmp.cleanup()

    def test_viewlist(self):
        tmp_file(self.tmp.name, 'pages/nn.ai4rei.net/dev_viewlist', VIEW)
        rows = list(parse_sprites.ai4rei_view(save_imgs=True))
        self.assertEqual([r['id'] for r in rows], [7, 9])
        self.assertEqual((rows[0]['name'], rows[0]['has_image'], rows[0]['note'], rows[0]['kr']), ('Angel Wing', True, 'servers: iRO, kRO', '엔젤윙'))
        self.assertFalse(rows[1]['has_image'])
        self.assertTrue(os.path.isfile(f'{self.tmp.name}/index/viewlist_img/7.gif'))

    def test_npclist_dedupes_ids_across_pages(self):
        tmp_file(self.tmp.name, 'pages/nn.ai4rei.net/dev_npclist_qq_0', NPC)
        tmp_file(self.tmp.name, 'pages/nn.ai4rei.net/dev_npclist_qq_1', NPC)
        rows = list(parse_sprites.ai4rei_npc())
        self.assertEqual([(r['id'], r['name'], r['note']) for r in rows], [(1002, 'PORING', 'a & b')])

    def test_dotalux(self):
        tmp_file(self.tmp.name, 'pages/dotalux.com/ro_npclist', "<a onmouseover=\"return overlib('45 : (warp)')\">")
        self.assertEqual(list(parse_sprites.dotalux_npc())[0]['id'], 45)

    def test_missing_pages_exit_with_message(self):
        with self.assertRaises(SystemExit) as cm: list(parse_sprites.ai4rei_view())
        self.assertIn('fetch_sprites.sh', str(cm.exception))

    def test_checked_rejects_empty_source(self):
        with self.assertRaises(SystemExit) as cm: list(parse_sprites.checked('x', iter([])))
        self.assertIn('no rows', str(cm.exception))

if __name__ == '__main__':
    unittest.main()
