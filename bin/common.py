"""Shared helpers for compare_mob.py and compare_skill.py."""
import glob, os, re, sys
from pathlib import Path
import yaml
ROOT = os.environ.get('GAME_DATA', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS = os.environ.get('DOCS_DIR') or 'docs'
PRECEDENCE = os.environ.get('PRECEDENCE', 'maintainer screenshot > newest patch note > wiki > Hercules pre-re > Hercules re > rAthena')
YAML_LOADER = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)  # the C loader needs libyaml; fall back to pure Python

def read_kv(path):
    """Parse a 'key: value' per line file such as a .meta sidecar; missing file gives {}."""
    p = Path(path)
    if not p.is_file(): return {}
    return {k.strip(): v.strip() for k, sep, v in (l.partition(':') for l in p.read_text(encoding='utf-8').splitlines()) if sep and k.strip()}

def client_file_info(root=None):
    """What the client item file is and what the index was built from: {'file': {...}, 'index': {...}, 'stale': str or None}."""
    root = root or ROOT
    f = read_kv(f'{root}/pages/downloads/itemInfo.lua.meta')
    i = read_kv(f'{root}/index/iteminfo.meta')
    stale = None
    if f and i and (f.get('variant'), f.get('commit')) != (i.get('variant'), i.get('commit')):
        stale = f"the item file is now {f.get('variant', '?')} @ {f.get('commit', '?')[:10]} but the index was built from {i.get('variant', '?')} @ {i.get('commit', '?')[:10]}: run bin/parse_iteminfo.py --index"
    return {'file': f, 'index': i, 'stale': stale}

def client_label(root=None):
    i = client_file_info(root)['index']
    return f"{i.get('variant', 'unknown variant')} @ {i['commit'][:10]}" if i.get('commit') else i.get('variant', 'unknown variant')

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

def col_widths(rows, fields, min_width=9, cap=40):
    """Width per column: at least min_width, wide enough for the longest value, never more than cap."""
    return {f: min(cap, max(min_width, len(f), *(len(str(r.get(f) if r.get(f) is not None else '-')) for r in rows if r))) for f in fields}

_MODE = re.compile(r'^(\S+) (pre-re|re)$')

def _differing(found, fields):
    out = {}
    for f in fields:
        vals = {k: str(v[f]) for k, v in found.items() if v.get(f) not in (None, '')}
        if len({x.lower() for x in vals.values()}) > 1: out[f] = vals
    return out

def print_table(srcs, fields, width=11):
    """Side-by-side table. Sources named '<tool> pre-re' / '<tool> re' are compared tool against tool within each mode;
    differences between the modes are listed separately because they are expected."""
    w = max(len(k) for k in srcs)
    cw = col_widths(srcs.values(), fields, width)
    print(f'{"":{w}}  ' + '  '.join(f'{f:<{cw[f]}}' for f in fields))
    for k, v in srcs.items():
        print(f'{k:{w}}  ' + ('  '.join(f'{str(v.get(f) if v.get(f) is not None else "-")[:cw[f]]:<{cw[f]}}' for f in fields) if v else '(not found)'))
    found = {k: v for k, v in srcs.items() if v}
    modes = {}
    for k in found:
        m = _MODE.match(k)
        modes.setdefault(m.group(2) if m else '', {})[k] = found[k]
    if '' in modes or len(modes) < 2:
        print('\nDisagreements:')
        d = _differing(found, fields)
        for f, vals in d.items(): print(f'  {f}: ' + ', '.join(f'{k}={x}' for k, x in vals.items()))
        if not d: print('  none')
        return
    print('\nDisagreements between sources (same mode):')
    any_diff = False
    for mode, grp in modes.items():
        for f, vals in _differing(grp, fields).items():
            any_diff = True; print(f'  [{mode}] {f}: ' + ', '.join(f'{k}={x}' for k, x in vals.items()))
    if not any_diff: print('  none')
    # fields that differ between modes, ignoring the ones already reported inside a mode
    agree = lambda grp, f: len({str(v[f]).lower() for v in grp.values() if v.get(f) not in (None, '')}) == 1
    names = [f for f in fields if all(agree(g, f) for g in modes.values())
             and len({str(next(v[f] for v in g.values() if v.get(f) not in (None, ''))).lower() for g in modes.values()}) > 1]
    if names: print('\nDiffers between pre-re and re (expected): ' + ', '.join(names))

def _squash(s): return re.sub(r'[^a-z0-9]', '', str(s).lower())

def suggest(key, names, n=5):
    """Near matches for a name that was not found: ignores case, spaces and punctuation ('Yggdrasilberry' finds 'Yggdrasil Berry'). names: [(id, name)]"""
    import difflib
    k = _squash(key)
    if len(k) < 3: return []
    seen, hits = set(), []
    pool = [(i, nm, _squash(nm)) for i, nm in names if nm and '\ufffd' not in nm and _squash(nm)]
    for i, nm, sq in pool:
        if (k in sq or (sq in k and len(sq) >= max(4, len(k) * 0.6))) and nm not in seen: seen.add(nm); hits.append((i, nm))
    for sq in difflib.get_close_matches(k, [p[2] for p in pool], n=n, cutoff=0.75):
        for i, nm, s2 in pool:
            if s2 == sq and nm not in seen: seen.add(nm); hits.append((i, nm))
    return hits[:n]

def print_suggestions(key, names):
    hits = suggest(key, names)
    if hits: print(f'\nNo exact match for {key!r}. Close names: ' + ', '.join(f'{nm} ({i})' for i, nm in hits))

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
