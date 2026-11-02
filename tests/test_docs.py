"""The landing page repeats things the code owns, so hold it to them."""

import html
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from graveyard import cli
from graveyard.models import Entry
from graveyard.search import search_entries

PAGE = (Path(__file__).resolve().parent.parent / "docs" / "index.html").read_text(encoding="utf-8")
QUERIES = ["numpy", "flaky test", "upgrade pandas", "ci", "auth", "torch", "dep", "the", "fix the numpy warning", "!!!", "zzz"]


def test_the_snippet_matches_graveyard_init():
    assert cli.CLAUDE_SNIPPET in html.unescape(PAGE)


def test_every_command_is_on_the_page():
    commands = cli._parser()._subparsers._group_actions[0].choices
    assert all(f"graveyard {name}" in PAGE for name in commands)


@pytest.mark.skipif(not shutil.which("node"), reason="needs node to run the page's script")
def test_demo_ranks_the_same_as_the_real_search():
    script = re.search(r"<script>(.*?)</script>", PAGE, re.DOTALL)[1]
    logic = script[: script.index("// Pixel sprites")]  # everything before the code that touches the page
    run = logic + f"console.log(JSON.stringify({{entries: ENTRIES, results: {json.dumps(QUERIES)}.map(q => searchEntries(q).map(e => e.id))}}))"
    data = json.loads(subprocess.run(["node", "-e", run], check=True, capture_output=True, text=True).stdout)
    entries = [Entry.from_dict(e) for e in data["entries"]]
    for query, expected in zip(QUERIES, data["results"]):
        assert [e.id for e in search_entries(entries, query)] == expected, query
