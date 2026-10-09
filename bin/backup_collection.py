#!/usr/bin/env python3
"""Back up the git-ignored image collection and notes (images/ and notes/) into a timestamped .tar.gz.
  backup_collection.py [--dest DIR] [--keep N] [--also DIR ...] [--force] [--dry-run]
Default destination: BACKUP_DIR, or <data folder>/../game-data-backups. Each run checks the new archive against the files on disk
(same names and sizes), writes a .sha256 next to it, and keeps only the newest N archives (default 10). If nothing in images/ or notes/
changed since the newest archive, it does nothing unless --force. --also copies the new archive (and checksum) to more folders, such as a
cloud-synced folder or an external drive; a missing folder is reported, not created. The backups are not for git: they hold game images."""
import argparse, hashlib, os, shutil, subprocess, sys, tarfile, time
from pathlib import Path

def default_root(script=__file__):
    """GAME_DATA, else the repo this script is in. Inside a linked git worktree that is the main checkout, where images/ and notes/ live
    (a worktree has its own empty copies)."""
    if os.environ.get('GAME_DATA'): return os.environ['GAME_DATA']
    here = Path(script).resolve().parent.parent
    if (here / '.git').is_file():
        try:
            common = subprocess.run(['git', '-C', str(here), 'rev-parse', '--path-format=absolute', '--git-common-dir'], capture_output=True, text=True, check=True).stdout.strip()
            return str(Path(common).parent)
        except (OSError, subprocess.CalledProcessError): pass
    return str(here)

ROOT = default_root()
PREFIX, FOLDERS = 'game-data-tools-images-notes-', ('images', 'notes')

def die(msg): sys.exit(f'error: {msg}')

def files(root):
    out = {}
    for name in FOLDERS:
        base = Path(root) / name
        if base.is_dir():
            for p in sorted(base.rglob('*')):
                if p.is_file(): out[p.relative_to(root).as_posix()] = p.stat().st_size
    return out

def archives(dest):
    return sorted((p for p in Path(dest).glob(f'{PREFIX}*.tar.gz')), key=lambda p: (p.stat().st_mtime, p.name))   # oldest first, by time not name

def newest_change(root):
    return max((Path(root, rel).stat().st_mtime for rel in files(root)), default=0)

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''): h.update(chunk)
    return h.hexdigest()

def verify(archive, expected):
    with tarfile.open(archive, 'r:gz') as t: got = {m.name: m.size for m in t.getmembers() if m.isfile()}
    return got == expected

def main(argv=None, now=time.time):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dest', default=os.environ.get('BACKUP_DIR') or str(Path(ROOT).resolve().parent / 'game-data-backups'))
    ap.add_argument('--keep', type=int, default=10); ap.add_argument('--also', action='append', default=[])
    ap.add_argument('--force', action='store_true'); ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args(argv)
    if a.keep < 1: die('--keep must be at least 1')
    expected = files(ROOT)
    if not expected: die(f'nothing to back up: no files in {ROOT}/images or {ROOT}/notes')
    dest = Path(a.dest); existing = archives(dest) if dest.is_dir() else []
    if existing and not a.force and newest_change(ROOT) <= existing[-1].stat().st_mtime:
        print(f'nothing changed since {existing[-1].name}; no new backup (use --force to make one anyway)'); return 0
    stamp = time.strftime('%Y-%m-%d-%H%M%S', time.localtime(now()))
    target = dest / f'{PREFIX}{stamp}.tar.gz'
    print(f'{len(expected)} files ({sum(expected.values()) / 1e6:.1f} MB) -> {target}' + (' (dry run)' if a.dry_run else ''))
    if a.dry_run: return 0
    dest.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix('.tmp')
    with tarfile.open(tmp, 'w:gz') as t:
        for name in FOLDERS:
            if (Path(ROOT) / name).is_dir(): t.add(Path(ROOT) / name, arcname=name)
    if not verify(tmp, expected): tmp.unlink(); die('the new archive does not match the files on disk; nothing was kept')
    os.replace(tmp, target)
    digest = sha256(target); Path(f'{target}.sha256').write_text(f'{digest}  {target.name}\n')
    print(f'verified {len(expected)} files, sha256 {digest[:16]}...')
    for extra in a.also:
        if not Path(extra).is_dir(): print(f'warning: {extra} is not a folder; skipped', file=sys.stderr); continue
        shutil.copy2(target, extra); shutil.copy2(f'{target}.sha256', extra); print(f'copied to {extra}')
    old = archives(dest)
    for p in old[:-a.keep]:
        p.unlink(); Path(f'{p}.sha256').unlink(missing_ok=True); print(f'removed old backup {p.name}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
