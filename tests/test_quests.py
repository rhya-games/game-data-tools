"""Tests for build_quests.py, quests.py and fetch_quest_text.sh."""
import contextlib, io, json, os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_quests as bq, import_loot_sheet as imp, quests as q
from test_network_scripts import FakeNetwork, ok, API

CLIENT = 'QuestInfoList = {\n\t[1180] = {\n\t\tTitle = "Get Rid of \\"Bakonawa\\"",\n\t\tDescription = {\n\t\t\t"Retrieve 2 Lost Belongings.",\n\t\t\t"Line two."\n\t\t},\n\t\tSummary = "Talk to him"\n\t},\n\t[1181] = {\n\t\tTitle = "Other",\n\t\tDescription = {\n\t\t},\n\t\tSummary = ""\n\t},\n}\n'
ITEMS = 'Body:\n  - Id: 6520\n    AegisName: Lost_Belongings\n    Name: Lost Belongings\n  - Id: 523\n    AegisName: Holy_Water\n    Name: Holy Water\n  - Id: 501\n    AegisName: Red_Potion\n    Name: Red Potion\n'
QDB = 'Body:\n  - Id: 1180\n    Title: Get Rid of Bakonawa\n    TimeLimit: 3600\n    Targets:\n      - Mob: TIYANAK\n        Count: 5\n    Drops:\n      - Mob: TIYANAK\n        Item: Lost_Belongings\n        Rate: 3000\n  - Id: 1190\n    Title: No details\n'
SCRIPT = '''prontera,1,1,4\tscript\tMissing Father\t100,{
\tif (checkquest(1180) == -1) {
\t\tif (countitem(Lost_Belongings) < 2) { mes "Bring 2."; close; }
\t\tdelitem Lost_Belongings,2;
\t\tcompletequest 1180;
\t\tgetitem Red_Potion,5;   // reward
\t}
\t// delitem Holy_Water,9;   commented out
\tsetquest 1190;
\tcountitem(Holy_Water) > 0;
\tdelitem 523,1;
\tclose;
}
-\tscript\tNo quest here\t-1,{
\tdelitem Red_Potion,1;
}
'''

class Parsing(unittest.TestCase):
    def test_client_quest_list(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'q.lub'; p.write_text(CLIENT); d = bq.parse_client(p)
        self.assertEqual(d[1180], {'title': 'Get Rid of "Bakonawa"', 'description': ['Retrieve 2 Lost Belongings.', 'Line two.'], 'summary': 'Talk to him'})
        self.assertEqual(d[1181]['description'], [])

    def test_quest_db_targets_and_drops_resolve_items(self):
        with tempfile.TemporaryDirectory() as t:
            Path(f'{t}/db/re').mkdir(parents=True); Path(f'{t}/db/re/quest_db.yml').write_text(QDB); Path(f'{t}/db/re/item_db_etc.yml').write_text(ITEMS)
            by_aegis, _ = bq.load_items(t); d = bq.parse_quest_db(t, 're', by_aegis)
        self.assertEqual((d[1180]['time_limit'], d[1180]['targets']), (3600, [{'mob': 'TIYANAK', 'count': 5}]))
        self.assertEqual(d[1180]['drops'], [{'mob': 'TIYANAK', 'item': 6520, 'item_name': 'Lost Belongings', 'count': 1, 'rate': 3000}])
        self.assertEqual(d[1190]['targets'], [])

    def test_needed_quantities_for_comparisons(self):
        self.assertEqual([bq.needed(c, 10) for c in ('<', '<=', '>', '>=', '==', None)], [10, 11, 11, 10, 10, 10])
        self.assertEqual(bq.needed('!=', 0), 1); self.assertIsNone(bq.needed('<', None))

    def test_script_items_attach_to_the_nearest_quest_and_comments_are_ignored(self):
        by_aegis = {'lost_belongings': (6520, 'Lost Belongings'), 'holy_water': (523, 'Holy Water'), 'red_potion': (501, 'Red Potion')}
        (name, mp, ids, items), = bq.parse_script(SCRIPT, by_aegis, {523: 'Holy Water'})   # the NPC without a quest is skipped
        self.assertEqual((name, mp, ids), ('Missing Father', 'prontera', [1180, 1190]))
        rows = {(i[0], i[1], i[3], i[5]) for i in items}
        self.assertIn(('checks', 6520, 2, 1180), rows); self.assertIn(('takes', 6520, 2, 1180), rows); self.assertIn(('gives', 501, 5, 1180), rows)
        self.assertIn(('takes', 523, 1, 1190), rows); self.assertIn(('checks', 523, 1, 1190), rows)    # countitem(...) > 0 means "at least 1"
        self.assertFalse(any(i[1] == 523 and i[3] == 9 for i in items))                              # the commented-out delitem

    def test_items_before_any_quest_belong_to_the_first_quest(self):
        (_, _, ids, items), = bq.parse_script('prt,1,1,1\tscript\tNPC\t1,{\n\tdelitem 501,3;\n\tsetquest 5000;\n}\n', {}, {501: 'Red Potion'})
        self.assertEqual([(i[0], i[1], i[3], i[5]) for i in items], [('takes', 501, 3, 5000)])

    def test_changequest_mentions_both_ids(self):
        (_, _, ids, _), = bq.parse_script('prt,1,1,1\tscript\tNPC\t1,{\n\tchangequest 5000,5001;\n}\n', {}, {})
        self.assertEqual(ids, [5000, 5001])

LOOT = [
    {'name': 'Agate', 'itemId': 730, 'categories': ['Other Quest', 'uaRO'], 'uses': [{'for': 'Great Axe', 'qty': 30, 'note': 'Level 4 weapon quest'}, {'for': 'Great Axe', 'qty': 30, 'note': 'Level 4 weapon quest'}]},
    {'name': 'Rose', 'itemId': 748, 'categories': ['Official Hat Quest'], 'uses': [{'for': 'Mystic Rose', 'qty': 3}]},
    {'name': 'Gem', 'itemId': 731, 'categories': ['Cooking', 'Not Reviewed'], 'uses': [{'for': 'Mystic Rose', 'qty': 10}, {'for': 'Soup'}]},
    {'name': 'Junk', 'itemId': None, 'categories': ['No Use'], 'uses': []},
]

class UaroData(unittest.TestCase):
    def setUp(self): self.tmp = tempfile.TemporaryDirectory(); self.t = self.tmp.name; Path(f'{self.t}/loot.json').write_text(json.dumps(LOOT))
    def tearDown(self): self.tmp.cleanup()
    def run_import(self, *extra):
        with contextlib.redirect_stdout(io.StringIO()): imp.main(['--loot', f'{self.t}/loot.json', '--out', f'{self.t}/data/uaro-quests.json', *extra])
        return {r['name']: r for r in json.loads(Path(f'{self.t}/data/uaro-quests.json').read_text(encoding='utf-8'))['quests']}

    def test_invert_groups_ingredients_by_target(self):
        r = self.run_import()
        self.assertEqual(sorted(r), ['Great Axe', 'Mystic Rose', 'Soup']); self.assertEqual(r['Mystic Rose']['id'], 'uaro-mystic-rose')
        self.assertEqual(r['Mystic Rose']['ingredients'], [{'item_id': 731, 'item': 'Gem', 'qty': 10}, {'item_id': 748, 'item': 'Rose', 'qty': 3}])
        self.assertEqual(r['Great Axe']['ingredients'], [{'item_id': 730, 'item': 'Agate', 'qty': 30, 'note': 'Level 4 weapon quest'}])   # a repeated use appears once
        self.assertEqual(r['Mystic Rose']['categories'], ['Cooking', 'Official Hat Quest']); self.assertEqual(r['Great Axe']['categories'], ['Other Quest'])   # placeholders dropped
        self.assertTrue(r['Mystic Rose']['is_quest'] and r['Great Axe']['is_quest'] and not r['Soup']['is_quest'])

    def test_reimport_keeps_hand_added_fields_and_records(self):
        self.run_import(); p = Path(f'{self.t}/data/uaro-quests.json'); d = json.loads(p.read_text(encoding='utf-8'))
        for r in d['quests']:
            if r['name'] == 'Mystic Rose': r['npc'] = 'Rose Lady'; r['wiki'] = 'x'; r['ingredients'] = []
        d['quests'].append({'id': 'uaro-custom', 'name': 'Custom Quest', 'categories': [], 'ingredients': [], 'is_quest': True, 'npc': 'Me'}); p.write_text(json.dumps(d))
        r = self.run_import()
        self.assertEqual((r['Mystic Rose']['npc'], r['Mystic Rose']['wiki']), ('Rose Lady', 'x')); self.assertEqual(len(r['Mystic Rose']['ingredients']), 2)   # ingredients are refreshed
        self.assertEqual(r['Custom Quest']['npc'], 'Me')

    def test_bad_input_is_refused(self):
        Path(f'{self.t}/bad.json').write_text('{not json'); 
        with self.assertRaises(SystemExit): imp.main(['--loot', f'{self.t}/bad.json', '--out', f'{self.t}/o.json'])
        Path(f'{self.t}/other.json').write_text('[{"name": "x"}]')
        with self.assertRaises(SystemExit): imp.main(['--loot', f'{self.t}/other.json', '--out', f'{self.t}/o.json'])
        with self.assertRaises(SystemExit): imp.main(['--loot', f'{self.t}/missing.json'])

    def test_uaro_quests_join_the_index(self):
        self.run_import(); rows = bq.uaro_rows(f'{self.t}/data/uaro-quests.json')
        self.assertEqual(sorted(r['id'] for r in rows), ['uaro-great-axe', 'uaro-mystic-rose'])   # recipes are not quests
        r = [x for x in rows if x['id'] == 'uaro-mystic-rose'][0]
        self.assertEqual((r['origin'], r['uaro'], r['title']), ('uaro', 'yes', 'Mystic Rose')); self.assertEqual([(i['item_name'], i['qty'], i['relation']) for i in r['items']], [('Gem', 10, 'takes'), ('Rose', 3, 'takes')])
        self.assertEqual(bq.uaro_rows('/nonexistent.json'), [])

class UaroRules(unittest.TestCase):
    NPC = lambda f: {'name': 'n', 'map': 'm', 'file': f, 'mode': 're'}
    def rules(self, text):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'r.csv'; p.write_text(text); return bq.load_uaro_rules(str(p))

    def test_file_rule_marks_quests_only_handled_by_those_files(self):
        r = self.rules('scope,value,note\nfile,npc/re/quests/juno.txt,not here\nfile,npc/re/events/,events folder\n')
        N = UaroRules.NPC
        self.assertEqual(bq.uaro_status(1, 't', [N('npc/re/quests/juno.txt')], r), ('no', 'not here'))
        self.assertEqual(bq.uaro_status(1, 't', [N('npc/re/quests/juno.txt'), N('npc/re/quests/other.txt')], r), ('unknown', ''))   # also handled elsewhere
        self.assertEqual(bq.uaro_status(1, 't', [N('npc/re/events/x.txt')], r)[0], 'no'); self.assertEqual(bq.uaro_status(1, 't', [], r)[0], 'unknown')

    def test_yes_rules_need_one_npc_no_rules_need_all(self):
        r = self.rules('scope,value,status,note\nfile,npc/a.txt,yes,present\nfile,npc/b.txt,no,absent\n'); N = UaroRules.NPC
        self.assertEqual(bq.uaro_status(1, 't', [N('npc/a.txt'), N('npc/c.txt')], r), ('yes', 'present'))      # one NPC in a "yes" file is enough
        self.assertEqual(bq.uaro_status(2, 't', [N('npc/b.txt'), N('npc/c.txt')], r), ('unknown', ''))         # a "no" file must cover every NPC
        self.assertEqual(bq.uaro_status(3, 't', [N('npc/b.txt')], r), ('no', 'absent'))
        self.assertEqual(bq.uaro_status(4, 't', [N('npc/a.txt'), N('npc/b.txt')], r)[0], 'yes')                # first matching rule wins

    def test_status_must_be_yes_or_no(self):
        with self.assertRaises(SystemExit): self.rules('scope,value,status,note\nquest,5,maybe,x\n')

    def test_quest_range_and_title_rules(self):
        r = self.rules('scope,value,note\nquest,5,one\nrange,10-20,span\ntitle,Subjugation,by name\n')
        self.assertEqual(bq.uaro_status(5, 'x', [], r), ('no', 'one')); self.assertEqual(bq.uaro_status(20, 'x', [], r), ('no', 'span')); self.assertEqual(bq.uaro_status(21, 'x', [], r)[0], 'unknown')
        self.assertEqual(bq.uaro_status(99, '[Standby] subjugation-Veins', [], r), ('no', 'by name'))

    def test_bad_scope_is_refused_and_missing_file_means_no_rules(self):
        with self.assertRaises(SystemExit): self.rules('scope,value,note\nbogus,x,y\n')
        self.assertEqual(bq.load_uaro_rules('/nonexistent.csv'), [])

class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); t = self.t = self.tmp.name
        for m in ('pre-re', 're'): Path(f'{t}/rathena/db/{m}').mkdir(parents=True); Path(f'{t}/rathena/db/{m}/item_db_etc.yml').write_text(ITEMS)
        Path(f'{t}/rathena/db/re/quest_db.yml').write_text(QDB); Path(f'{t}/rathena/db/pre-re/quest_db.yml').write_text('Body:\n  - Id: 1190\n    Title: No details\n')
        Path(f'{t}/rathena/npc/re/quests').mkdir(parents=True); Path(f'{t}/rathena/npc/re/quests/q.txt').write_text(SCRIPT)
        Path(f'{t}/client.lub').write_text(CLIENT)
        self.out = f'{t}/index/quests.jsonl'
        with contextlib.redirect_stdout(io.StringIO()): bq.main(['--client', f'{t}/client.lub', '--rathena', f'{t}/rathena', '--out', self.out, '--uaro-data', f'{t}/none.json'])
        self.rows = {r['id']: r for r in map(json.loads, Path(self.out).read_text(encoding='utf-8').splitlines())}
    def tearDown(self): self.tmp.cleanup()

    def test_index_merges_all_sources(self):
        self.assertEqual(sorted(self.rows), [1180, 1181, 1190])
        r = self.rows[1180]; self.assertEqual(r['title'], 'Get Rid of "Bakonawa"'); self.assertEqual(set(r['db']), {'re'})
        self.assertEqual(r['npcs'], [{'name': 'Missing Father', 'map': 'prontera', 'file': 'npc/re/quests/q.txt', 'mode': 're'}])
        self.assertEqual(self.rows[1190]['title'], 'No details'); self.assertEqual(set(self.rows[1190]['db']), {'pre-re', 're'})

    def test_uaro_rules_mark_quests_and_the_cli_can_hide_them(self):
        rules = f'{self.t}/rules.csv'; Path(rules).write_text('scope,value,note\nfile,npc/re/quests/q.txt,not on uaRO\n'); out = f'{self.t}/index/marked.jsonl'
        with contextlib.redirect_stdout(io.StringIO()): bq.main(['--client', f'{self.t}/client.lub', '--rathena', f'{self.t}/rathena', '--out', out, '--uaro', rules, '--uaro-data', f'{self.t}/none.json'])
        rows = {r['id']: r for r in map(json.loads, Path(out).read_text(encoding='utf-8').splitlines())}
        self.assertEqual((rows[1180]['uaro'], rows[1181]['uaro']), ('no', 'unknown')); self.assertEqual(rows[1180]['uaro_note'], 'not on uaRO')
        old = q.IDX; q.IDX = out
        def run(*a):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf): q.main(list(a))
            return buf.getvalue()
        try:
            self.assertIn('(not on uaRO)', run('--item', 'Lost Belongings')); self.assertIn('0 quest(s) ask for', run('--uaro', '--item', 'Lost Belongings'))
            self.assertIn('[not on uaRO: not on uaRO]', run('1180')); self.assertIn('2 marked not on uaRO', run('--stats'))   # 1190 is handled by the same NPC
        finally: q.IDX = old

    def test_cli_lookups(self):
        old = q.IDX; q.IDX = self.out
        def run(*a):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf): q.main(list(a))
            return buf.getvalue()
        try:
            out = run('1180'); self.assertIn('asks for 2 x Lost Belongings (6520)', out); self.assertIn('gives 5 x Red Potion', out); self.assertIn('kill 5 TIYANAK', out); self.assertIn('time limit 3600s', out)
            self.assertIn('1 quest(s) ask for', run('--item', 'Lost Belongings')); self.assertIn('give', run('--item', 'Red Potion', '--gives'))
            self.assertIn('1 quest(s) target tiyanak', run('--mob', 'tiyanak')); self.assertIn('Get Rid', run('bakonawa'))
            self.assertIn('3 quests', run('--stats'))
            with self.assertRaises(SystemExit): run('nonsense-title')
        finally: q.IDX = old

class FetchQuestText(FakeNetwork):
    SHA = 'b' * 40
    def test_downloads_the_quest_list_and_records_meta(self):
        self.routes[API + 'master'] = ok(json.dumps({'sha': self.SHA}))
        self.routes[f'https://raw.githubusercontent.com/llchrisll/ROenglishRE/{self.SHA}/Translation/Renewal/SystemEN/OngoingQuests.lub'] = ok('QuestInfoList = {}')
        r = self.run_script('fetch_quest_text.sh'); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f'commit: {self.SHA}', Path(f'{self.tmp.name}/data/pages/downloads/OngoingQuests.lub.meta').read_text())
        again = self.run_script('fetch_quest_text.sh'); self.assertIn('already downloaded', again.stdout)

    def test_rejects_something_that_is_not_a_quest_list(self):
        self.routes[API + 'master'] = ok(json.dumps({'sha': self.SHA}))
        self.routes[f'https://raw.githubusercontent.com/llchrisll/ROenglishRE/{self.SHA}/Translation/Renewal/SystemEN/OngoingQuests.lub'] = ok('<html>rate limited</html>')
        r = self.run_script('fetch_quest_text.sh'); self.assertNotEqual(r.returncode, 0); self.assertIn('not a quest list', r.stderr)

if __name__ == '__main__':
    unittest.main()
