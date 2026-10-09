"""Tests for bin/backup_collection.py."""
import contextlib, io, os, sys, tarfile, tempfile, time, unittest
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin'))
import backup_collection as b

class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); t = self.t = self.tmp.name
        Path(f'{t}/data/images/items').mkdir(parents=True); Path(f'{t}/data/notes').mkdir(); Path(f'{t}/data/local').mkdir()
        Path(f'{t}/data/images/items/item1.gif').write_bytes(b'GIF' * 10); Path(f'{t}/data/notes/list.csv').write_text('id\n1\n'); Path(f'{t}/data/local/tool.py').write_text('x')
        self.old, b.ROOT = b.ROOT, f'{t}/data'; self.dest = f'{t}/backups'
    def tearDown(self): b.ROOT = self.old; self.tmp.cleanup()
    def run_backup(self, *extra, now=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try: code = b.main(['--dest', self.dest, *extra], **({'now': now} if now else {}))
            except SystemExit as e: code = e.code
        return code, out.getvalue(), err.getvalue()
    def made(self): return sorted(p.name for p in Path(self.dest).glob('*.tar.gz'))

    def test_creates_a_verified_archive_with_checksum(self):
        code, out, _ = self.run_backup(); self.assertEqual(code, 0); self.assertIn('verified 2 files', out)
        (name,) = self.made()
        with tarfile.open(f'{self.dest}/{name}') as t: self.assertEqual(sorted(m.name for m in t.getmembers() if m.isfile()), ['images/items/item1.gif', 'notes/list.csv'])   # local/ is not included
        self.assertEqual(b.sha256(f'{self.dest}/{name}'), Path(f'{self.dest}/{name}.sha256').read_text().split()[0])

    def test_unchanged_files_make_no_new_backup_unless_forced(self):
        self.run_backup(now=lambda: 1_000_000_000)
        code, out, _ = self.run_backup(now=lambda: 1_000_000_100); self.assertIn('nothing changed', out); self.assertEqual(len(self.made()), 1)
        self.run_backup('--force', now=lambda: 1_000_000_200); self.assertEqual(len(self.made()), 2)

    def test_a_changed_file_triggers_a_new_backup(self):
        self.run_backup(now=lambda: 1_000_000_000)
        newer = time.time() + 100; os.utime(f'{self.t}/data/notes/list.csv', (newer, newer))
        self.run_backup(now=lambda: 1_000_000_100); self.assertEqual(len(self.made()), 2)

    def test_keeps_only_the_newest_n_and_removes_their_checksums(self):
        for k in range(4): self.run_backup('--force', '--keep', '2', now=lambda k=k: 1_000_000_000 + k * 1000)
        self.assertEqual(len(self.made()), 2); self.assertEqual(len(list(Path(self.dest).glob('*.sha256'))), 2)
        Path(f'{self.dest}/unrelated.tar.gz').write_text('keep me'); self.run_backup('--force', '--keep', '1'); self.assertTrue(os.path.exists(f'{self.dest}/unrelated.tar.gz'))

    def test_also_copies_to_other_folders_and_warns_about_missing_ones(self):
        os.makedirs(f'{self.t}/usb')
        code, out, err = self.run_backup('--also', f'{self.t}/usb', '--also', f'{self.t}/missing')
        self.assertEqual(code, 0); self.assertEqual(len(list(Path(f'{self.t}/usb').glob('*.tar.gz'))), 1); self.assertTrue(list(Path(f'{self.t}/usb').glob('*.sha256')))
        self.assertIn('is not a folder', err); self.assertFalse(os.path.exists(f'{self.t}/missing'))

    def test_dry_run_writes_nothing_and_empty_collection_errors(self):
        self.run_backup('--dry-run'); self.assertFalse(os.path.exists(self.dest))
        for f in list(Path(f'{self.t}/data/images').rglob('*.gif')) + [Path(f'{self.t}/data/notes/list.csv')]: f.unlink()
        code, _, _ = self.run_backup(); self.assertIn('nothing to back up', str(code))

    def test_newest_and_oldest_are_judged_by_time_not_by_file_name(self):
        os.makedirs(self.dest)
        old, new = Path(self.dest) / f'{b.PREFIX}2026-10-09.tar.gz', Path(self.dest) / f'{b.PREFIX}2026-10-09-134702.tar.gz'   # the older one sorts last by name
        for p, ts in ((old, 1_000_000_000), (new, 1_500_000_000)): p.write_bytes(b'x'); os.utime(p, (ts, ts))
        self.assertEqual([p.name for p in b.archives(self.dest)], [old.name, new.name])
        self.run_backup('--force', '--keep', '1'); self.assertEqual(len(self.made()), 1); self.assertFalse(old.exists() or new.exists())

    def test_a_linked_worktree_uses_the_main_checkout(self):
        import subprocess
        main = Path(self.t) / 'main'; (main / 'bin').mkdir(parents=True)
        git = lambda *a, cwd=main: subprocess.run(['git', *a], cwd=cwd, check=True, capture_output=True)
        git('init', '-q'); git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'x')
        wt = Path(self.t) / 'wt'; git('worktree', 'add', '-q', str(wt))
        (wt / 'bin').mkdir(exist_ok=True); (wt / 'bin' / 'backup_collection.py').write_text('')
        (main / 'bin' / 'backup_collection.py').write_text('')
        env, old = os.environ.pop('GAME_DATA', None), None
        try:
            self.assertEqual(Path(b.default_root(str(wt / 'bin' / 'backup_collection.py'))).resolve(), main.resolve())
            self.assertEqual(Path(b.default_root(str(main / 'bin' / 'backup_collection.py'))).resolve(), main.resolve())
            os.environ['GAME_DATA'] = '/custom'; self.assertEqual(b.default_root(str(wt / 'bin' / 'backup_collection.py')), '/custom')
        finally:
            os.environ.pop('GAME_DATA', None)
            if env is not None: os.environ['GAME_DATA'] = env

    def test_bad_keep_value_is_refused(self):
        code, _, _ = self.run_backup('--keep', '0'); self.assertIn('--keep', str(code))

if __name__ == '__main__':
    unittest.main()
