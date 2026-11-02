"""The MCP server: the same graveyard as the CLI, as tools an agent can call.

Stdout carries the protocol over stdio, so nothing in here may print to it.
"""

import os

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from . import display, search, storage

MAX_SEARCH_RESULTS = 10

mcp = MCPServer(
    "graveyard",
    instructions="A log of approaches that already failed in this repo. Check it before trying a fix, and add to it when an approach fails.",
)


def _root():
    # Claude Code names the project here. Other clients get the folder they started us in.
    try:
        return storage.find_repo_root(os.environ.get("CLAUDE_PROJECT_DIR"))
    except storage.NotInRepoError as e:
        raise ToolError(f"{e}. The graveyard lives in a git repo.")


def _render(entries, limit):
    text = "\n\n".join(display.format_entry(e) for e in entries[:limit])
    if len(entries) > limit:
        text += f"\n\nShowing {limit} of {len(entries)}. Narrow the search to see the rest."
    return text


def _client_name(ctx):
    params = ctx.session.client_params
    return params.client_info.name if params else None


# structured_output=False: otherwise every result reaches the agent twice and costs context twice.
@mcp.tool(structured_output=False)
def search_dead_ends(query: str, area: str | None = None, tags: list[str] | None = None) -> str:
    """Find approaches that already failed here. Call this BEFORE attempting a fix or changing an area of the code. Use keywords like package names, files, or error text."""
    entries = search.search_entries(storage.read_entries(_root()), query, area=area, tags=tags)
    return _render(entries, MAX_SEARCH_RESULTS) if entries else "No matching dead ends."


@mcp.tool(structured_output=False)
def record_dead_end(
    attempt: str,
    why_failed: str,
    ctx: Context,
    area: str | None = None,
    tags: list[str] | None = None,
    error_snippet: str | None = None,
) -> str:
    """Save an approach that failed. Call this whenever an approach fails and you're about to try something different, so nobody repeats it."""
    root = _root()
    storage.init_store(root)
    try:
        entry = storage.append_entry(
            root, attempt, why_failed, area=area, tags=tags or [], error_snippet=error_snippet, author=_client_name(ctx)
        )
    except ValueError as e:
        raise ToolError(str(e))
    return f"Recorded dead end #{entry.id}."


@mcp.tool(structured_output=False)
def list_dead_ends(limit: int = 10, tag: str | None = None, area: str | None = None) -> str:
    """List recent failed approaches, newest first. To check a specific idea, use search_dead_ends instead."""
    if limit < 1:
        raise ToolError("limit must be 1 or more")
    entries = search.filter_entries(storage.read_entries(_root()), tag=tag, area=area)
    return _render(entries, limit) if entries else "No dead ends found."


@mcp.tool(structured_output=False)
def revive_dead_end(id: int, note: str) -> str:
    """Mark a dead end as revived because it worked under different conditions. The note says what changed."""
    try:
        entry = storage.revive_entry(_root(), id, note)
    except KeyError:
        raise ToolError(f"no entry #{id}")
    except ValueError as e:
        raise ToolError(str(e))
    return f"Revived #{entry.id}."


def main():
    mcp.run()


if __name__ == "__main__":
    main()
