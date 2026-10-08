"""Tests for the mob, skill and drop tools using tiny emulator database fixtures. Run: python3 -m unittest discover -s tests"""
import contextlib, io, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin'))
import common, compare_mob, compare_skill, drops

def put(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f: f.write(text)

HERC_MOB = '''mob_db: (
{
\tId: 1002
\tName: "Poring"
\tLv: 1
\tHp: 50
\tExp: 2
\tJExp: 1
\tAttack: [7, 10]
\tDef: 0
\tStats: {
\t\tStr: 6
\t\tLuk: 30
\t}
\tSize: "Size_Medium"
\tRace: "RC_Plant"
\tElement: ("Ele_Water", 1)
\tMoveSpeed: 400
\tDrops: {
\t\tJellopy: 7000
\t\tApple: 100
\t}
\tMvpDrops: {
\t\tBlade: 5
\t}
},
)
'''
RATH_MOB = '''Body:
  - Id: 1002
    AegisName: PORING
    Name: Poring
    Level: 1
    Hp: 50
    BaseExp: 2
    JobExp: 1
    Attack: 7
    Attack2: 10
    Defense: 0
    Str: 6
    Luk: 30
    Size: Medium
    Race: Plant
    Element: Water
    ElementLevel: 1
    WalkSpeed: 400
    Drops:
      - Item: Jellopy
        Rate: 7000
    MvpDrops:
      - Item: Blade
        Rate: 5
'''
HERC_ITEMS = '''item_db: (
{
\tId: 909
\tAegisName: "Jellopy"
\tName: "Jellopy"
},
{
\tId: 512
\tAegisName: "Apple"
\tName: "Apple"
},
{
\tId: 1201
\tAegisName: "Blade"
\tName: "Blade"
},
)
'''
RATH_ITEMS = '''Body:
  - Id: 909
    AegisName: Jellopy
    Name: Jellopy
  - Id: 1201
    AegisName: Blade
    Name: Blade
'''
HERC_SKILL = '''skill_db: (
{
\tId: 28
\tName: "AL_HEAL"
\tDescription: "Heal"
\tMaxLevel: 10
\tRange: 9
\tElement: "Ele_Holy"
\tCastTime: {
\t\tLv1: 1000
\t\tLv2: 1000
\t}
\tRequirements: {
\t\tSPCost: {
\t\t\tLv1: 13
\t\t\tLv2: 16
\t\t}
\t}
},
)
'''
RATH_SKILL = '''Body:
  - Id: 28
    Name: AL_HEAL
    Description: Heal
    MaxLevel: 10
    Range: 9
    Element: Holy
    Requires:
      SpCost:
        - Level: 1
          Amount: 13
        - Level: 2
          Amount: 16
    CastTime:
      - Level: 1
        Time: 1000
      - Level: 2
        Time: 1000
'''
TREE = '''skill_tree: {
Acolyte: {
\t\tAL_HEAL: 1
\t\tAL_DP: 2
}
Priest: {
\t\tPR_SANCTUARY: 1
}
}
'''

class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        for mode in ('pre-re', 're'):
            put(r, f'hercules/db/{mode}/mob_db.conf', HERC_MOB); put(r, f'rathena/db/{mode}/mob_db.yml', RATH_MOB)
            put(r, f'hercules/db/{mode}/item_db.conf', HERC_ITEMS); put(r, f'rathena/db/{mode}/item_db_etc.yml', RATH_ITEMS)
            put(r, f'hercules/db/{mode}/skill_db.conf', HERC_SKILL); put(r, f'rathena/db/{mode}/skill_db.yml', RATH_SKILL)
        put(r, 'hercules/db/pre-re/skill_tree.conf', TREE)
        self.saved = [(m, a, getattr(m, a)) for m, attrs in ((compare_mob, ['ROOT']), (compare_skill, ['ROOT']), (drops, ['ROOT', 'H', 'R'])) for a in attrs]
        for m in (compare_mob, compare_skill): m.ROOT = r
        drops.ROOT, drops.H, drops.R = r, f'{r}/hercules/db', f'{r}/rathena/db'

    def tearDown(self):
        for m, a, v in self.saved: setattr(m, a, v)
        self.tmp.cleanup()

    def out(self, fn, *a):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf): fn(*a)
        return buf.getvalue()

class MobTests(Fixture):
    def test_herc_and_rath_rows(self):
        h, r = compare_mob.herc('pre-re')[1002], compare_mob.rath('pre-re')[1002]
        self.assertEqual((h['Name'], h['Hp'], h['Atk'], h['Size'], h['Race'], h['Element'], h['Str'], h['Luk']), ('Poring', 50, '7-10', 'Medium', 'Plant', 'Water 1', 6, 30))
        self.assertEqual((r['Atk'], r['Element'], r['Size']), ('7-10', 'Water 1', 'Medium'))
        self.assertEqual(compare_mob.herc('re')[1002]['Atk'], '7/10')
        self.assertEqual(compare_mob.rath('re')[1002]['Atk'], '7/10')

class MissingFieldDefaults(Fixture):
    """A field a database leaves out takes that project's documented default, so a blank is not mistaken for a difference."""
    def test_mob_defaults_differ_by_project(self):
        put(self.tmp.name, 'hercules/db/pre-re/mob_db.conf', 'm: (\n{\n\tId: 1\n\tName: "Bare"\n}\n)\n')
        put(self.tmp.name, 'rathena/db/pre-re/mob_db.yml', 'Body:\n  - Id: 1\n    AegisName: BARE\n    Name: Bare\n')
        h, r = compare_mob.herc('pre-re')[1], compare_mob.rath('pre-re')[1]
        self.assertEqual((h['Level'], h['Hp'], h['Exp'], h['Str'], h['Size'], h['Race']), (1, 1, 0, 0, 'Medium', 'Formless'))
        self.assertEqual((r['Level'], r['Hp'], r['Exp'], r['Str'], r['Size'], r['Race'], r['Element']), (1, 1, 0, 1, 'Small', 'Formless', 'Neutral 1'))

    def test_explicit_values_are_not_overridden(self):
        h, r = compare_mob.herc('pre-re')[1002], compare_mob.rath('pre-re')[1002]
        self.assertEqual((h['Str'], h['Size'], r['Str'], r['Size']), (6, 'Medium', 6, 'Medium'))

    def test_skill_defaults(self):
        put(self.tmp.name, 'hercules/db/pre-re/skill_db.conf', 's: (\n{\n\tId: 5\n\tName: "XX_BARE"\n\tMaxLevel: 1\n}\n)\n')
        put(self.tmp.name, 'rathena/db/pre-re/skill_db.yml', 'Body:\n  - Id: 5\n    Name: XX_BARE\n    Description: Bare\n    MaxLevel: 1\n')
        h, r = compare_skill.herc('pre-re')[5], compare_skill.rath('pre-re')[5]
        for row, neutral in ((h, 'Neutral'), (r, 'Neutral')):
            self.assertEqual((row['Range'], row['CastTime'], row['AfterCast'], row['CoolDown'], row['Element']), ('0', '0', '0', '0', neutral))

class SkillTests(Fixture):
    def test_lv(self):
        lv = compare_skill.lv
        self.assertEqual((lv(None), lv(9), lv({'Lv1': 5, 'Lv2': 5}), lv({'Lv10': 1, 'Lv2': 7}), lv([{'Level': 2, 'Time': 8}, {'Level': 1, 'Time': 6}], 'Time')), (None, '9', '5', '7,1', '6,8'))

    def test_herc_and_rath_agree(self):
        h, r = compare_skill.herc('pre-re')[28], compare_skill.rath('pre-re')[28]
        self.assertEqual((h['Const'], h['SP'], h['CastTime'], h['Element']), ('AL_HEAL', '13,16', '1000', 'Holy'))
        for k in ('Const', 'SP', 'CastTime', 'Element', 'Range', 'MaxLevel'): self.assertEqual(str(h[k]), str(r[k]), k)

    def test_classes(self):
        self.assertEqual(compare_skill.classes('AL_HEAL'), ['Acolyte'])
        self.assertEqual(compare_skill.classes('AL_DP'), ['Acolyte'])
        self.assertEqual(compare_skill.classes('NOPE'), [])

class DropTests(Fixture):
    def test_item_maps(self):
        self.assertEqual(drops.herc_items('re')['Jellopy'], (909, 'Jellopy'))
        self.assertEqual(drops.rath_items('re')['Blade'], (1201, 'Blade'))

    def test_mob_drop_tables(self):
        h = drops.herc_mobs('pre-re')[0]
        self.assertEqual((h['id'], h['drops'], h['mvp']), (1002, [('Jellopy', 7000), ('Apple', 100)], [('Blade', 5)]))
        self.assertEqual(drops.rath_mobs('pre-re')[0]['drops'], [('Jellopy', 7000)])

    def test_by_item_lists_monsters_with_percent(self):
        out = self.out(drops.by_item, 'jellopy')
        self.assertIn('1002 Poring', out); self.assertIn('70%', out)
        self.assertIn('MVP', self.out(drops.by_item, '1201'))
        self.assertIn('item not found', self.out(drops.by_item, 'nothing'))

    def test_by_mob_resolves_item_names(self):
        out = self.out(drops.by_mob, 'Poring')
        self.assertIn('Jellopy', out); self.assertIn('(909)', out); self.assertIn('MVP Blade', out)
        self.assertIn('monster not found', self.out(drops.by_mob, '9'))

class CommonNotes(unittest.TestCase):
    def test_precedence_override_and_hide(self):
        old = common.PRECEDENCE
        try:
            common.PRECEDENCE = 'my order'
            self.assertIn('Precedence: my order.', common.precedence_note())
            common.PRECEDENCE = ''
            self.assertEqual(common.precedence_note(), '')
        finally: common.PRECEDENCE = old

    def test_docs_missing_note(self):
        old = common.DOCS
        try:
            common.DOCS = '/nonexistent/docs'
            self.assertIn('No docs folder', common.docs_missing_note())
            with tempfile.TemporaryDirectory() as t:
                common.DOCS = t
                self.assertIsNone(common.docs_missing_note())
        finally: common.DOCS = old

if __name__ == '__main__':
    unittest.main()
