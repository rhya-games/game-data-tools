#!/usr/bin/env python3
"""Compare one skill across Hercules pre-re/re and rAthena pre-re/re, show which class learns it, and list project docs and patch note mentions.
  compare_skill.py AL_HEAL | compare_skill.py Heal | compare_skill.py 28 | compare_skill.py --quest (list every quest skill)   (run from a repo with a docs/ folder, or set DOCS_DIR)
Quest = yes means the database flags it as a quest skill (platinum skills, for example), learned through a quest, not skill points.
Per-level values print as a list (all levels equal collapses to one number). Times are in ms.
"""
import os, re, sys
from pathlib import Path
import yaml
from common import *
FIELDS = ['Name', 'MaxLevel', 'Range', 'Element', 'SP', 'CastTime', 'AfterCast', 'CoolDown', 'Quest']

def lv(v, key=None):
    """scalar, Lv table (dict), or rAthena [{Level, <key>}] -> one comparable string"""
    if v is None: return None
    if isinstance(v, dict):
        vals = [str(x) for k, x in sorted(v.items(), key=lambda kv: int(re.sub(r'\D', '', kv[0]) or 0))]
    elif isinstance(v, list):
        vals = [str(x.get(key) if key else list(x.values())[-1]) for x in sorted(v, key=lambda x: x.get('Level', 0))]
    else: return str(v)
    return vals[0] if len(set(vals)) == 1 else ','.join(vals)

def herc(mode):
    out = {}
    for b in herc_blocks(f'{ROOT}/hercules/db/{mode}/skill_db.conf'):
        d = herc_parse(b)
        if 'Id' not in d: continue
        req = d.get('Requirements', {})
        out[d['Id']] = {'Const': d.get('Name'), 'Name': d.get('Description'), 'MaxLevel': d.get('MaxLevel'), 'Range': lv(d.get('Range', 0)),
            'Element': strip_prefix(lv(d.get('Element', 'Ele_Neutral'))), 'SP': lv(req.get('SPCost')), 'CastTime': lv(d.get('CastTime', 0)),
            'AfterCast': lv(d.get('AfterCastActDelay', 0)), 'CoolDown': lv(d.get('CoolDown', 0)), 'Quest': 'yes' if (d['SkillInfo'].get('Quest') if isinstance(d.get('SkillInfo'), dict) else 'Quest' in str(d.get('SkillInfo', ''))) else 'no'}
    return out

def rath(mode):
    out = {}
    for d in yaml.load(Path(f'{ROOT}/rathena/db/{mode}/skill_db.yml').read_text(encoding='utf-8'), Loader=YAML_LOADER).get('Body', []):
        req = d.get('Requires', {})
        out[d['Id']] = {'Const': d.get('Name'), 'Name': d.get('Description'), 'MaxLevel': d.get('MaxLevel'), 'Range': lv(d.get('Range', 0), 'Size'),
            'Element': lv(d.get('Element', 'Neutral'), 'Element'), 'SP': lv(req.get('SpCost'), 'Amount'), 'CastTime': lv(d.get('CastTime', 0), 'Time'),
            'AfterCast': lv(d.get('AfterCastActDelay', 0), 'Time'), 'CoolDown': lv(d.get('Cooldown') or d.get('CoolDown') or 0, 'Time'), 'Quest': 'yes' if (d['Flags'].get('IsQuest') if isinstance(d.get('Flags'), dict) else False) else 'no'}
    return out

def classes(const):
    job, got = None, []
    for l in Path(f'{ROOT}/hercules/db/pre-re/skill_tree.conf').read_text(encoding='utf-8', errors='replace').splitlines():
        m = re.match(r'^([A-Za-z_0-9]+):\s*\{', l)
        if m: job = m.group(1)
        if re.match(rf'^\t\t{re.escape(const)}:', l) and job: got.append(job)
    return got

def list_quest(data):
    """Every skill the databases flag as a quest skill (this includes the platinum skills), with the class that lists it."""
    rows = {}
    for label, d in data.items():
        for i, v in d.items():
            if v['Quest'] == 'yes': rows.setdefault(i, {'Const': v['Const'], 'Name': v['Name'], 'in': []})['in'].append(label)
    print(f'{len(rows)} skills flagged as quest skills in at least one source\n')
    for i, r in sorted(rows.items(), key=lambda kv: kv[1]['Const']):
        note = '' if len(r['in']) == len(data) else f"  (flag only in: {', '.join(r['in'])})"
        print(f"{i:>5}  {r['Const']:22} {r['Name'] or '':28} {', '.join(classes(r['Const'])) or '-'}{note}")

if __name__ == '__main__':
    key = sys.argv[1]
    data = {'herc pre-re': herc('pre-re'), 'herc re': herc('re'), 'rath pre-re': rath('pre-re'), 'rath re': rath('re')}
    if key == '--quest': list_quest(data); sys.exit()
    ids = sorted({i for d in data.values() for i, v in d.items() if str(i) == key or (v['Const'] or '').lower() == key.lower() or (v['Name'] or '').lower() == key.lower()})
    if not ids:
        names = {(i, n) for d in data.values() for i, v in d.items() for n in (v.get('Name'), v.get('Const')) if n}
        print_suggestions(key, sorted(names, key=str)); sys.exit(f'No skill matches {key!r} in any source.')
    for i in ids[:6]:
        print(f'\n===== Skill {i} =====')
        print_table({k: d.get(i) for k, d in data.items()}, FIELDS, 11)
        const = next((d[i]['Const'] for d in data.values() if i in d), None)
        flags = [k for k, d in data.items() if i in d and d[i]['Quest'] == 'yes']
        if flags: print('\nQuest skill: learned through a quest, not skill points (platinum skills are flagged this way). Flagged in: ' + ', '.join(flags))
        print(f'\nConstant: {const}\nLearned by (Hercules pre-re skill tree): {", ".join(classes(const)) or "not in the tree (quest, script or status granted: say so, do not guess)"}')
    names = {v[i]['Name'] for v in data.values() for i in ids if i in v and v[i]['Name']}
    doc_hits(names)
