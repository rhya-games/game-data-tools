#!/usr/bin/env python3
"""Compare drop rates on uaRO wiki pages with the renewal data (index from renewal_items.py).
  compare_wiki_drops.py <wiki page.md ...> [--wiki DIR]
Reads table rows with an item id in backticks and percentages in the last cell, then reports for each:
  ok        a rate on the page equals the uaRO rate we computed for that item (or the 1x rate: then it says so)
  differs   the page has other rates than any we computed
  no data   the item is not dropped in the renewal data (a uaRO custom item, or a different source)
Wiki rates are what uaRO shows; ours are official 1x rates with the stated multipliers applied.
"""
import json, os, re, sys
from pathlib import Path
from common import ROOT

def load_index():
    p = Path(ROOT) / 'notes/handoff/renewal-items.jsonl'
    if not p.is_file(): sys.exit(f'error: {p} not found; run renewal_items.py first')
    return {r['id']: r for r in map(json.loads, p.read_text(encoding='utf-8').splitlines())}

def rows(text):
    for line in text.splitlines():
        if not line.startswith('|'): continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        m = re.search(r'`(\d{3,6})`', line)
        pcts = [float(x) for x in re.findall(r'(\d+(?:\.\d+)?)\s*%', cells[-1])]
        if m and pcts: yield int(m.group(1)), re.sub(r'<[^>]+>|!\[[^\]]*\]\([^)]*\)', '', cells[0]).strip(), pcts, cells[-1]

def compare(text, idx):
    out = []
    for iid, name, pcts, cell in rows(text):
        rec = idx.get(iid)
        if not rec: out.append(('no data', iid, name, pcts, [], [])); continue
        drops = [d for a in rec['areas'] for d in a['dropped_by']]
        named = [d for d in drops if d['name'] and d['name'].lower() in cell.lower()]  # narrow to the monsters the cell names
        drops = named or drops
        ours = sorted({d['uaro_pct'] for d in drops}); one = sorted({d['rate_pct'] for d in drops})
        status = 'ok' if any(abs(p - o) < 1e-9 for p in pcts for o in ours) else 'ok (1x)' if any(abs(p - o) < 1e-9 for p in pcts for o in one) else 'differs'
        out.append((status, iid, name, pcts, ours, one))
    return out

def main():
    args = sys.argv[1:]
    wiki = Path(os.environ.get('WIKI_DOCS', '/Users/jax/Projects/uaro-docs/docs'))
    if '--wiki' in args: i = args.index('--wiki'); wiki = Path(args[i + 1]); del args[i:i + 2]
    if not args: sys.exit(__doc__)
    idx = load_index()
    for a in args:
        p = Path(a) if Path(a).is_file() else wiki / a
        print(f'== {p.name}')
        for status, iid, name, pcts, ours, one in compare(p.read_text(encoding='utf-8'), idx):
            print(f'  {status:8} {iid} {name}: wiki {pcts}' + (f', ours uaRO {ours} (1x {one})' if ours else ''))

if __name__ == '__main__': main()
