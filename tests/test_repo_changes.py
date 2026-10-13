"""Tests for bin/repo_changes.py against throwaway git repositories."""
import contextlib, io, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin'))
import repo_changes as r

def git(p, *a): subprocess.run(['git', '-C', str(p), '-c', 'user.name=t', '-c', 'user.email=t@t', *a], check=True, capture_output=True)

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); t = Path(self.tmp.name)
        self.paths = {k: t / k for k in ('docs', 'loot', 'tools')}
        for p in self.paths.values():
            p.mkdir(); subprocess.run(['git', 'init', '-q', '-b', 'main', str(p)], check=True)
            (p / 'README').write_text('x'); git(p, 'add', '.'); git(p, 'commit', '-qm', 'init')
        (t / 'tools' / 'images' / 'items').mkdir(parents=True); (t / 'tools' / 'images' / 'mobs').mkdir()
        self.saved = (r.REPOS, r.ROOT); r.REPOS = self.paths; r.ROOT = str(t / 'tools')
        self.notes = t / 'tools' / 'notes'

    def tearDown(self): r.REPOS, r.ROOT = self.saved; self.tmp.cleanup()

    def run_tool(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out): code = r.main(list(args))
        self.assertEqual(code, 0); return out.getvalue()

    def commit(self, repo, files):
        p = self.paths[repo]
        for name, text in files.items():
            (p / name).parent.mkdir(parents=True, exist_ok=True); (p / name).write_text(text)
        git(p, 'add', '.'); git(p, 'commit', '-qm', 'change')

    def test_first_run_records_baseline_only(self):
        self.assertIn('Baseline recorded', self.run_tool())
        self.assertEqual(set(json.loads((self.notes / 'cross-repo-state.json').read_text())), {'docs', 'loot', 'tools'})

    def test_no_change_says_nothing_to_do(self):
        self.run_tool(); self.assertIn('Nothing to do.', self.run_tool())

    def test_changes_trigger_follow_ups_and_list_ids_without_pictures(self):
        self.run_tool()
        (Path(r.ROOT) / 'images' / 'items' / 'item501.gif').write_bytes(b'x')
        self.commit('docs', {'docs/patch-notes/2026/patches01012026.md': '- `@mi 1002` and `@ii 501` and `@ii 502`\n', 'docs/monster-changes.md': '| Sting | `1207` |\n'})
        self.commit('loot', {'src/data/loot.json': '[{"itemId": 7000}]'})
        out = self.run_tool()
        self.assertIn('New patch notes', out); self.assertIn('uaRO value changes', out); self.assertIn('Loot sheet items changed', out)
        self.assertIn('monsters (bin/fetch_mob_sprites.py ID ...): 1002', out); self.assertIn('fetch_item_icons.py --ids FILE): 502 7000', out)
        self.assertNotIn(' 501', out.split('no picture yet')[1]); self.assertIn('1207', out.split('no picture yet')[1])
        self.assertTrue((self.notes / 'cross-repo-changes.md').exists())

    def test_report_repeats_until_acknowledged(self):
        self.run_tool(); self.commit('docs', {'docs/monster-changes.md': 'x'})
        self.assertIn('uaRO value changes', self.run_tool()); self.assertIn('uaRO value changes', self.run_tool())
        self.assertIn('Baselines moved', self.run_tool('--ack')); self.assertIn('Nothing to do.', self.run_tool())

    def test_added_only_rule_ignores_edits_to_existing_patch_notes(self):
        self.commit('docs', {'docs/patch-notes/2026/p.md': 'a'}); self.run_tool()
        self.commit('docs', {'docs/patch-notes/2026/p.md': 'b'})
        self.assertNotIn('New patch notes', self.run_tool())

    def test_since_compares_against_given_revision_without_saving(self):
        self.run_tool(); self.commit('tools', {'data/uaro-quests.json': '{}'}); self.run_tool('--ack')
        out = self.run_tool('--since', 'tools=HEAD~1'); self.assertIn('Quest data changed', out)
        self.assertIn('Nothing to do.', self.run_tool())

if __name__ == '__main__':
    unittest.main()
