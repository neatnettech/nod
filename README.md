# Nod

Git-native project management for humans and coding agents.

Nod lives in your repository: project state is stored in `.nod/nod.db`, so
the plan travels with the code. Humans drive it through a focused CLI,
coding agents drive the same state through an MCP server.

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
* **Dependencies** order the work: `nod depends OSS-2 OSS-1`

## Views

```bash
nod task list                    # tabular work items
nod module list                  # modules
nod cycle list                   # cycles
nod board                        # kanban grouped by status
nod timeline                     # cycles over time with estimates
nod graph                        # ASCII dependency diagram
```

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
project info, the board, the timeline, and the dependency graph. Point your
MCP client at `nod-mcp` from inside the repository.

## Development

```bash
pip install -e ".[dev]"
pytest
```
