"""The README makes promises a reader will copy and paste, so hold it to them."""

import re
from pathlib import Path

from graveyard import cli, display, mcp_server
from graveyard.models import Entry

README = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")


def test_the_snippet_matches_graveyard_init():
    assert cli.CLAUDE_SNIPPET in README


def test_the_example_entry_is_real_output():
    entry = Entry(
        id=12,
        attempt="Bumped numpy to 2.x to fix the dtype warning",
        why_failed="broke torch 2.1 (ABI mismatch on import)",
        area="deps · requirements.txt",
        tags=["numpy", "torch", "dependencies"],
        author="claude-code",
        created_at="2026-11-01T00:00:00+00:00",
    )
    assert display.format_entry(entry) in README


def test_every_command_is_documented():
    commands = cli._parser()._subparsers._group_actions[0].choices
    assert set(commands) == set(re.findall(r"^\| `graveyard (\w+)", README, re.MULTILINE))


def test_every_add_flag_is_documented():
    add = cli._parser()._subparsers._group_actions[0].choices["add"]
    flags = {o for a in add._actions for o in a.option_strings} - {"-h", "--help"}
    assert all(flag in README for flag in flags)


def test_every_tool_is_documented():
    tools = {t.name for t in mcp_server.mcp._tool_manager.list_tools()}
    assert tools == set(re.findall(r"^\| `(\w+_dead_ends?)\(", README, re.MULTILINE))
