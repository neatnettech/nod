# Nod

[![CI](https://github.com/neatnettech/nod/actions/workflows/ci.yml/badge.svg)](https://github.com/neatnettech/nod/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/nod-cli)](https://pypi.org/project/nod-cli/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Buy me a coffee](https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow?logo=buymeacoffee)](https://buymeacoffee.com/neatnettech)

Git-native project management for humans and coding agents.

Nod lives in your repository: project state is stored in `.nod/nod.db` at
the root of the main checkout, so the plan travels with the code. Every git
worktree and subdirectory shares that one database; set `NOD_DB` to use a
different file. Humans drive it through a focused CLI, coding agents drive
the same state through an MCP server.

## Install

```bash
# released version from PyPI (both nod and nod-mcp on PATH)
pipx install nod-cli

# bleeding edge, straight from main
pipx install git+https://github.com/neatnettech/nod.git
```

After a PyPI release, update with `pipx upgrade nod-cli`. For git installs,
run `pipx reinstall nod-cli` to pick up new commits.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

mkdir demo && cd demo
git init
nod init
```

## Concepts

* **Modules** group work by area: `nod module add "Vault"`
* **Cycles** are timeboxed plans: `nod cycle add "Sprint 1" --start 2026-10-01 --end 2026-10-14`
* **Work items** are epics, stories, tasks, and bugs:
  `nod task add "Seed categories" --module vault --cycle sprint-1 --estimate 2h`
* **Epics** group work that ships together: `nod task add "Slice" --parent OSS-110`
  or `nod task set OSS-133 --parent OSS-110` (`--no-parent` detaches). The parent must be
  an epic, never the item itself, never a loop. `nod task list --parent OSS-110` lists the
  children and `nod task show OSS-110` shows them. Closing an epic leaves children alone.
* **Dependencies** order the work: `nod depends OSS-2 OSS-1`
* **Branch flow** says where the work lives and goes: `--branch` plus optional
  `--from-branch` (the branch or tag it is cut from) and `--to-branch` (where it
  merges), for example `nod task set OSS-2 --from-branch chore/ground --to-branch main`
  for a long lived branch that lands on main later
* **Due dates** are optional per item: `--due 2026-10-16` on `task add` and `task set`
  (an empty value clears it); an open item past its date shows as OVERDUE in
  `nod task list` and `nod graph`
* **Statuses** move one step at a time: `backlog` > `todo` > `in_progress` > `done`.
  `hold` is the blocked side step, entered from and left to `in_progress`. Work can be
  handed back (`in_progress` or `hold` to `todo`, `todo` to `backlog`), a `done` item
  reopens to `in_progress` or `todo`, and `cancelled` is reachable from any open status
  and revives to `backlog` or `todo`. A skipped stage is refused with the statuses that
  are allowed next. A new item starts as `backlog`, `todo` or `in_progress`
* **Timestamps** are UTC and follow the moves: `created_at`, `started_at` (the first move
  to `in_progress`; hold, resume and reopen keep it, handing the item back clears it)
  and `completed_at` (set on `done`, cleared on reopen). `--started-at` and
  `--completed-at` on `task set` take ISO 8601 to backdate (another zone is converted
  to UTC, an empty value clears) and must fit the stage: no start before the item has
  started, no completion unless it is done, never a completion before the start. Cycle
  time is completed minus started. Dates such as due and overdue use the UTC day too
* **Status history** records every move (from, to, when) in the same commit as the move.
  `nod task show` lists it, `--json` and the MCP get tool return it as `history`. It
  gives the time each finished stage took, so time on hold is told apart from time in
  progress. Backdating `--started-at` or `--completed-at` does not rewrite the history,
  and items that moved before the history existed have none
* **Agent context** points an item at the plan and memory files an LLM wrote for it:
  `nod task set NOD-3 --plan ~/.claude/plans/x.md --memory .claude/memory/nod.md`
  (an empty value clears it), so a fresh session can pick the work back up

## Views

```bash
nod task list                    # tabular work items
nod module list                  # modules
nod cycle list                   # cycles
nod board                        # kanban grouped by status
nod timeline                     # cycles over time with estimates
nod cycle report sprint-1 --open # printable HTML sprint report (--out path)
nod serve --open                 # live dashboard: in progress now, cycles, items per cycle
nod graph                        # ASCII dependency diagram
```

`board`, `graph` and `task list` cut by area or release with `--module <slug>` and
`--cycle <slug>` (an unknown slug is an error). A filtered graph still names the
prerequisites it does not draw (`needs NOD-7 outside this view`). Items not yet
placed in a module or a cycle are flagged ORPHANED, and `--orphaned` shows only them.

On the board each item's ID takes its module's colour and its title ends with its
cycle's letter (`[A]`, `[B]`, in date order); a legend under the board explains the
colours and letters shown. `nod board --json` names each item's module and cycle.

`nod serve --port 8765` is optional: a read only dashboard on localhost that reloads
itself as humans and agents move work. It shows what is in progress right now (with
branch and plan), every cycle with its progress, and the items of each open cycle by
status. Each cycle links to its full report at `/cycle/<slug>`; items in no cycle live
at `/unplanned`. Every item is clickable and opens `/item/<identifier>`: its facts,
description, epic, children and dependencies. Cycles and the header show the average
cycle time and, from the status history, the average time actually worked (hold left
out); in progress cards show when work started, a feed the latest moves, and an item
page its full history with the time per stage. The current cycle is the active one, else the one whose dates include
today; `nod serve <slug>` picks it by hand.

The dependency graph renders as a tree of prerequisite arrows with status
glyphs and branch names:

```
OSS-1  StateBadge component  ✓ DONE  ⎇ feat/oss-1-statebadge
OSS-3  Seed categories       ○ TODO
├─► OSS-4  Vault home        ◐ IN_PROGRESS  (depends on this)
└─► OSS-6  Note editor       ○ TODO         (depends on this)
```

Every view accepts `--json` for scripting and agents.

## Agents

`nod-mcp` exposes the same state as MCP tools: work item create/update/list,
project info, the board, the timeline, and the dependency graph. Work item
create/update take a `parent` epic (an empty value detaches), list filters by it,
and get returns the item's `children`. Point your
MCP client at `nod-mcp` from inside the repository.

## Development

```bash
pip install -e ".[dev]"
pytest
```

To watch the dashboard move, `python scripts/sandbox.py` builds a throwaway project in
`tmp/sandbox` (modules, three cycles, an epic, dependencies), serves it, opens the
browser and plays a scripted sprint: two agents picking up work, a blocked item, the
cycle rolling over. `--step 1` plays faster, `--seed-only` leaves the moves to you or
to an agent started inside `tmp/sandbox`.

Schema changes ship as append only `MIGRATIONS` in
`src/nod/infrastructure/database.py`, tracked by SQLite's `user_version`, so an
existing `.nod/nod.db` upgrades in place on its next command.

Releases: tag a version (`v0.1.0-rc.1`, then `v0.1.0`) and push it. The
`publish` workflow builds the version from the tag and publishes to PyPI via
trusted publishing. Requires Python 3.13+.
