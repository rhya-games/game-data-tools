"""Tests for import_wiki_quests.py and how its fields reach the quest index and quests.py."""
import contextlib, copy, io, json, os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'bin'))
import build_quests as bq, import_loot_sheet as imp, import_wiki_quests as w, quests as q

PAGE = '''# Repeatable EXP Quests

### Item Quest List

| NPC | Location | Min Level | Max Level | Items | Base EXP | Job EXP | Base EXP Per Item | Job EXP Per Item |
|:---|:---|---:|---:|:---|---:|---:|---:|---:|
| **Langry** | `/navi gef_fild07 321/193` | 2 | 20 | 25 Fluff | 770 | 60 | 30 | 2 |
| **Nutters** | `/navi mjolnir_01 293/20` | 18 | 60 | 25 Acorn | 7,200 | 7,810 | 288 | 312 |
| **Old Man** | `/navi prt_fild00 1/2` | 5 | 9 | 10 Jellopy | 100 | 50 | 1 | 1 |
| **Broken** | `somewhere` | 5 | 9 | 10 Jellopy | 100 | 50 | 1 | 1 |

The following NPCs offer players a choice of how many monsters they want to hunt, with options of **50**, **100**, or **150**. All three yield the same, hunting **100 monsters** rewarding twice as much as hunting **50**.

### Hunting Quest List

| NPC | Location | Min Level | Max Level | Monster | Base EXP | Job EXP | Base EXP Per Monster | Job EXP Per Monster |
|:---|:---|---:|---:|:---|---:|---:|---:|---:|
| **Langry** | `/navi gef_fild07 321/193` | 2 | 20 | Fabre | 770 | 60 | 15 | 1 |
| **Gandolf** | `/navi lhz_dun01 146/287` | 45 | 80 | Remover`*` | 550,000 | 340,000 | 11,000 | 6,800 |

| Other | Table |
|:---|:---|
| not | a quest |
'''
def rec(name, ings, **kw): return {'id': imp.slug(name), 'name': name, 'categories': [], 'ingredients': [{'item_id': None, 'item': i, 'qty': n} for i, n in ings], 'is_quest': False, **kw}

class Parsing(unittest.TestCase):
    def test_small_helpers(self):
        self.assertEqual(w.clean('**Langry** ![x](img/a.gif) `a`<br>b'), 'Langry a b'); self.assertEqual(w.num('1,162,800 '), 1162800); self.assertIsNone(w.num('-'))
        self.assertEqual(w.navi('`/navi gef_fild07 321/193`'), 'gef_fild07 321/193'); self.assertIsNone(w.navi('Located in every inn'))
        self.assertEqual(w.norm("Mr. Smile's [1]"), 'mrsmiles1')

    def test_tables_know_their_heading(self):
        t = w.md_tables(PAGE); self.assertEqual([x[0] for x in t], ['Item Quest List', 'Hunting Quest List', 'Hunting Quest List'])
        self.assertEqual(t[0][1][:3], ['NPC', 'Location', 'Min Level']); self.assertEqual(len(t[0][2]), 4); self.assertEqual(t[0][2][1]['Base EXP'], '7,200')

    def test_rows_and_warnings(self):
        rows, warn = w.repeatable_quests(PAGE); r = {x['name']: x for x in rows}
        self.assertEqual(sorted(r), ['Gandolf Hunting Quest', 'Langry Hunting Quest', 'Langry Repeatable Quest', 'Nutters Repeatable Quest', 'Old Man Repeatable Quest'])
        n = r['Nutters Repeatable Quest']
        self.assertEqual((n['npc'], n['location'], n['min_level'], n['max_level'], n['rewards'], n['ingredients']), ('Nutters', 'mjolnir_01 293/20', 18, 60, {'base_exp': 7200, 'job_exp': 7810}, [{'item': 'Acorn', 'qty': 25}]))
        self.assertEqual(n['wiki'], 'https://wiki.uaro.net/repeatable-quests/')
        g = r['Gandolf Hunting Quest']; self.assertEqual(g['hunt'], {'monster': 'Remover', 'quest_access': True, 'counts': [50, 100, 150], 'rewards_for': 50})   # not [50,100,150,50,...] from the next sentence
        self.assertFalse(r['Langry Hunting Quest']['hunt']['quest_access']); self.assertEqual(r['Langry Hunting Quest']['ingredients'], [])
        self.assertEqual(len(warn), 1); self.assertIn('Broken', warn[0])
        rows, warn = w.repeatable_quests(PAGE.replace('options of **50**, **100**, or **150**', 'some options')); self.assertTrue(any('kill counts' in x for x in warn)); self.assertNotIn('counts', rows[-1]['hunt'])

class Applying(unittest.TestCase):
    def setUp(self):
        self.rows, _ = w.repeatable_quests(PAGE)
        self.recs = [rec('Nutters Repeatable Quest', [('Acorn', 25)]), rec('Fluff Thing', [('Fluff', 25)]), rec('Other', [('Fluff', 25)]), rec('Jelly Hat', [('Jellopy', 10)]), rec('Hat Quest', [('Acorn', 99)])]
    def run_apply(self, **kw): self.rep = w.apply_rows(self.recs, self.rows, **kw); return {r['name']: r for r in self.recs}

    def test_match_by_name_by_ingredients_or_new(self):
        r = self.run_apply()
        self.assertEqual(self.rep['by_name'], ['Nutters Repeatable Quest']); self.assertEqual(r['Nutters Repeatable Quest']['npc'], 'Nutters'); self.assertTrue(r['Nutters Repeatable Quest']['is_quest'])
        self.assertEqual(self.rep['by_ingredients'], ['Old Man Repeatable Quest -> Jelly Hat']); self.assertEqual(r['Jelly Hat']['npc'], 'Old Man')   # one record has exactly these ingredients
        self.assertEqual(len(self.rep['ambiguous']), 1); self.assertIn('Fluff Thing, Other', self.rep['ambiguous'][0]); self.assertNotIn('npc', r['Fluff Thing']); self.assertNotIn('Langry Repeatable Quest', r)   # two records: left alone
        self.assertEqual(sorted(self.rep['created']), ['Gandolf Hunting Quest', 'Langry Hunting Quest'])
        c = r['Gandolf Hunting Quest']; self.assertEqual((c['id'], c['source'], c['is_quest'], c['ingredients'], c['location']), ('uaro-gandolf-hunting-quest', 'wiki', True, [], 'lhz_dun01 146/287'))

    def test_new_record_takes_item_ids_it_already_knows(self):
        self.recs[0]['ingredients'][0]['item_id'] = 1026; self.rows = [{'name': 'Squirrel Quest', 'npc': 'S', 'ingredients': [{'item': 'Acorn', 'qty': 3}, {'item': 'Moss', 'qty': 1}], 'categories': ['X']}]
        r = self.run_apply(); self.assertEqual(r['Squirrel Quest']['ingredients'], [{'item_id': 1026, 'item': 'Acorn', 'qty': 3}, {'item': 'Moss', 'qty': 1}])

    def test_hand_fields_are_kept_and_differences_reported(self):
        self.recs[0].update(npc='Nutters (hand)', min_level=18, notes='mine'); r = self.run_apply()
        self.assertEqual((r['Nutters Repeatable Quest']['npc'], r['Nutters Repeatable Quest']['notes'], r['Nutters Repeatable Quest']['max_level']), ('Nutters (hand)', 'mine', 60))   # filled the gap, kept the hand value
        self.assertEqual(self.rep['differs'], ["Nutters Repeatable Quest: npc is 'Nutters (hand)', wiki says 'Nutters'"])   # equal min_level is not a difference
        r = self.run_apply(overwrite=True); self.assertEqual(r['Nutters Repeatable Quest']['npc'], 'Nutters'); self.assertEqual(r['Nutters Repeatable Quest']['notes'], 'mine')

    def test_ingredient_difference_is_reported_not_applied(self):
        self.recs[0]['ingredients'][0]['qty'] = 30; r = self.run_apply()
        self.assertEqual(len(self.rep['ingredient_diffs']), 1); self.assertEqual(r['Nutters Repeatable Quest']['ingredients'][0]['qty'], 30)

    def test_filling_fields_of_an_existing_quest_counts_as_a_change(self):
        self.recs[0]['is_quest'] = True; self.run_apply(); self.assertIn('uaro-nutters-repeatable-quest', self.rep['changed'])   # or the file would not be written

    def test_second_run_changes_nothing(self):
        self.run_apply(); after = copy.deepcopy(self.recs); w.apply_rows(self.recs, self.rows); rep = w.apply_rows(self.recs, self.rows)
        self.assertEqual(self.recs, after); self.assertEqual((rep['changed'], rep['created']), ([], []))

HATS = '''# Dimonka Headgear Quests

**Content type:** [uaRO](whats-different.md#content-tags)

<table>
<thead>
<tr>
<th>Headgear</th>
<th>Materials</th>
</tr>
</thead>
<tbody>
<tr>
<td><img src="../img/D/5747.gif" alt="5747"><br>Mitra [1]</td>
<td><img src="../img/7539_1.png" alt="Poring Coin"> Poring Coin - 1,500<br><img src="../img/D/7345.gif" alt="7345"> Handcuffs  - 1000<br><img src="../img/D/card.gif" alt="card"> Margaretha Sorin Card - 1</td>
</tr>
<tr>
<td><img src="../img/Ganst3.png" alt="Gangster Scarf"><br>Crimson Rose (Scarlet Rose)</td>
<td><img src="../img/7539_1.png" alt="Poring Coin"> Poring Coin - 2000<br><img src="../img/7293.gif" alt="Rose Quartz"> Rose Quartz - 10<br>weird line</td>
</tr>
<tr>
<td><img src="../img/1.gif" alt="x"><br>Glaris Doll Hat [1]</td>
<td>Poring Coin - 2000<br>Thara Frog Card - 1</td>
</tr>
<tr>
<td><img src="../img/2.gif" alt="x"><br>Nothing Hat</td>
<td>no materials here</td>
</tr>
</tbody>
</table>
'''
OFFICE = 'Welcome to Main Office. Located in the heart of the city (`/navi prontera 134/184`), Main Office is home to NPCs.'

class HeadgearPage(unittest.TestCase):
    def test_rows_ids_aliases_and_location(self):
        rows, warn = w.dimonka_headgear(HATS, read=lambda n: OFFICE); r = {x['name']: x for x in rows}
        self.assertEqual(sorted(r), ['Crimson Rose (Scarlet Rose)', 'Glaris Doll Hat [1]', 'Mitra [1]'])
        m = r['Mitra [1]']
        self.assertEqual(m['ingredients'], [{'item': 'Poring Coin', 'qty': 1500, 'item_id': 7539}, {'item': 'Handcuffs', 'qty': 1000, 'item_id': 7345}, {'item': 'Margaretha Sorin Card', 'qty': 1}])
        self.assertEqual((m['npc'], m['location'], m['content']), ('Dimonka', 'prontera 134/184', 'uaRO')); self.assertEqual(m['rewards'], {'items': [{'item_id': 5747, 'item': 'Mitra [1]', 'qty': 1}]})
        self.assertEqual(r['Crimson Rose (Scarlet Rose)']['aliases'], ['Crimson Rose', 'Scarlet Rose']); self.assertEqual(r['Crimson Rose (Scarlet Rose)']['rewards']['items'][0], {'item': 'Crimson Rose (Scarlet Rose)', 'qty': 1})   # no numeric icon, no id
        self.assertEqual(len(warn), 2); self.assertTrue(any('weird line' in x for x in warn) and any('Nothing Hat' in x for x in warn))
        rows, warn = w.dimonka_headgear(HATS, read=lambda n: ''); self.assertNotIn('location', rows[0]); self.assertTrue(any('Main Office' in x for x in warn))

    def test_matching_by_similar_name_and_hat_suffix(self):
        rows, _ = w.dimonka_headgear(HATS, read=lambda n: OFFICE)
        recs = [rec('Mitra', [('Poring Coin', 1500), ('Handcuffs', 1000), ('Margaretha Sorin Card', 1)]), rec('Scarlet Rose', [('Rose Quartz', 10)]), rec('Glaris Doll', [('Thara Frog Card', 1)]), rec('Defolty Doll', [('Thara Frog Card', 1)])]
        rep = w.apply_rows(recs, rows)
        self.assertEqual(rep['by_similar_name'], ['Mitra [1] -> Mitra', 'Glaris Doll Hat [1] -> Glaris Doll'])   # the ' Hat' suffix and the slot are ignored, once
        self.assertEqual(rep['by_name'], ['Crimson Rose (Scarlet Rose) -> Scarlet Rose'])                        # the bracketed alias is the record's name
        self.assertEqual(recs[0]['rewards']['items'][0]['item_id'], 5747); self.assertNotIn('npc', recs[3])
        self.assertEqual(len(rep['ingredient_diffs']), 2)   # the sheet has no Poring Coin on these two, the wiki does

    def test_two_wiki_rows_cannot_claim_one_record(self):
        rows = [{'name': 'Alice Doll [1]', 'npc': 'D', 'ingredients': [], 'categories': []}, {'name': 'Alice Doll Hat', 'npc': 'E', 'ingredients': [], 'categories': []}]
        recs = [rec('Alice Doll', [('Soft Apron', 3)])]; rep = w.apply_rows(recs, rows)
        self.assertEqual(recs[0]['npc'], 'D'); self.assertEqual(len(rep['ambiguous']), 1); self.assertIn('already matched', rep['ambiguous'][0])

    def test_slot_zero_is_the_same_item_but_slot_one_is_not(self):
        self.assertEqual(w.ing_key([{'item': 'Kitty Band [0]', 'qty': 1}]), w.ing_key([{'item': 'Kitty Band', 'qty': 1}]))
        self.assertNotEqual(w.ing_key([{'item': 'Majestic Goat [1]', 'qty': 1}]), w.ing_key([{'item': 'Majestic Goat', 'qty': 1}]))

    def test_reward_dicts_merge_key_by_key(self):
        recs = [rec('Nutters Repeatable Quest', [('Acorn', 25)], rewards={'base_exp': 1})]
        rep = w.apply_rows(recs, [{'name': 'Nutters Repeatable Quest', 'ingredients': [], 'rewards': {'base_exp': 2, 'items': [{'item': 'X', 'qty': 1}]}}])
        self.assertEqual(recs[0]['rewards'], {'base_exp': 1, 'items': [{'item': 'X', 'qty': 1}]}); self.assertEqual(rep['differs'], ["Nutters Repeatable Quest: rewards.base_exp is 1, wiki says 2"])

    def test_reward_items_reach_the_index_as_gives(self):
        rows, _ = w.dimonka_headgear(HATS, read=lambda n: OFFICE); recs = [rec('Mitra [1]', [('Poring Coin', 1500)])]; w.apply_rows(recs, rows[:1])
        with tempfile.TemporaryDirectory() as t:
            Path(f'{t}/d.json').write_text(json.dumps({'quests': recs})); out = bq.uaro_rows(f'{t}/d.json')[0]
            self.assertEqual([(i['relation'], i['item'], i['item_name'], i['qty']) for i in out['items']], [('takes', None, 'Poring Coin', 1500), ('gives', 5747, 'Mitra [1]', 1)])
            Path(f'{t}/q.jsonl').write_text(json.dumps(out) + '\n'); old = q.IDX; q.IDX = f'{t}/q.jsonl'; buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf): q.main(['Mitra'])
            finally: q.IDX = old
        self.assertIn('gives 1 x Mitra [1] (5747)', buf.getvalue()); self.assertNotIn('rewards:', buf.getvalue())   # items are not shown as EXP

    def test_pages_missing_from_the_wiki_are_skipped_unless_asked_for(self):
        with tempfile.TemporaryDirectory() as t:
            Path(f'{t}/wiki').mkdir(); Path(f'{t}/wiki/dimonka-headgear-quest.md').write_text(HATS); Path(f'{t}/d.json').write_text(json.dumps({'about': '', 'quests': []}))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf): w.main(['--wiki', f'{t}/wiki', '--data', f'{t}/d.json'])
            self.assertIn('repeatable-quests.md not found', buf.getvalue()); self.assertIn('Mitra [1]', Path(f'{t}/d.json').read_text())
            with self.assertRaises(SystemExit): w.main(['--wiki', f'{t}/wiki', '--data', f'{t}/d.json', '--page', 'repeatable-quests'])

FROG = '''# 🐸 King Frog Hat Quest

A **Mysterious Boy** has appeared, offering to help you craft the ![Frog Hat](img/5528.gif) **King Frog Hat [1]**! You can find him at: `/navi beach_dun3 213/99`.

| **Item**                                 | **Quantity** |
|------------------------------------------|--------------|
| ![Frog Hat](img/5447.gif) **Frog Hat**   | x1           |
| ![Pearl](img/722.png) **Pearl**          | x100         |
| ![Card](img/card-1.gif) **Poisonous Toad Card** | x1    |
| **Broken** | lots |

| Item | Where to farm |
|---|---|
| Pearl | Clam |

Once you present the items, he will reward you with the ![Frog Hat](img/5528.gif) **King Frog Hat [1]**.
'''

class ProsePage(unittest.TestCase):
    def test_row(self):
        rows, warn = w.king_frog_hat(FROG); r = rows[0]
        self.assertEqual(r['name'], 'King Frog Hat Quest'); self.assertEqual(r['aliases'], ['King Frog Hat', 'King Frog Hat [1]'])
        self.assertEqual((r['npc'], r['location']), ('Mysterious Boy', 'beach_dun3 213/99'))
        self.assertEqual(r['ingredients'], [{'item': 'Frog Hat', 'qty': 1, 'item_id': 5447}, {'item': 'Pearl', 'qty': 100, 'item_id': 722}, {'item': 'Poisonous Toad Card', 'qty': 1}])
        self.assertEqual(r['rewards'], {'items': [{'item_id': 5528, 'item': 'King Frog Hat [1]', 'qty': 1}]}); self.assertEqual(len(warn), 1); self.assertIn('Broken', warn[0])

    def test_incomplete_pages_warn(self):
        self.assertEqual(w.king_frog_hat('no title here'), ([], ['no title found']))
        rows, warn = w.king_frog_hat('# Hat Quest\n\nNo table.'); self.assertEqual(rows, []); self.assertIn('no materials table', warn[0])
        rows, warn = w.king_frog_hat(FROG.replace('reward you with', 'give you').replace('`/navi beach_dun3 213/99`', 'the cave'))
        self.assertEqual([x for x in warn if 'Broken' not in x], ['King Frog Hat Quest: no NPC and /navi spot found', 'King Frog Hat Quest: no reward item found']); self.assertNotIn('npc', rows[0])

    def test_matches_an_existing_record_by_its_reward_or_becomes_new(self):
        rows, _ = w.king_frog_hat(FROG); recs = [rec('King Frog Hat', [('Pearl', 100)])]; rep = w.apply_rows(recs, rows)
        self.assertEqual(rep['by_name'], ['King Frog Hat Quest -> King Frog Hat'])   # the title minus ' Quest' is the record's name; self.assertEqual(recs[0]['npc'], 'Mysterious Boy'); self.assertEqual(len(rep['ingredient_diffs']), 1)
        recs = []; rep = w.apply_rows(recs, rows); self.assertEqual((rep['created'], recs[0]['id'], recs[0]['source']), (['King Frog Hat Quest'], 'uaro-king-frog-hat-quest', 'wiki'))

ECW = '''# Expanded Class Weapons

### Gunslinger

| Weapon | In-game command |
|--------|-----------------|
|![32303](img/E/32303.gif) Bolt Revolver [2] | @ii 32303 |
|![35658](img/E/830001.png) Bolt Revolver [2] | @ii 35658 |

### Ninja

| Weapon | In-game command |
|--------|-----------------|
|![35659](img/E/510053.png) Fortified Dagger [2] | @ii 35659 |
| Broken | none |

| Weapon | Class |
|---|---|
| Some Weapon | Any |

### Token Creation Requirements

To create a token, you must combine:

- **1000 × Expanded Token Fragments**
- **10,000,000 Zeny**

## Expanded Token Fragments

- Dropped by monsters included in **Elite-tier Hunting Mission quests**
- **Drop Rate:** 3%

### NPC Location

All NPCs are in the eastern room (`/navi prt_in 90/72`)

- Acidus (@mi 1713)
- Draco (@mi 2013)
'''

class TokenPage(unittest.TestCase):
    def test_row(self):
        rows, warn = w.expanded_class_weapons(ECW); r = rows[0]
        self.assertEqual((r['name'], r['zeny'], r['location']), ('Expanded Class Weapons', 10000000, 'prt_in 90/72')); self.assertNotIn('npc', r)
        self.assertEqual(r['ingredients'], [{'item': 'Expanded Token Fragments', 'qty': 1000}])
        self.assertEqual(r['rewards']['items'], [{'item_id': 32303, 'item': 'Bolt Revolver [2]', 'qty': 1, 'class': 'Gunslinger'}, {'item_id': 35658, 'item': 'Bolt Revolver [2]', 'qty': 1, 'class': 'Gunslinger'}, {'item_id': 35659, 'item': 'Fortified Dagger [2]', 'qty': 1, 'class': 'Ninja'}])
        self.assertTrue(r['rewards']['choose_one']); self.assertEqual(len(warn), 1); self.assertIn('Broken', warn[0])
        self.assertIn('dropped by monsters included in Elite-tier Hunting Mission quests at 3% (2 monsters listed', r['notes'])

    def test_incomplete_pages(self):
        self.assertEqual(w.expanded_class_weapons('x'), ([], ['no title found']))
        rows, warn = w.expanded_class_weapons('# T\n\nnothing'); self.assertEqual(rows, []); self.assertIn('no token requirements', warn[-1])
        rows, warn = w.expanded_class_weapons(ECW.replace('Token Creation Requirements', 'Other').replace('NPC Location', 'Elsewhere'))
        self.assertEqual(rows, [])

    def test_shows_cost_choice_and_items_without_calling_a_flag_exp(self):
        rows, _ = w.expanded_class_weapons(ECW); recs = []; w.apply_rows(recs, rows)
        with tempfile.TemporaryDirectory() as t:
            Path(f'{t}/d.json').write_text(json.dumps({'quests': recs})); out = bq.uaro_rows(f'{t}/d.json')[0]
            Path(f'{t}/q.jsonl').write_text(json.dumps(out) + '\n'); old = q.IDX; q.IDX = f'{t}/q.jsonl'; buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf): q.main(['Expanded Class'])
            finally: q.IDX = old
        s = buf.getvalue()
        for want in ('costs: 10,000,000 zeny', 'rewards: one of the items below, your choice', 'asks for 1000 x Expanded Token Fragments', 'gives 1 x Fortified Dagger [2] (35659)'): self.assertIn(want, s)
        self.assertNotIn('choose one', s)   # the choose_one flag is not an EXP amount

DIC = '''# El Dicastes

**Content type:** [Renewal](whats-different.md#content-tags)

## Getting There

El Dicastes is reached through the Ep 13.2 quest chain. Complete the steps in order.

| Step | NPC - Location | What to do |
|---|---|---|
| `1` | **Promotional Staff** - `/navi prontera 163/53`, then `/navi geffen 90/67` | Ash Vacuum chain. The Geffen staff requires base level `70`. |
| `2` | **Schwartzvalt Mechanic** - `/navi mid_camp 197/237` | Gives the **Ring of the Ancient Wise King** after a `1` hour wait. |
| `x` | **Nobody** | broken row |

Cross the tunnel.

---

## Sapha Certificates

Base level `80` is required for every repeatable
source.

**Department dailies.** Take a request from a giver, complete it, then report to the manager. Each pays `1` Certificate plus `4,000` \u2013 `82,800` base EXP, rolled per request.

| Giver | Location | Department |
|---|---|---|
| **Laponte** | `/navi dicastes01 187/230` | Hunting `1` - kill a target |
| **Pura** | `/navi dicastes01 208/230` | Supply `1` - deliver items |

---

## Quest Chains

**Ahat's Secret** starts with **Inspector Doha** (`/navi mid_campin 168/170`). It costs `6` Certificates,
rewards `9` Unidentified Relics, **opens Scaraba Hole** and unlocks a repeatable daily worth `70,000` base EXP,
`30,000` job EXP and `1` Certificate. Type the phrase.

**Frede's Request** starts with **Frede** (`/navi dicastes01 117/262`, base level `70`). Find his friends, then bring **Bouy** (`/navi dic_in01 349/129`) `30` **Small Bradium** (Dolomedes,
`75%`). Pays `3` Certificates.

!!! warning "Finish Ahat's Secret First"
    A paragraph that is not a chain.

---

## Enchanting

| Giver | Location | Department |
|---|---|---|
| **Jahbong** | `/navi dic_fild01 228/159` | not a daily |
'''

class ElDicastes(unittest.TestCase):
    def rows(self, text=DIC):
        r, warn = w.el_dicastes(text); return {x['name']: x for x in r}, warn

    def test_dailies(self):
        r, warn = self.rows(); d = r['Laponte Daily Quest']
        self.assertEqual((d['npc'], d['location'], d['min_level'], d['content']), ('Laponte', 'dicastes01 187/230', 80, 'Renewal'))
        self.assertEqual(d['rewards'], {'base_exp_min': 4000, 'base_exp_max': 82800, 'items': [{'item': 'Sapha Certificate', 'qty': 1}]})
        self.assertTrue(d['notes'].startswith('Hunting 1 - kill a target. Take a request')); self.assertIn('Supply 1', r['Pura Daily Quest']['notes'])

    def test_chains_read_costs_hand_ins_rewards_and_the_daily(self):
        r, _ = self.rows(); a = r["Ahat's Secret"]
        self.assertEqual((a['npc'], a['location']), ('Inspector Doha', 'mid_campin 168/170')); self.assertNotIn('min_level', a)
        self.assertEqual(a['ingredients'], [{'item': 'Sapha Certificate', 'qty': 6}]); self.assertEqual(a['rewards'], {'items': [{'item': 'Unidentified Relic', 'qty': 9}]})
        self.assertIn('opens Scaraba Hole', a['notes']); self.assertIn('(/navi mid_campin 168/170)', a['notes'])   # no stray spaces where the backticks were
        self.assertEqual(r["Ahat's Secret Daily"]['rewards'], {'base_exp': 70000, 'job_exp': 30000, 'items': [{'item': 'Sapha Certificate', 'qty': 1}]})   # the sentence wraps across lines in the source
        f = r["Frede's Request"]; self.assertEqual(f['min_level'], 70)
        self.assertEqual(f['ingredients'], [{'item': 'Small Bradium', 'qty': 30, 'note': 'hand in to Bouy'}]); self.assertEqual(f['rewards'], {'items': [{'item': 'Sapha Certificate', 'qty': 3}]})
        self.assertNotIn('Finish Ahat', ''.join(r))

    def test_access_chain_steps(self):
        r, warn = self.rows(); g = r['El Dicastes: Getting There']
        self.assertEqual((g['npc'], g['location']), ('Promotional Staff', 'prontera 163/53'))
        self.assertEqual(g['steps'][0], {'step': 1, 'npc': 'Promotional Staff', 'locations': ['prontera 163/53', 'geffen 90/67'], 'what': 'Ash Vacuum chain. The Geffen staff requires base level 70.'})
        self.assertEqual(len(g['steps']), 2); self.assertEqual(g['rewards'], {'items': [{'item': 'Ring of the Ancient Wise King', 'qty': 1}]})
        self.assertEqual(g['notes'], 'El Dicastes is reached through the Ep 13.2 quest chain. Complete the steps in order.')
        self.assertEqual(len(warn), 1); self.assertIn('Nobody', warn[0])   # the unreadable step row

    def test_other_tables_are_not_quests(self):
        r, _ = self.rows()   # DIC has a Giver | Location | Department table under Enchanting too; only the one in the dailies section counts
        self.assertEqual(sorted(r), ["Ahat's Secret", "Ahat's Secret Daily", 'El Dicastes: Getting There', "Frede's Request", 'Laponte Daily Quest', 'Pura Daily Quest'])

    def test_lookup_shows_steps_ranges_and_open_ended_levels(self):
        r, _ = w.el_dicastes(DIC); recs = []; w.apply_rows(recs, r)
        with tempfile.TemporaryDirectory() as t:
            Path(f'{t}/d.json').write_text(json.dumps({'quests': recs})); Path(f'{t}/q.jsonl').write_text('\n'.join(json.dumps(x) for x in bq.uaro_rows(f'{t}/d.json')) + '\n')
            old = q.IDX; q.IDX = f'{t}/q.jsonl'; buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf): q.main(['Getting There']); q.main(['Laponte Daily']); q.main(["Ahat's Secret Daily"])
            finally: q.IDX = old
        s = buf.getvalue()
        for want in ('step 1: Promotional Staff (prontera 163/53; geffen 90/67) - Ash Vacuum chain.', 'step 2: Schwartzvalt Mechanic (mid_camp 197/237)', 'content type: Renewal', 'levels: 80+', 'rewards: 4,000-82,800 base exp',
                     'rewards: 70,000 base exp, 30,000 job exp', 'gives 1 x Sapha Certificate'): self.assertIn(want, s)
        self.assertNotIn('80-?', s)

    def test_missing_parts_warn(self):
        rows, warn = w.el_dicastes('# El Dicastes\n\nnothing here')
        self.assertEqual(rows, []); self.assertTrue(any('dailies table' in x for x in warn) and any('quest chain' in x for x in warn) and any('Getting There' in x for x in warn))
        r, warn = self.rows(DIC.replace('Each pays', 'Pays').replace('Base level', 'Level'))
        self.assertNotIn('rewards', r['Pura Daily Quest']); self.assertNotIn('min_level', r['Pura Daily Quest'])
        self.assertTrue(any('rewards sentence' in x for x in warn) and any('level requirement' in x for x in warn))

class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.t = self.tmp.name; Path(f'{self.t}/wiki').mkdir(); Path(f'{self.t}/wiki/repeatable-quests.md').write_text(PAGE)
        self.data = f'{self.t}/data.json'; Path(self.data).write_text(json.dumps({'about': 'x', 'quests': [rec('Nutters Repeatable Quest', [('Acorn', 25)])]}))
    def tearDown(self): self.tmp.cleanup()
    def run_cli(self, *a):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf): w.main(['--wiki', f'{self.t}/wiki', '--data', self.data, *a])
        return buf.getvalue()
    def load(self): return {r['name']: r for r in json.loads(Path(self.data).read_text(encoding='utf-8'))['quests']}

    def test_dry_run_writes_nothing_and_a_real_run_is_idempotent(self):
        before = Path(self.data).read_text(); out = self.run_cli('--dry-run'); self.assertIn('1 matched by name', out); self.assertEqual(Path(self.data).read_text(), before)
        self.run_cli(); once = Path(self.data).read_text(); self.assertNotEqual(once, before); self.assertIn('0 records changed', self.run_cli()); self.assertEqual(Path(self.data).read_text(), once)
        r = self.load(); self.assertEqual(r['Nutters Repeatable Quest']['rewards'], {'base_exp': 7200, 'job_exp': 7810}); self.assertTrue(r['Nutters Repeatable Quest']['is_quest'])
        self.assertEqual(list(r), sorted(r, key=str.lower))

    def test_missing_inputs_are_refused(self):
        with self.assertRaises(SystemExit): w.main(['--wiki', f'{self.t}/nowhere', '--data', self.data])
        with self.assertRaises(SystemExit): w.main(['--wiki', f'{self.t}/wiki', '--data', f'{self.t}/none.json'])

    def test_loot_sheet_reimport_keeps_wiki_quests(self):
        self.run_cli(); loot = [{'name': 'Acorn', 'itemId': 1026, 'categories': ['Cooking'], 'uses': [{'for': 'Nutters Repeatable Quest', 'qty': 25}]}]
        Path(f'{self.t}/loot.json').write_text(json.dumps(loot))
        with contextlib.redirect_stdout(io.StringIO()): imp.main(['--loot', f'{self.t}/loot.json', '--out', self.data])
        r = self.load(); n = r['Nutters Repeatable Quest']
        self.assertTrue(n['is_quest']); self.assertEqual((n['npc'], n['ingredients'][0]['item_id']), ('Nutters', 1026))   # not a quest by category, but the wiki says so
        self.assertEqual(r['Gandolf Hunting Quest']['source'], 'wiki')   # records the loot sheet does not know stay

    def test_index_and_lookup_show_the_wiki_fields(self):
        self.run_cli(); rows = {r['title']: r for r in bq.uaro_rows(self.data)}
        n = rows['Nutters Repeatable Quest']; self.assertEqual(n['npcs'], [{'name': 'Nutters', 'map': 'mjolnir_01 293/20', 'file': 'data/uaro-quests.json', 'mode': 'uaro'}])
        self.assertEqual(n['uaro_info'], {'min_level': 18, 'max_level': 60, 'rewards': {'base_exp': 7200, 'job_exp': 7810}}); self.assertEqual(n['wiki'], 'https://wiki.uaro.net/repeatable-quests/')
        out = f'{self.t}/index/quests.jsonl'; Path(out).parent.mkdir(); Path(out).write_text('\n'.join(json.dumps(r) for r in rows.values()) + '\n')
        old = q.IDX; q.IDX = out
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf): q.main(['Gandolf Hunting']); q.main(['Nutters Rep'])
            s = buf.getvalue()
        finally: q.IDX = old
        self.assertEqual([i['item_name'] for i in rows['Nutters Repeatable Quest']['items'] if i['relation'] == 'gives'], [])
        for want in ('levels: 45-80', 'rewards: 550,000 base exp, 340,000 job exp (for 50 kills)', 'hunt: 50/100/150 x Remover  (map needs a quest to enter)', 'NPCs: Gandolf (lhz_dun01 146/287, uaro)', 'wiki: https://wiki.uaro.net/repeatable-quests/', 'levels: 18-60', 'asks for 25 x Acorn'): self.assertIn(want, s)

if __name__ == '__main__':
    unittest.main()
