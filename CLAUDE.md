# CLAUDE.md

Guidance for Claude Code in this repo. Setup and the tool list are in README.md.

## Where this repo sits

Three repos work together. Each has its own CLAUDE.md or AGENTS.md; read the one for the repo you are changing, and don't carry one repo's rules into another.

| Repo | Path | What it holds | Flows to the others |
|---|---|---|---|
| game-data-tools (this one) | `~/Projects/game-data-tools` | emulator databases, saved pages, the image collection (`images/`), `data/uaro-quests.json` | item icons and monster pictures, lookups, quest data |
| uaro-docs | `~/Projects/uaro-docs` | the uaRO wiki (wiki.uaro.net); a fork of `Privettema/uaro-docs`, `main` kept in step with upstream by `~/.local/bin/sync-uaro-docs` | pages that name items, monsters and quests; images this collection ingests |
| uaro-loot-sheet | `~/Projects/uaro-loot-sheet` | `src/data/loot.json`, uaRO overrides, the item icons it copies with `npm run sync:icons` | items and drop data the wiki should agree with |

Run all game-data tools with `GAME_DATA=/Users/jax/Projects/game-data-tools`. In a worktree, `images/`, `rathena/` and `notes/` don't exist (they are git-ignored), so without it the tools look in the wrong place.

## Keeping the repos in step

`bin/repo_changes.py` tracks the tip of `main` in all three repos and reports, since the last baseline, which changed files mean follow-up elsewhere (new patch notes, quest pages, loot sheet items, overrides) and which item or monster ids the changes mention that have no picture yet.

- Run it at the start of cross-repo work, and after the wiki or loot sheet changes.
- It repeats the same report until you run `bin/repo_changes.py --ack`. Acknowledge only once the follow-ups are done or deliberately skipped.
- Add a rule to `RULES` in the script when a new kind of dependency shows up, with a test.

## Agents and handoffs

Use an agent for wide, independent, read-only sweeps (auditing wiki pages against the data, checking loot sheet drops against `drops.py`). Do small, sequential edits yourself.

An agent starts cold, so it can't rely on this conversation:

1. Give it the repo paths it needs, the `GAME_DATA` value, and the exact question.
2. Have it write its findings to `notes/handoff/<YYYY-MM-DD>-<task>.md` in `~/Projects/game-data-tools` as it goes, not only in its reply. Findings need the source for each claim (database file, wiki page, line).
3. Say in the file what was checked, what was not, and what is unconfirmed for uaRO. Emulator values are official iRO values, not uaRO's.
4. When you act on a handoff, add a line at the top: done, skipped or still open.

`notes/` is git-ignored and `bin/backup_collection.py` backs it up, so handoffs survive between sessions.

## Rules that apply everywhere

- Use the classic class names (Whitesmith, Creator, Professor, Clown, Star Gladiator).
- Event content (event items, event quests) stays out of the loot sheet and `data/uaro-quests.json`.
- Work on a branch and merge on approval; no PRs here. Commit as `rhya`, with no Co-Authored-By line.
- Don't push, deploy or merge in any of the repos unless asked.
