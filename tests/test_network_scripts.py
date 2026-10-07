"""Tests for fetch_sprites.sh and fetch_iteminfo.sh with a fake curl on PATH, so no network is used.
The fake curl serves URLs from a routes table: {url: {"status": 200, "body": "...", "flaky": N}} (flaky = fail with 503 that many times first).
Unlisted URLs return 404."""
import json, os, stat, subprocess, tempfile, unittest
from pathlib import Path
BIN = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'bin'))

FAKE_CURL = r'''#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
out = a[a.index('-o') + 1] if '-o' in a else None
fmt = a[a.index('-w') + 1] if '-w' in a else None
fail_on_error = any(x.startswith('-') and not x.startswith('--') and 'f' in x[1:] for x in a if x not in ('-o', '-w', '-A'))
url = next(x for x in a if x.startswith('http'))
routes = json.load(open(os.environ['FAKE_ROUTES']))
r = routes.get(url, {'status': 404, 'body': ''})
counter = os.environ['FAKE_ROUTES'] + '.count'
seen = json.load(open(counter)) if os.path.exists(counter) else {}
seen[url] = seen.get(url, 0) + 1
json.dump(seen, open(counter, 'w'))
status = 503 if seen[url] <= r.get('flaky', 0) else r['status']
if status == 200:
    if out: open(out, 'w').write(r['body'])
    else: sys.stdout.write(r['body'])
if fmt: sys.stdout.write(str(status))
sys.exit(22 if fail_on_error and status >= 400 else 0)
'''
NPC = '<div class="npc"><span>ID: %d</span></div></div>'
VIEW = 'https://nn.ai4rei.net/dev/viewlist/'
def npc(n): return f'https://nn.ai4rei.net/dev/npclist/?qq={n}'
DOTALUX = 'https://dotalux.com/ro/npclist/'
API = 'https://api.github.com/repos/llchrisll/ROenglishRE/commits/'
RAW = 'https://raw.githubusercontent.com/llchrisll/ROenglishRE/%s/Translation/%s/SystemEN/LuaFiles514/itemInfo.lua'

class FakeNetwork(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); t = self.tmp.name
        os.makedirs(f'{t}/fakebin')
        curl = Path(f'{t}/fakebin/curl'); curl.write_text(FAKE_CURL); curl.chmod(curl.stat().st_mode | stat.S_IXUSR)
        self.routes = {}
        self.env = {**os.environ, 'PATH': f'{t}/fakebin:{os.environ["PATH"]}', 'FAKE_ROUTES': f'{t}/routes.json', 'GAME_DATA': f'{t}/data', 'FETCH_RETRY_DELAY': '0'}

    def tearDown(self): self.tmp.cleanup()

    def run_script(self, script, **extra):
        Path(self.env['FAKE_ROUTES']).write_text(json.dumps(self.routes))
        return subprocess.run([f'{BIN}/{script}'], capture_output=True, text=True, env={**self.env, **extra})

    def saved(self): return sorted(os.listdir(f'{self.tmp.name}/data/pages/nn.ai4rei.net'))

def ok(body, **kw): return {'status': 200, 'body': body, **kw}

class FetchSprites(FakeNetwork):
    def base(self, pages=2):
        self.routes[VIEW] = ok('<td><a name="id1"></a></td>')
        for n in range(pages): self.routes[npc(n)] = ok(NPC % (1000 + n))

    def test_saves_pages_until_404(self):
        self.base(); self.routes[DOTALUX] = ok("overlib('45 : x')")
        r = self.run_script('fetch_sprites.sh')
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn('saved 2 npclist pages', r.stdout)
        self.assertEqual([f for f in self.saved() if not f.endswith('.meta')], ['dev_npclist_qq_0', 'dev_npclist_qq_1', 'dev_viewlist'])
        self.assertTrue(os.path.isfile(f'{self.tmp.name}/data/pages/dotalux.com/ro_npclist'))

    def test_stops_at_empty_page_and_removes_it(self):
        self.base(); self.routes[npc(2)] = ok('<html>no entries</html>')
        r = self.run_script('fetch_sprites.sh')
        self.assertEqual(r.returncode, 0, r.stderr); self.assertNotIn('dev_npclist_qq_2', self.saved())

    def test_retries_a_transient_failure(self):
        self.base(); self.routes[npc(1)]['flaky'] = 2
        r = self.run_script('fetch_sprites.sh')
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn('saved 2 npclist pages', r.stdout)

    def test_persistent_failure_is_an_error_not_a_short_run(self):
        self.base(); self.routes[npc(1)]['flaky'] = 99
        r = self.run_script('fetch_sprites.sh')
        self.assertNotEqual(r.returncode, 0); self.assertIn('page 1 failed after retries', r.stderr)

    def test_missing_dotalux_is_not_fatal(self):
        self.base()
        r = self.run_script('fetch_sprites.sh')
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn('optional', r.stderr)

    def test_no_pages_at_all_is_an_error(self):
        self.routes[VIEW] = ok('x')
        r = self.run_script('fetch_sprites.sh')
        self.assertNotEqual(r.returncode, 0); self.assertIn('No npclist pages saved', r.stderr)

class FetchIteminfo(FakeNetwork):
    SHA = 'a' * 40
    def meta(self): return Path(f'{self.tmp.name}/data/pages/downloads/itemInfo.lua.meta').read_text()

    def test_downloads_pinned_commit_and_records_meta(self):
        self.routes[API + 'master'] = ok(json.dumps({'sha': self.SHA}))
        self.routes[RAW % (self.SHA, 'Renewal')] = ok('tbl = { [1] = { identifiedDisplayName = "X" } }')
        r = self.run_script('fetch_iteminfo.sh')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f'commit: {self.SHA}', self.meta()); self.assertIn('variant: Renewal', self.meta())
        self.assertIn('identifiedDisplayName', Path(f'{self.tmp.name}/data/pages/downloads/itemInfo.lua').read_text())

    def test_pre_renewal_variant_and_ref(self):
        self.routes[API + 'v1'] = ok(json.dumps({'sha': self.SHA}))
        self.routes[RAW % (self.SHA, 'Pre-Renewal')] = ok('identifiedDisplayName')
        r = self.run_script('fetch_iteminfo.sh', ITEMINFO_VARIANT='Pre-Renewal', ITEMINFO_REF='v1')
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn('ref: v1', self.meta())

    def test_second_run_keeps_file_and_variant_change_redownloads(self):
        self.routes[API + 'master'] = ok(json.dumps({'sha': self.SHA}))
        self.routes[RAW % (self.SHA, 'Renewal')] = ok('identifiedDisplayName')
        self.routes[RAW % (self.SHA, 'Pre-Renewal')] = ok('identifiedDisplayName')
        self.run_script('fetch_iteminfo.sh')
        again = self.run_script('fetch_iteminfo.sh')
        self.assertIn('already downloaded', again.stdout)
        self.run_script('fetch_iteminfo.sh', ITEMINFO_VARIANT='Pre-Renewal')
        self.assertIn('variant: Pre-Renewal', self.meta())

    def test_rejects_non_item_file_and_keeps_old_one(self):
        self.routes[API + 'master'] = ok(json.dumps({'sha': self.SHA}))
        self.routes[RAW % (self.SHA, 'Renewal')] = ok('<html>rate limited</html>')
        r = self.run_script('fetch_iteminfo.sh')
        self.assertNotEqual(r.returncode, 0); self.assertIn('not an item file', r.stderr)
        self.assertFalse(os.path.exists(f'{self.tmp.name}/data/pages/downloads/itemInfo.lua'))

    def test_api_failure_is_reported(self):
        r = self.run_script('fetch_iteminfo.sh')
        self.assertNotEqual(r.returncode, 0); self.assertIn('Could not resolve', r.stderr)

if __name__ == '__main__':
    unittest.main()
