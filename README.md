<div align="center">

# Graveyard 🪦

A log of dead ends for coding agents.

[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/ryanjmahn/graveyard?style=flat&color=black)](https://github.com/ryanjmahn/graveyard/stargazers)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-black.svg)](https://www.python.org)
[![Built with MCP](https://img.shields.io/badge/MCP-2-black.svg)](https://modelcontextprotocol.io)

</div>

Your agent tries a fix, it fails, and Graveyard records what it tried and why. The next session looks it up before trying the same thing again.

```
🪦 #12  Bumped numpy to 2.x to fix the dtype warning
   ✗ Why it failed: broke torch 2.1 (ABI mismatch on import)
   📁 Area: deps · requirements.txt
   🏷  tags: numpy, torch, dependencies
   🕐 2026-11-01 · by claude-code
```

Graveyard runs on your machine and keeps everything in a plain file in your repo. You read and write it with a CLI, and your agent does the same through an MCP server.

> **Your agent has to be told to use it.**
>
> Connecting the server gives your agent the tools, but not the habit. Paste the [`CLAUDE.md` snippet](#3-tell-your-agent-to-use-it) into your repo, or the agent has to think of the graveyard on its own.

## The problem

Coding agents keep retrying fixes that already failed, especially after their context gets compacted or a new session starts. Nothing in a new session says what the last one already ruled out, so you pay for the same mistake again.

A failed approach is worth keeping. Graveyard gives it a place to live, in the repo, next to the code it's about.

## Features

- Search before trying. Keyword search ranks an entry higher when it matches more of your words, and when they appear in its tags or area rather than its error text.
- Record on failure. One tool call saves what was tried, why it failed, and where.
- Revive. Mark an entry as having worked under different conditions. Earlier notes are kept.
- Compact results. Agents get short text, not JSON dumps, so a search doesn't eat their context.
- Shared through git. Commit `.graveyard/` and teammates and their agents get the same graveyard, or use `--private` to keep it to yourself.
- One server, every repo. Register it once, and each repo keeps its own graveyard.
- Hard to lose data. New entries are only ever appended. `revive` writes a temp file and renames it, changing only that entry's line. A line it can't read is skipped with a warning, never deleted.
- Stats. See your totals, most common tags, and most haunted areas.

## How it works

1. Your agent is about to change something, so it calls `search_dead_ends` with a few keywords.
2. Graveyard finds your repo, reads `.graveyard/entries.jsonl`, and returns the best matches.
3. If the idea is already listed as dead, the agent tries something else, or says why conditions have changed.
4. If a new approach fails, the agent calls `record_dead_end` before moving on.
5. The next session finds that entry, even though it has no memory of the failure.

The file holds one JSON object per line, so git diffs stay readable. `init` also sets git's `union` merge for it, so two branches that both add entries merge cleanly.

## Quick start

### 1. Install it

```bash
git clone https://github.com/ryanjmahn/graveyard.git
cd graveyard
python3 -m venv .venv
.venv/bin/pip install -e .
source .venv/bin/activate    # so you can type plain `graveyard`
```

Then set it up inside the repo you want a graveyard for:

```bash
cd /path/to/your/repo
graveyard init               # add --private to have git ignore it
```

Commit `.graveyard/` unless you went private.

### 2. Connect it to Claude Code

From the `graveyard` folder you cloned:

```bash
claude mcp add --scope user graveyard -- "$(pwd)/.venv/bin/graveyard-mcp"
claude mcp list              # should show graveyard as ✔ Connected
```

Start a new session to pick up the tools. The path has to be absolute, because Claude Code starts the server itself and won't have your virtualenv active.

If you only use the VS Code extension and have no `claude` command, it's included with the extension:

```bash
C=$(ls -d ~/.vscode/extensions/anthropic.claude-code-*/ | sort -V | tail -1)resources/native-binary/claude
"$C" mcp add --scope user graveyard -- "$(pwd)/.venv/bin/graveyard-mcp"
```

### 3. Tell your agent to use it

`graveyard init` prints this for you. Paste it into your repo's `CLAUDE.md`:

```md
## Graveyard (failed approaches)
- Before trying a fix or changing an area of the code, call `search_dead_ends` with relevant keywords.
- If an approach fails and you're switching to a different one, call `record_dead_end` with what you tried and why it failed.
- Don't retry anything listed as dead unless conditions have clearly changed. If you do, say why.
```

## Commands

### For your agent

| Tool | What it does |
|---|---|
| `search_dead_ends(query, area?, tags?)` | Finds matching entries, best first, up to 10 |
| `record_dead_end(attempt, why_failed, area?, tags?, error_snippet?)` | Saves an entry, with the client's name as the author |
| `list_dead_ends(limit?, tag?, area?)` | Shows recent entries, newest first |
| `revive_dead_end(id, note)` | Marks an entry as having worked after all |

Error snippets are left out of these results. `graveyard show <id>` has the full entry.

### For you

| Command | What it does |
|---|---|
| `graveyard init [--private]` | Sets up `.graveyard/` and prints the `CLAUDE.md` snippet |
| `graveyard add` | Asks for each field, or takes `--attempt --why --area --tags --error --author --note` |
| `graveyard search <query>` | Searches by keyword, with `--tag`, `--area` and `--limit` |
| `graveyard list` | Shows recent entries, with `--tag`, `--area` and `--limit` |
| `graveyard show <id>` | Shows one entry in full |
| `graveyard revive <id>` | Marks an entry as revived, keeping any earlier note |
| `graveyard stats` | Shows totals, the most common tags, and the most haunted areas |

## Known limits

- Search matches keywords, not meaning, so "dependency conflict" won't find "numpy broke torch".
- Branches that each add an entry can merge into two entries with the same id. `show` prints both, and `revive` refuses until you fix the id by hand.
- Whatever is in a committed graveyard goes into your agent's context, so review changes to that file the way you'd review code.
- It's only been run on macOS. Windows has no file locking yet, so two agents writing at the same moment could collide.

## Tech stack

- Python 3.10+
- The official [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) for the server, over stdio
- JSONL for storage, with no database
- `argparse` for the CLI
- `pytest` for the tests

## Roadmap

None of this is built yet.

- Auto-capture. Use Claude Code hooks to notice when a command fails twice in a row and nudge the agent to record a dead end.
- Semantic search. Embeddings, so "dependency conflict" matches "numpy broke torch".
- [Squeeze](https://github.com/ryanjmahn/squeeze) integration. When the log squeezer sees the same failure repeating, suggest an entry.
- Expiry. Flag old entries for a re-check after big dependency upgrades.
- Web view. A little cemetery page, one tombstone per entry 🪦
- Cross-repo graveyard. For lessons that apply everywhere.
- Stats card. Track "dead ends avoided" on the same shareable weekly card as Squeeze's tokens saved.

## Contributing

Found a bug, or a dead end Graveyard should have caught? Open an issue or send a PR. To run the tests:

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

## Credits

Made by Ryan Ahn ([@ryanjmahn](https://github.com/ryanjmahn)).

## License

MIT. See [LICENSE](LICENSE).
