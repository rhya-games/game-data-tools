"""Tests for bin/fetch_mob_sprites.py: id gathering from the wiki and the Endless Tower script, and downloads against a local HTTP server (no internet)."""
import contextlib, csv, io, os, sys, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from PIL import Image
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin'))
import fetch_mob_sprites as f

def gif_bytes(size=(40, 40), frames=1):
    b = io.BytesIO(); ims = [Image.new('RGB', size, (i * 80, 10, 10)) for i in range(frames)]
    ims[0].save(b, 'GIF', save_all=True, append_images=ims[1:]); return b.getvalue()

class Handler(BaseHTTPRequestHandler):
    routes, hits, flaky, agents = {}, {}, {}, []
    def do_GET(self):
        key = self.path.strip('/'); Handler.hits[key] = Handler.hits.get(key, 0) + 1; Handler.agents.append(self.headers.get('User-Agent'))
        if Handler.hits[key] <= Handler.flaky.get(key, 0): code, body = 503, b''
        else: code, body = Handler.routes.get(key, (404, b''))
        self.send_response(code); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass

class FetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(('127.0.0.1', 0), Handler)
        cls.first = f'http://127.0.0.1:{cls.srv.server_port}/a/{{}}.gif'; cls.second = f'http://127.0.0.1:{cls.srv.server_port}/b/{{}}.gif'
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown(); cls.srv.server_close()
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.out = f'{self.tmp.name}/mobs'
        Handler.routes, Handler.hits, Handler.flaky, Handler.agents = {}, {}, {}, []
    def tearDown(self): self.tmp.cleanup()
    def run_fetch(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = f.main(['--out', self.out, '--source', self.first, '--source', self.second, '--delay', '0', *map(str, args)], sleep=lambda s: None)
        return code, out.getvalue(), err.getvalue()

    def test_saves_animated_gif_unchanged_and_records_source(self):
        pic = gif_bytes((30, 20), frames=3); Handler.routes = {'a/1002.gif': (200, pic)}
        code, out, _ = self.run_fetch(1002); self.assertEqual(code, 0); self.assertIn('saved 1; not on the sites 0', out)
        self.assertEqual(Path(f'{self.out}/mob1002.gif').read_bytes(), pic)
        with open(f'{self.out}/manifest.csv', encoding='utf-8') as fh: rows = list(csv.DictReader(fh))
        self.assertEqual((rows[0]['id'], rows[0]['size'], rows[0]['notes']), ('1002', '30x20', 'downloaded; animated, 3 frames'))
        self.assertTrue(rows[0]['source'].endswith('/a/1002.gif')); self.assertTrue(all('game-data-tools' in (a or '') for a in Handler.agents))

    def test_a_404_falls_through_to_the_next_source_and_unknown_ids_are_listed(self):
        Handler.routes = {'b/20575.gif': (200, gif_bytes())}
        code, out, _ = self.run_fetch(20575, 99); self.assertEqual(code, 0)
        self.assertIn('saved 1; not on the sites 1', out); self.assertTrue(os.path.exists(f'{self.out}/mob20575.gif'))
        self.assertEqual(Path(f'{self.out}/not-found.txt').read_text().split(), ['99'])
        with open(f'{self.out}/manifest.csv', encoding='utf-8') as fh: self.assertTrue(next(csv.DictReader(fh))['source'].endswith('/b/20575.gif'))

    def test_not_an_image_is_rejected_and_the_next_source_is_tried(self):
        Handler.routes = {'a/1.gif': (200, b'<html>blocked</html>'), 'b/1.gif': (200, gif_bytes())}
        code, out, err = self.run_fetch(1); self.assertEqual(code, 0)
        self.assertIn('rejected 1', err); self.assertIn('saved 1', out)

    def test_existing_pictures_are_never_replaced(self):
        os.makedirs(self.out); Path(f'{self.out}/mob1002.gif').write_bytes(b'mine'); Path(f'{self.out}/mob1003.png').write_bytes(b'png')
        Handler.routes = {'a/1002.gif': (200, gif_bytes()), 'a/1003.gif': (200, gif_bytes())}
        _, out, _ = self.run_fetch(1002, 1003); self.assertIn('2 already in the collection, 0 to fetch', out)
        self.assertEqual(Path(f'{self.out}/mob1002.gif').read_bytes(), b'mine'); self.assertEqual(Handler.hits, {})

    def test_transient_errors_are_retried(self):
        Handler.routes = {'a/7.gif': (200, gif_bytes())}; Handler.flaky = {'a/7.gif': 2}
        code, out, _ = self.run_fetch(7); self.assertEqual(code, 0); self.assertIn('saved 1', out); self.assertEqual(Handler.hits['a/7.gif'], 3)

    def test_persistent_errors_stop_the_run_and_keep_finished_pictures(self):
        Handler.routes = {'a/1.gif': (200, gif_bytes()), 'a/3.gif': (200, gif_bytes())}; Handler.flaky = {'a/2.gif': 99}
        code, _, err = self.run_fetch(1, 2, 3); self.assertEqual(code, 1); self.assertIn('stopping after 1 pictures', err)
        self.assertTrue(os.path.exists(f'{self.out}/mob1.gif')); self.assertNotIn('a/3.gif', Handler.hits)

    def test_dry_run_downloads_nothing(self):
        code, out, _ = self.run_fetch(1, 2, '--dry-run'); self.assertEqual(code, 0)
        self.assertIn('2 to fetch (dry run)', out); self.assertEqual(Handler.hits, {}); self.assertFalse(os.path.exists(self.out))

class IdSourceTests(unittest.TestCase):
    NAMES = {1002: 'Poring', 1119: 'Frilldora', 1273: 'Orc Lady', 1478: 'Rideword', 1625: 'Porcellio', 1646: 'Lord Knight Seyren', 1871: 'Falling Bishop', 1713: 'Acidus'}

    def docs(self, files):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        for name, text in files.items():
            p = Path(tmp.name) / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding='utf-8')
        return tmp.name

    def test_mi_macro_prose_and_monster_table(self):
        d = self.docs({'a.md': '| Acidus | `@mi 1713`{ .copy } |\n\nWatch out for Frilldoras (`1119`) and Orc Ladies (`1273`).\n\n'
                               '| Monster | ID | Original |\n|-|-|-|\n| Fallen Bishop | `1871` | – |\n| Lord Knight Seyren | `1646` | Dragon Slayer (`1166`): 100% |\n'})
        self.assertEqual(f.wiki_ids(d, self.NAMES), {1713, 1119, 1273, 1871, 1646})

    def test_item_ids_with_the_same_look_are_ignored(self):
        d = self.docs({'a.md': 'The weapon Ahlspiess (`1478`) is cheap; Healing Staff (`1625`) drops.\n\n'
                               '| Item | ID |\n|-|-|\n| Healing Staff | `1625` |\n'})
        self.assertEqual(f.wiki_ids(d, self.NAMES), set())

    def test_patch_notes_and_dev_pages_are_skipped(self):
        d = self.docs({'all-patch-notes.md': '`@mi 1002`', 'dev/x.md': '`@mi 1002`', 'real.md': 'Poring (`1002`)'})
        self.assertEqual(f.wiki_ids(d, self.NAMES), {1002})
        d = self.docs({'all-patch-notes/x.md': '@mi 1002'}); self.assertEqual(f.wiki_ids(d, self.NAMES), set())

    def test_tower_script_ids_come_from_spawn_lines_only(self):
        d = self.docs({'t.txt': 'prontera,1,1,0\tscript\tX\t1,{\n\tareamonster .@map$,7,351,17,387,"Poring",1002,5,.@label$;\n'
                                '\tmonster "1@tower",50,50,"Acidus",1713,1,"l";\n\tmes "Wait, \\"x\\",1478,1";\n\tif (checkweight(1201,1) == 0) end;\n}\n'})
        self.assertEqual(f.tower_ids(f'{d}/t.txt', self.NAMES), {1002, 1713})

if __name__ == '__main__':
    unittest.main()
