# game-data-tools

Small command-line tools for checking game database values. They read local copies of public emulator databases and saved web pages, line the sources up side by side, and flag where they disagree, so a value is confirmed from more than one place before it goes into documentation.

Nothing here contains game data. The databases are cloned and the pages are saved on your machine, and both are ignored by git.

## What it does

| Tool | Use |
|---|---|
| `bin/compare_item.py <id or name>` | Compare an item across the databases, a saved page, the client item file and your docs |
| `bin/compare_mob.py <id or name>` | Compare a monster the same way |
| `bin/compare_skill.py <constant, name or id>` | Compare a skill and show which class learns it and whether it is a quest skill (`--quest` lists them all) |
| `bin/drops.py <item>` / `--mob <monster>` | Which monsters drop an item, or what a monster drops |
| `bin/parse_iteminfo.py <id or name>` | Descriptions, slots and view IDs from a client item file (`--view N` for the items using a view ID) |
| `bin/parse_sprites.py <id or name>` | Look up sprite IDs in saved sprite lists (`--gaps` lists missing headgear view IDs) |
| `bin/parse_irowiki_item.py <id>` | Parse a saved item page |
| `bin/classify_images.py` | Say whether each wiki image is an item icon or a monster picture, with the evidence |
| `bin/list_wanted_items.py` | List the items your wiki and loot sheet need icons for |
| `bin/build_item_images.py` | Build the `item<ID>.gif` icon collection (and `mob<ID>.gif`) from your image folders |
| `bin/fetch_item_icons.py` | Download missing item icons from RateMyServer or Divine Pride |
| `bin/backup_collection.py` | Back up `images/` and `notes/` into a verified, timestamped archive (keeps the newest 10; `--also` copies elsewhere) |
| `bin/quests.py <id or title>` | Look up a quest: client text, kill targets, NPCs, the items it asks for and gives (`--item`, `--mob`, `--stats`) |
| `bin/build_quests.py` | Build the quest index from the client quest list, the emulator quest databases and NPC scripts |
| `bin/save_page.sh <url>` | Save a page byte-for-byte with a metadata file |
| `bin/fetch_iteminfo.sh` | Download the client item file (variant and version selectable) |
| `bin/fetch_sprites.sh` | Save all the ai4rei sprite list pages |

The compare tools search a `docs/` folder for mentions of the thing you looked up. Run them from the repo you are documenting, or set `DOCS_DIR`; the tools say so when the folder is missing. The closing "Precedence" line names which source wins when they disagree. Set `PRECEDENCE` to your own order, or to an empty string to hide it.

## Setup

1. Install Python 3 and PyYAML (`pip install -r requirements.txt`).
2. Run `./setup.sh`. It clones the Hercules (`stable`) and rAthena (`master`) databases and builds whatever indexes it can.
3. Client item descriptions come from the [ROenglishRE](https://github.com/llchrisll/ROenglishRE) project's `itemInfo.lua`. `setup.sh` runs `bin/fetch_iteminfo.sh`, which saves it to `pages/downloads/itemInfo.lua` with a `.meta` file recording the exact commit. Set `ITEMINFO_VARIANT=Pre-Renewal` for the pre-renewal translation (default `Renewal`) and `ITEMINFO_REF=<branch, tag or commit>` to pin or update a version (default `master`). An existing file is kept unless the variant or ref you ask for differs. Then run `bin/parse_iteminfo.py --index`. The index records which variant and commit it was built from (`index/iteminfo.meta`). Lookups print that on the first line, and warn if the downloaded file has changed since the index was built.
4. Sprite lists: `setup.sh` runs `bin/fetch_sprites.sh`, which saves the ai4rei viewlist and all npclist pages (`nn.ai4rei.net/dev/viewlist/` and `nn.ai4rei.net/dev/npclist/?qq=0..N`, about 150 pages and a couple of minutes) and then `bin/parse_sprites.py --index` builds the index. It also saves the dotalux npclist (`dotalux.com/ro/npclist/`) if reachable. The index builders stop with a clear error if a file is missing or nothing parses, and keep the previous index.

Set `GAME_DATA` to keep the data somewhere other than this folder.

## Quests

`setup.sh` downloads the ROenglishRE quest list (`bin/fetch_quest_text.sh`) and runs `bin/build_quests.py`, which merges it with rAthena's quest databases and NPC scripts into `index/quests.jsonl` (about 11,000 quests). Item facts come from the NPC scripts, which are code, so they are heuristic: an item is attached to the nearest quest the NPC mentions, and each one shows the NPC, map and file so you can check it. They describe the official game, not uaRO's own changes.

uaRO's own quests (hat, weapon, pet and other quests) are not in any emulator script. They live in `data/uaro-quests.json`, which this repo owns and which is committed. `bin/import_loot_sheet.py --loot <loot.json>` seeds and refreshes it from the loot sheet's "used for" lists; fields you add by hand (npc, location, wiki, notes) survive a re-import. `build_quests.py` adds those records to the index as quests with ids like `uaro-mystic-rose`.

## Reading the output

- Monster and skill tables compare Hercules against rAthena within each mode (`[re] Exp: ...`). Differences between pre-renewal and renewal are listed on one separate line, because they are expected.
- A field a database leaves out takes that project's documented default (rAthena monster stats default to 1, Hercules to 0; size Small vs Medium), so a blank is not mistaken for a difference.
- In the docs list, lines containing the ID come first, and a numbered variant (`Field Manual 100%`) is not counted as a mention of `Field Manual`.
- A name that is not found prints close names, ignoring case, spaces and punctuation (`Yggdrasilberry` finds `Yggdrasil Berry`).

## Tests

```bash
python3 -m unittest discover -s tests
```

The tests use small inline fixtures (a fake `curl` stands in for the network) and need no downloaded data (PyYAML is required).

## Notes on the data

- Emulator values are the official values. They show nothing about what a private server changed, so check those against your server's own patch notes.
- The client item file follows the current client, which is usually renewal values. A difference from the pre-renewal database is expected for items renewal changed.
- Emulator weights are divided by 10 to match in-game units. A missing sell price is shown as the buy price divided by 2.
- Saved pages are never modified. Keep your own notes about a page in `notes/`, which is also ignored by git.

## Licence

MIT for the code. The data belongs to its original projects and sites, so don't republish it.
