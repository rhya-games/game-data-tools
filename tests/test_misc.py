"""Tests for the irowiki page parser, compare_item's client and docs lookups, and the shell scripts (offline paths only)."""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin')
sys.path.insert(0, BIN)
import compare_item, parse_irowiki_item as irowiki

PAGE = '''<script>var curID = 740;</script>
<td class="mdTitle" colspan="2">Knife &amp; Fork</td>
<td class="bgLtRow1 padded">Sharp.<br>Very sharp.</td>
<table><tr><td class="x infoTitle">Buying Price</td> <td class="y infoText">1,200z (sell 600z)</td></tr>
<tr><td class="x infoTitle">Weight</td><td class="y infoText"><b>40</b></td></tr></table>
<div>Monster Drops</div><table>
<tr><td></td><td><a href="/monster-info/1002">Poring</a></td><td>70%</td></tr>
<tr><td>no id here</td><td>x</td><td>1%</td></tr></table>'''

def sh(script, *args, env=None):
    return subprocess.run([os.path.join(BIN, script), *args], capture_output=True, text=True, env={**os.environ, **(env or {})})

class Irowiki(unittest.TestCase):
    def test_parse(self):
        d = irowiki.parse(PAGE)
        self.assertEqual((d['id'], d['name'], d['description']), (740, 'Knife & Fork', 'Sharp.\nVery sharp.'))
        self.assertEqual(d['fields'], {'Buying Price': '1,200z (sell 600z)', 'Weight': '40'})
        self.assertEqual(d['drops'], [{'monster_id': 1002, 'monster': 'Poring', 'rate': '70%'}])

    def test_parse_empty_page(self):
        d = irowiki.parse('<html></html>')
        self.assertEqual((d['id'], d['name'], d['fields'], d['drops']), (None, None, {}, []))

    def test_load_missing_page_raises(self):
        old, irowiki.PAGES = irowiki.PAGES, '/nonexistent'
        try:
            with self.assertRaises(FileNotFoundError): irowiki.load(1)
        finally: irowiki.PAGES = old

class CompareItemLookups(unittest.TestCase):
    def test_from_client_reads_stats_from_description(self):
        with tempfile.TemporaryDirectory() as t:
            os.makedirs(f'{t}/index')
            row = {'id': 1201, 'name': 'Knife', 'description': ['Attack: 17', 'Weight: 40', 'Required Level: 5'], 'slots': 3}
            Path(f'{t}/index/iteminfo.jsonl').write_text(json.dumps(row) + '\n')
            old, compare_item.ROOT = compare_item.ROOT, t
            try:
                r, desc = compare_item.from_client(1201)
                self.assertEqual((r['Atk'], r['Weight'], r['Level'], r['Slots']), ('17', '40', '5', '3'))
                self.assertIsNone(compare_item.from_client(9))
                self.assertIsNone(compare_item.from_client(None))
            finally: compare_item.ROOT = old

    def test_from_client_without_index(self):
        old, compare_item.ROOT = compare_item.ROOT, '/nonexistent'
        try: self.assertIsNone(compare_item.from_client(1))
        finally: compare_item.ROOT = old

    def test_doc_hits(self):
        with tempfile.TemporaryDirectory() as t:
            for rel, text in (('a.md', 'Knife is 1201\nVenom Knife is not\nKnife Goblin neither\n'), ('all-patch-notes.md', 'Knife\n'), ('dev/x.md', 'Knife\n')):
                os.makedirs(os.path.dirname(f'{t}/{rel}') or t, exist_ok=True); Path(f'{t}/{rel}').write_text(text)
            old, compare_item.common.DOCS = compare_item.common.DOCS, t
            try: hits = compare_item.doc_hits('1201', 'Knife [3]')
            finally: compare_item.common.DOCS = old
        self.assertEqual([(b, n) for b, n, _ in hits], [('a.md', 1)])

class ShellScripts(unittest.TestCase):
    def test_save_page_file_mode_is_byte_exact_with_meta(self):
        with tempfile.TemporaryDirectory() as t:
            src = f'{t}/src.html'; Path(src).write_bytes(b'<p>\xff raw</p>\n')
            r = sh('save_page.sh', 'https://example.com/a/b?c=1', '--file', src, env={'GAME_DATA': t})
            self.assertEqual(r.returncode, 0, r.stderr)
            saved = f'{t}/pages/example.com/a_b_c_1'
            self.assertEqual(Path(saved).read_bytes(), b'<p>\xff raw</p>\n')
            meta = Path(saved + '.meta').read_text()
            self.assertIn('via: file', meta); self.assertIn('bytes: 13', meta)

    def test_fetch_iteminfo_rejects_bad_variant(self):
        r = sh('fetch_iteminfo.sh', env={'ITEMINFO_VARIANT': 'bogus', 'GAME_DATA': '/nonexistent'})
        self.assertNotEqual(r.returncode, 0); self.assertIn('Renewal or Pre-Renewal', r.stderr)

    def test_fetch_iteminfo_keeps_matching_download(self):
        with tempfile.TemporaryDirectory() as t:
            os.makedirs(f'{t}/pages/downloads')
            Path(f'{t}/pages/downloads/itemInfo.lua').write_text('x')
            Path(f'{t}/pages/downloads/itemInfo.lua.meta').write_text('variant: Renewal\nref: master\ncommit: abc123\n')
            r = sh('fetch_iteminfo.sh', env={'GAME_DATA': t})
            self.assertEqual(r.returncode, 0, r.stderr); self.assertIn('already downloaded', r.stdout); self.assertIn('abc123', r.stdout)

    def test_index_commands_report_missing_data(self):
        for script in ('parse_iteminfo.py', 'parse_sprites.py'):
            r = sh(script, '501', env={'GAME_DATA': '/nonexistent'})
            self.assertNotEqual(r.returncode, 0); self.assertTrue(r.stderr.startswith('error:'), r.stderr)

if __name__ == '__main__':
    unittest.main()
