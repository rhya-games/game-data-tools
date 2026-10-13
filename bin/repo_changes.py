#!/usr/bin/env python3
"""Say what changed in the uaRO repos since you last looked, and what that means for the other repos.
  repo_changes.py [--ack] [--since REPO=REV ...] [--out FILE]
Tracks the tip of main in three repos (override the paths with UARO_DOCS, UARO_LOOT_SHEET and GAME_DATA):
  docs   ~/Projects/uaro-docs          the wiki pages (docs/), patch notes, images
  loot   ~/Projects/uaro-loot-sheet    src/data/loot.json and the overrides
  tools  $GAME_DATA                    data/uaro-quests.json and the scripts
The first run only records where each repo is. Later runs compare against that, list the changed files that matter, apply the follow-up
rules below, and list item and monster ids the changes mention that have no picture yet. The report is printed and written to
<data folder>/notes/cross-repo-changes.md. Nothing moves the baseline except --ack, so the report stays until you say you handled it.
  --ack            move every baseline to the current tip (after you have dealt with the report)
  --since R=REV    compare repo R (docs, loot, tools) against REV for this run instead of its baseline (does not save)
State lives in <data folder>/notes/cross-repo-state.json. Both files are in the git-ignored notes/ folder."""
import argparse, json, os, re, subprocess, sys
from pathlib import Path
ROOT = os.environ.get('GAME_DATA', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOME = Path.home() / 'Projects'
REPOS = {'docs': Path(os.environ.get('UARO_DOCS', HOME / 'uaro-docs')),
         'loot': Path(os.environ.get('UARO_LOOT_SHEET', HOME / 'uaro-loot-sheet')),
         'tools': Path(ROOT)}
BRANCH = 'main'

# (repo, path regex, only for added files, what it means for the other repos)
RULES = [
    ('docs', r'^docs/patch-notes/.*\.md$', True, 'New patch notes: read them for item, monster, drop or quest changes that the loot sheet (loot.json, uaro-overrides.json) or data/uaro-quests.json should reflect.'),
    ('docs', r'^docs/(monster|item|map)-changes\.md$', False, 'uaRO value changes: check loot sheet uaro-overrides.json and compare with bin/compare_item.py or compare_mob.py.'),
    ('docs', r'^docs/(repeatable-quests|dimonka-headgear-quest|king-frog-hat|expanded-class-weapons|el-dicastes)\.md$', False, 'A quest page the quest import reads: run bin/import_wiki_quests.py --wiki <docs> --dry-run.'),
    ('docs', r'^docs/img/', False, 'Wiki images: bin/build_item_images.py can ingest new item and monster pictures into the collection.'),
    ('loot', r'^src/data/loot\.json$', False, 'Loot sheet items changed: run bin/fetch_item_icons.py for new ids, then npm run sync:icons there; check the wiki mentions the same values.'),
    ('loot', r'^src/data/uaro-overrides\.json$', False, 'uaRO overrides changed: the wiki item-changes and monster-changes pages may need the same change.'),
    ('tools', r'^data/uaro-quests\.json$', False, 'Quest data changed: wiki quest pages and the loot sheet quest uses may need updating.'),
]
ID_PATTERNS = [('mob', re.compile(r'@mi\s*(\d{3,6})')), ('item', re.compile(r'@ii\s*(\d{3,6})')),
               ('either', re.compile(r'`(\d{3,6})`')), ('item', re.compile(r'"itemId":\s*(\d{3,7})'))]

def die(msg): sys.exit(f'error: {msg}')

def git(repo, *args):
    r = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def tip(repo):
    code, out, err = git(repo, 'rev-parse', '--verify', '--quiet', BRANCH)
    return out if code == 0 else None

def changes(repo, old, new):
    """({path: status letter}, added lines) between two commits, or None when old is not an ancestor of new."""
    if git(repo, 'merge-base', '--is-ancestor', old, new)[0] != 0: return None
    _, names, _ = git(repo, 'diff', '--name-status', '--no-renames', f'{old}..{new}')
    files = {}
    for line in names.splitlines():
        st, _, path = line.partition('\t'); files[path] = st[0]
    _, patch, _ = git(repo, 'diff', '-U0', '--no-renames', f'{old}..{new}', '--', '*.md', '*.json')
    added = [l[1:] for l in patch.splitlines() if l.startswith('+') and not l.startswith('+++')]
    return files, added

def mentioned_ids(added):
    out = {'item': set(), 'mob': set(), 'either': set()}
    for line in added:
        for kind, pat in ID_PATTERNS: out[kind] |= {int(x) for x in pat.findall(line)}
    return out

def missing_pictures(ids):
    """ids with no collected picture: items need item<ID>.gif, monsters mob<ID>.gif|png, ambiguous ids either."""
    img = Path(ROOT) / 'images'
    item = lambda i: (img / 'items' / f'item{i}.gif').exists()
    mob = lambda i: any((img / 'mobs' / f'mob{i}.{e}').exists() for e in ('gif', 'png'))
    return {'items': sorted(i for i in ids['item'] if not item(i)),
            'monsters': sorted(i for i in ids['mob'] if not mob(i)),
            'unclear': sorted(i for i in ids['either'] if not item(i) and not mob(i) and i not in ids['item'] | ids['mob'])}

def follow_ups(repo, files):
    out = []
    for r, pat, added_only, text in RULES:
        if r != repo: continue
        hit = [p for p, st in files.items() if re.search(pat, p) and (st == 'A' or not added_only)]
        if hit: out.append((text, hit))
    return out

def report(old_tips, new_tips, since):
    lines, any_change = [f'# Cross-repo changes ({len(new_tips)} repos)\n'], False
    ids = {'item': set(), 'mob': set(), 'either': set()}
    for repo in REPOS:
        old, new = since.get(repo) or old_tips.get(repo), new_tips.get(repo)
        lines.append(f'## {repo}: {REPOS[repo]}')
        if not new: lines.append(f'- no `{BRANCH}` branch found\n'); continue
        if not old or old == new: lines.append(f'- no change since {new[:7]}\n'); continue
        diff = changes(REPOS[repo], old, new)
        if diff is None: lines.append(f'- {old[:7]} is not an ancestor of {new[:7]} (history rewritten?); compare by hand\n'); any_change = True; continue
        files, added = diff
        any_change = True
        lines.append(f'- {old[:7]} -> {new[:7]}, {len(files)} files changed')
        for text, hit in follow_ups(repo, files):
            lines.append(f'- TODO: {text}'); lines += [f'    - {p}' for p in sorted(hit)[:8]] + ([f'    - ... and {len(hit) - 8} more'] if len(hit) > 8 else [])
        for k, v in mentioned_ids(added).items(): ids[k] |= v
        lines.append('')
    miss = missing_pictures(ids)
    if any(miss.values()):
        lines.append('## Ids mentioned in the changes with no picture yet')
        for k, label in (('items', 'items (bin/fetch_item_icons.py --ids FILE)'), ('monsters', 'monsters (bin/fetch_mob_sprites.py ID ...)'), ('unclear', 'item or monster, not clear (check which)')):
            if miss[k]: lines.append(f'- {label}: ' + ' '.join(map(str, miss[k])))
        lines.append('')
    if not any_change: lines.append('Nothing to do.')
    return '\n'.join(lines).rstrip() + '\n'

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ack', action='store_true'); ap.add_argument('--since', action='append', default=[])
    ap.add_argument('--out', default=f'{ROOT}/notes/cross-repo-changes.md')
    a = ap.parse_args(argv)
    since = {}
    for s in a.since:
        k, _, rev = s.partition('=')
        if k not in REPOS or not rev: die(f'--since wants REPO=REV with REPO one of {", ".join(REPOS)}: {s}')
        since[k] = rev
    for repo, p in REPOS.items():
        if not (p / '.git').exists() and not (p / 'HEAD').exists() and git(p, 'rev-parse', '--git-dir')[0] != 0: die(f'{repo}: {p} is not a git repository (set UARO_DOCS, UARO_LOOT_SHEET or GAME_DATA)')
    state_file = Path(ROOT) / 'notes' / 'cross-repo-state.json'
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    new_tips = {r: tip(p) for r, p in REPOS.items()}
    first = not state
    text = report(state, new_tips, since) if not first else None
    if first:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps({r: t for r, t in new_tips.items() if t}, indent=2) + '\n')
        print('Baseline recorded: ' + ', '.join(f'{r} {t[:7]}' for r, t in new_tips.items() if t) + '. Run again later to see what changed.')
        return 0
    Path(a.out).parent.mkdir(parents=True, exist_ok=True); Path(a.out).write_text(text)
    print(text, end='')
    if a.ack:
        state_file.write_text(json.dumps({r: t for r, t in new_tips.items() if t}, indent=2) + '\n'); print('Baselines moved to the current tips.')
    else: print(f'(report saved to {a.out}; run with --ack when handled)')
    return 0

if __name__ == '__main__':
    sys.exit(main())
