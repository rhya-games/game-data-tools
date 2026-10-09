"""Tests for bin/fetch_item_icons.py against a local HTTP server (no internet)."""
import contextlib, csv, io, os, sys, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from PIL import Image
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin'))
import fetch_item_icons as f

def gif_bytes(size=(24, 24)):
    b = io.BytesIO(); Image.new('RGB', size, (9, 9, 9)).save(b, 'GIF'); return b.getvalue()

class Handler(BaseHTTPRequestHandler):
    routes, hits, flaky, agents = {}, {}, {}, []
    def do_GET(self):
        i = self.path.strip('/').split('.')[0]; Handler.hits[i] = Handler.hits.get(i, 0) + 1; Handler.agents.append(self.headers.get('User-Agent'))
        if Handler.hits[i] <= Handler.flaky.get(i, 0): code, body = 503, b''
        else: code, body = Handler.routes.get(i, (404, b''))
        self.send_response(code); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass

class FetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(('127.0.0.1', 0), Handler); cls.url = f'http://127.0.0.1:{cls.srv.server_port}/{{}}.gif'
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown(); cls.srv.server_close()
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.out = f'{self.tmp.name}/items'; os.makedirs(self.out)
        Handler.routes, Handler.hits, Handler.flaky, Handler.agents = {}, {}, {}, []
    def tearDown(self): self.tmp.cleanup()
    def run_fetch(self, ids, *extra):
        Path(f'{self.out}/missing.txt').write_text('\n'.join(map(str, ids)))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = f.main(['--out', self.out, '--base-url', self.url, '--delay', '0', *extra], sleep=lambda s: None)
        return code, out.getvalue(), err.getvalue()

    def test_saves_valid_icons_records_404_and_sends_user_agent(self):
        Handler.routes = {'501': (200, gif_bytes())}
        code, out, _ = self.run_fetch([501, 502])
        self.assertEqual(code, 0); self.assertIn('saved 1; not on the site 1', out)
        self.assertEqual(Path(f'{self.out}/item501.gif').read_bytes(), gif_bytes()); self.assertFalse(os.path.exists(f'{self.out}/item502.gif'))
        self.assertEqual(Path(f'{self.out}/not-found.txt').read_text().split(), ['502'])
        with open(f'{self.out}/manifest.csv', encoding='utf-8') as fh: rows = list(csv.DictReader(fh))
        self.assertEqual((rows[0]['id'], rows[0]['notes']), ('501', 'downloaded')); self.assertTrue(all('game-data-tools' in (a or '') for a in Handler.agents))

    def test_wrong_size_or_not_an_image_is_rejected(self):
        Handler.routes = {'1': (200, gif_bytes((40, 40))), '2': (200, b'<html>blocked</html>')}
        code, out, err = self.run_fetch([1, 2]); self.assertEqual(code, 0)
        self.assertIn('rejected 1', err); self.assertIn('rejected 2', err); self.assertEqual(os.listdir(self.out).count('item1.gif'), 0)

    def test_existing_icons_are_never_replaced(self):
        Path(f'{self.out}/item501.gif').write_bytes(b'mine'); Handler.routes = {'501': (200, gif_bytes())}
        _, out, _ = self.run_fetch([501]); self.assertIn('1 already in the collection, 0 to fetch', out)
        self.assertEqual(Path(f'{self.out}/item501.gif').read_bytes(), b'mine'); self.assertNotIn('501', Handler.hits)

    def test_transient_errors_are_retried(self):
        Handler.routes = {'501': (200, gif_bytes())}; Handler.flaky = {'501': 2}
        code, out, _ = self.run_fetch([501]); self.assertEqual(code, 0); self.assertIn('saved 1', out); self.assertEqual(Handler.hits['501'], 3)

    def test_persistent_errors_stop_the_run_and_keep_finished_icons(self):
        Handler.routes = {'1': (200, gif_bytes()), '3': (200, gif_bytes())}; Handler.flaky = {'2': 99}
        code, _, err = self.run_fetch([1, 2, 3]); self.assertEqual(code, 1); self.assertIn('stopping after 1 icons', err)
        self.assertTrue(os.path.exists(f'{self.out}/item1.gif')); self.assertNotIn('3', Handler.hits)

    def test_the_sites_no_image_placeholder_counts_as_not_found(self):
        ph = gif_bytes(); other = io.BytesIO(); Image.new('RGB', (24, 24), (200, 0, 0)).save(other, 'GIF')
        Handler.routes = {'99999999': (200, ph), '1': (200, ph), '2': (200, other.getvalue())}
        code, out, _ = self.run_fetch([1, 2]); self.assertEqual(code, 0)
        self.assertIn('placeholder for unknown ids: detected', out); self.assertIn('saved 1; not on the site 1', out)
        self.assertFalse(os.path.exists(f'{self.out}/item1.gif')); self.assertTrue(os.path.exists(f'{self.out}/item2.gif'))
        self.assertEqual(Path(f'{self.out}/not-found.txt').read_text().split(), ['1'])

    def test_png_icons_are_converted_and_the_big_placeholder_is_not_found(self):
        b = io.BytesIO(); Image.new('RGBA', (24, 24), (10, 200, 10, 255)).save(b, 'PNG'); big = io.BytesIO(); Image.new('RGBA', (57, 57), (0, 0, 0, 255)).save(big, 'PNG')
        Handler.routes = {'99999999': (200, big.getvalue()), '7': (200, b.getvalue()), '8': (200, big.getvalue())}
        code, out, err = self.run_fetch([7, 8]); self.assertEqual(code, 0)
        self.assertIn('saved 1; not on the site 1', out); self.assertEqual(err, '')
        with Image.open(f'{self.out}/item7.gif') as g: self.assertEqual((g.format, g.size), ('GIF', (24, 24)))
        self.assertFalse(os.path.exists(f'{self.out}/item8.gif'))
        with open(f'{self.out}/manifest.csv', encoding='utf-8') as fh: self.assertIn('converted from png', fh.read())

    def test_limit_dry_run_and_missing_input(self):
        Handler.routes = {str(i): (200, gif_bytes()) for i in (1, 2, 3)}
        self.run_fetch([1, 2, 3], '--limit', '2'); self.assertEqual(sorted(x for x in os.listdir(self.out) if x.endswith('.gif')), ['item1.gif', 'item2.gif'])
        before = dict(Handler.hits); self.run_fetch([4, 5], '--dry-run'); self.assertEqual(Handler.hits, before)
        with self.assertRaises(SystemExit): f.main(['--out', f'{self.tmp.name}/none'])

if __name__ == '__main__':
    unittest.main()
