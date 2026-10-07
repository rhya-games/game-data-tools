"""Shared helpers for compare_mob.py and compare_skill.py."""
import glob, os, re, sys
from pathlib import Path
import yaml
ROOT = os.environ.get('GAME_DATA', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS = os.environ.get('DOCS_DIR') or 'docs'
PRECEDENCE = os.environ.get('PRECEDENCE', 'maintainer screenshot > newest patch note > wiki > Hercules pre-re > Hercules re > rAthena')
YAML_LOADER = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)  # the C loader needs libyaml; fall back to pure Python

def docs_missing_note():
    if os.path.isdir(DOCS): return None
    return f'No docs folder at {os.path.abspath(DOCS)}: doc and patch note mentions are skipped. Run from the repo you are documenting or set DOCS_DIR.'

def precedence_note():
    """Closing line naming which source wins. Set PRECEDENCE to your own order, or to an empty string to hide it."""
    return f'Precedence: {PRECEDENCE}. Anything left unresolved: say "unknown" and ask.' if PRECEDENCE else ''

def herc_blocks(path):
    t = Path(path).read_text(encoding='utf-8', errors='replace')
    return [m.group(1) for m in re.finditer(r'\n\{\n(.*?)\n\}', t, re.S)]

def _val(v):
    v = v.strip().rstrip(',')
    if v.startswith('"') and v.endswith('"'): return v[1:-1]
    if v in ('true', 'false'): return v == 'true'
    if re.fullmatch(r'-?\d+(_\d+)*', v): return int(v.replace('_', ''))
    if re.fullmatch(r'0x[0-9a-fA-F]+', v): return int(v, 16)
    return v

def herc_parse(block):
    """Indentation-based parse of one libconfig block into nested dicts (arrays and tuples stay raw strings)."""
    root, stack = {}, []
    cur = root
    for line in block.split('\n'):
        s = line.strip()
        if not s or s.startswith('//'): continue
        if s == '}' or s == '},': cur = stack.pop() if stack else root; continue
        m = re.match(r'(\w+): \{$', s)
        if m: new = {}; cur[m.group(1)] = new; stack.append(cur); cur = new; continue
        m = re.match(r'(\w+): (.+)$', s)
        if m: cur[m.group(1)] = _val(m.group(2))
    return root

def strip_prefix(s):
    return re.sub(r'^(Ele_|RC_|Size_|RC2_)', '', str(s)) if s is not None else None

def print_table(srcs, fields, width=11):
    w = max(len(k) for k in srcs)
    print(f'{"":{w}}  ' + '  '.join(f'{f:<{width}}' for f in fields))
    for k, v in srcs.items():
        print(f'{k:{w}}  ' + ('  '.join(f'{str(v.get(f) if v.get(f) is not None else "-")[:width]:<{width}}' for f in fields) if v else '(not found)'))
    print('\nDisagreements:')
    found = {k: v for k, v in srcs.items() if v}
    diff = False
    for f in fields:
        vals = {k: str(v[f]) for k, v in found.items() if v.get(f) not in (None, '')}
        if len({x.lower() for x in vals.values()}) > 1:
            diff = True; print(f'  {f}: ' + ', '.join(f'{k}={x}' for k, x in vals.items()))
    if not diff: print('  none')

def doc_hits(names, id_pat=None, limit=25):
    """Lines in docs/ and patch notes naming the thing. A name inside a longer capitalised name ("Poring Card") is skipped."""
    def hit(l):
        if id_pat and id_pat.search(l): return True
        for base in names:
            for m in re.finditer(rf'(?<![A-Za-z]){re.escape(base)}(?![A-Za-z])', l):
                prev = re.search(r"([A-Za-z']+) $", l[:m.start()]); nxt = re.match(r" ([A-Za-z']+)", l[m.end():])
                if not (prev and prev.group(1)[0].isupper()) and not (nxt and nxt.group(1)[0].isupper()): return True
        return False
    out = []
    note = docs_missing_note()
    if note: print('\n' + note); return
    for f in sorted(glob.glob(f'{DOCS}/**/*.md', recursive=True)):
        b = os.path.relpath(f, DOCS)
        if b.startswith(('all-patch-notes', 'dev/')) or re.search(r'patch-notes/\d{4}/index', b): continue
        for n, l in enumerate(Path(f).read_text(encoding='utf-8', errors='replace').splitlines(), 1):
            if hit(l): out.append((b, n, l.strip()[:200]))
    print(f'\nproject docs / patch notes ({len(out)} lines mention it):')
    for b, n, l in out[:limit]: print(f'  {b}:{n}: {l}')
    if len(out) > limit: print(f'  ... {len(out) - limit} more')
    p = precedence_note()
    if p: print('\n' + p)
