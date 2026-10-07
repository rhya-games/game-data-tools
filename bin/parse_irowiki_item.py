#!/usr/bin/env python3
"""Parse saved db.irowiki.org item pages into JSON (reads pages/, never modifies them).
  parse_irowiki_item.py 740          one item as JSON
  parse_irowiki_item.py --index      rewrite index/irowiki_items.jsonl from every saved item page
"""
import html, json, os, re, sys
from pathlib import Path
ROOT = os.environ.get('GAME_DATA', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGES = f'{ROOT}/pages/db.irowiki.org'

def text(s):
    s = re.sub(r'<br\s*/?>', '\n', s)
    return html.unescape(re.sub(r'<[^>]+>', '', s)).strip()

def parse(raw):
    m = re.search(r'curID = (\d+)', raw)
    name = re.search(r'<td class="mdTitle"[^>]*>(.*?)</td>', raw, re.S)
    desc = re.search(r'<td class="bgLtRow1 padded">(.*?)</td>', raw, re.S)
    fields = {}
    for k, v in re.findall(r'<td class="[^"]*infoTitle">(.*?)</td>\s*<td class="[^"]*infoText">(.*?)</td>', raw, re.S):
        fields[text(k)] = text(v)
    drops = []
    sec = re.search(r'Monster Drops</div>(.*?)</table>', raw, re.S)
    if sec:
        for row in re.findall(r'<tr>(.*?)</tr>', sec.group(1), re.S):
            c = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
            mid = re.search(r'monster-info/(\d+)', row)
            if len(c) >= 3 and mid:
                drops.append({'monster_id': int(mid.group(1)), 'monster': text(c[1]), 'rate': text(c[2])})
    return {'id': int(m.group(1)) if m else None, 'name': text(name.group(1)) if name else None,
            'description': text(desc.group(1)) if desc else None, 'fields': fields, 'drops': drops}

def load(i):
    return parse(Path(f'{PAGES}/db_item-info_{i}').read_text(encoding='utf-8', errors='replace'))

if __name__ == '__main__':
    if sys.argv[1:] == ['--index']:
        os.makedirs(f'{ROOT}/index', exist_ok=True)
        ids = sorted(int(f.split('_')[-1]) for f in os.listdir(PAGES) if re.fullmatch(r'db_item-info_\d+', f))
        with open(f'{ROOT}/index/irowiki_items.jsonl', 'w', encoding='utf-8') as out:
            for i in ids: out.write(json.dumps(load(i), ensure_ascii=False) + '\n')
        print(len(ids), 'items indexed')
    else:
        print(json.dumps(load(int(sys.argv[1])), indent=1, ensure_ascii=False))
