"""Drives the server the way an agent does: a real subprocess, speaking MCP over stdio."""

import asyncio
import sys

import pytest
from mcp import Client, StdioServerParameters

from graveyard.storage import append_entry, entries_path, read_entries, revive_entry


def session(cwd, steps, env=None):
    """Run async steps(client) against a freshly started server."""
    server = StdioServerParameters(command=sys.executable, args=["-m", "graveyard.mcp_server"], cwd=str(cwd), env=env)

    async def run():
        async with Client(server) as client:
            return await steps(client)

    return asyncio.run(run())


def call(cwd, tool, env=None, **arguments):
    async def steps(client):
        return await client.call_tool(tool, arguments)

    return session(cwd, steps, env)


def text(result):
    return result.content[0].text


@pytest.fixture
def repo(tmp_path):
    (tmp_path / ".git").mkdir()
    return tmp_path


def test_agent_discovers_the_four_tools_with_guidance(repo):
    async def steps(client):
        return {t.name: t for t in (await client.list_tools()).tools}

    tools = session(repo, steps)
    assert set(tools) == {"search_dead_ends", "record_dead_end", "list_dead_ends", "revive_dead_end"}
    assert "BEFORE" in tools["search_dead_ends"].description
    assert "whenever an approach fails" in tools["record_dead_end"].description
    record = tools["record_dead_end"].input_schema
    assert sorted(record["required"]) == ["attempt", "why_failed"]
    assert "ctx" not in record["properties"]  # injected by the SDK, not the agent's to fill in


def test_record_saves_entry_and_names_the_client(repo):
    result = call(repo, "record_dead_end", attempt="Bumped numpy", why_failed="broke torch", area="deps", tags=["numpy"], error_snippet="boom")
    assert not result.is_error
    assert text(result) == "Recorded dead end #1."
    entry = read_entries(repo)[0]
    assert (entry.attempt, entry.area, entry.tags, entry.error_snippet) == ("Bumped numpy", "deps", ["numpy"], "boom")
    assert entry.author  # whatever name the client announced
    assert (repo / ".graveyard" / ".gitattributes").exists()


def test_record_then_search_across_sessions(repo):
    call(repo, "record_dead_end", attempt="Bumped numpy", why_failed="broke torch")
    result = call(repo, "search_dead_ends", query="numpy")
    assert "#1  Bumped numpy" in text(result) and "broke torch" in text(result)


def test_results_are_compact_text_not_doubled(repo):
    append_entry(repo, "Bumped numpy", "x", error_snippet="a very long traceback")
    result = call(repo, "search_dead_ends", query="numpy")
    assert result.structured_content is None
    assert len(result.content) == 1
    assert "\x1b" not in text(result)
    assert "traceback" not in text(result)


def test_search_filters(repo):
    append_entry(repo, "numpy one", "x", area="deps", tags=["a"])
    append_entry(repo, "numpy two", "x", area="src", tags=["b"])
    assert "two" not in text(call(repo, "search_dead_ends", query="numpy", area="deps"))
    assert "one" not in text(call(repo, "search_dead_ends", query="numpy", tags=["b"]))


def test_search_says_when_nothing_matches_or_results_are_cut(repo):
    assert text(call(repo, "search_dead_ends", query="numpy")) == "No matching dead ends."
    for i in range(12):
        append_entry(repo, f"numpy {i}", "x")
    assert "Showing 10 of 12" in text(call(repo, "search_dead_ends", query="numpy"))


def test_list_with_limit_and_filters(repo):
    append_entry(repo, "first", "x", tags=["a"])
    append_entry(repo, "second", "x", area="src")
    out = text(call(repo, "list_dead_ends", limit=1))
    assert "Showing 1 of 2" in out
    assert "first" in text(call(repo, "list_dead_ends", tag="a"))
    assert "first" not in text(call(repo, "list_dead_ends", area="src"))
    assert text(call(repo, "list_dead_ends", tag="zzz")) == "No dead ends found."


def test_revive_keeps_earlier_note_and_shows_in_search(repo):
    append_entry(repo, "numpy", "x", note="try after torch upgrade")
    assert text(call(repo, "revive_dead_end", id=1, note="torch 2.3 fixed it")) == "Revived #1."
    out = text(call(repo, "search_dead_ends", query="numpy"))
    assert "(revived)" in out and "try after torch upgrade | torch 2.3 fixed it" in out


@pytest.mark.parametrize(
    "tool, arguments, message",
    [
        ("record_dead_end", {"attempt": " ", "why_failed": "x"}, "attempt is required"),
        ("revive_dead_end", {"id": 9, "note": "n"}, "no entry #9"),
        ("revive_dead_end", {"id": 1, "note": " "}, "needs a note"),
        ("list_dead_ends", {"limit": 0}, "limit must be"),
    ],
)
def test_bad_calls_tell_the_agent_why(repo, tool, arguments, message):
    append_entry(repo, "a", "b")
    before = entries_path(repo).read_text()
    result = call(repo, tool, **arguments)
    assert result.is_error and message in text(result)
    assert entries_path(repo).read_text() == before


def test_duplicate_id_error_reaches_the_agent(repo):
    append_entry(repo, "a", "b")
    path = entries_path(repo)
    path.write_text(path.read_text() * 2)
    result = call(repo, "revive_dead_end", id=1, note="n")
    assert result.is_error and "2 times" in text(result)


def test_project_dir_env_wins_over_working_directory(repo, tmp_path_factory):
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    call(elsewhere, "record_dead_end", env={"CLAUDE_PROJECT_DIR": str(repo)}, attempt="a", why_failed="b")
    assert len(read_entries(repo)) == 1
    assert not (elsewhere / ".graveyard").exists()


def test_outside_a_repo_is_an_error_not_a_crash(tmp_path):
    result = call(tmp_path, "search_dead_ends", query="x")
    assert result.is_error and "git repo" in text(result)


def test_bad_line_in_file_doesnt_corrupt_the_protocol(repo):
    # The skip warning has to go to stderr: on stdout it would break the connection.
    append_entry(repo, "numpy", "x")
    with open(entries_path(repo), "a") as f:
        f.write("not json\n")
    assert "numpy" in text(call(repo, "search_dead_ends", query="numpy"))


def test_stored_escape_codes_never_reach_the_agent(repo):
    append_entry(repo, "numpy \x1b[31mred\x1b[0m", "x")
    revive_entry(repo, 1, "n")
    assert "\x1b" not in text(call(repo, "list_dead_ends"))
