"""Pretty printing. Color only reaches a real terminal, so piped output stays plain."""

import os
import re
import sys
import textwrap
from collections import Counter

from .models import Entry

_ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")

DIM, RED, GREEN, BOLD = "2", "31", "32", "1"


def use_color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"


def _clean(text: str) -> str:
    # Pasted errors often carry color codes, and a shared file shouldn't get to drive your terminal.
    return _CONTROL_RE.sub("", _ANSI_RE.sub("", text))


def _line(text: str) -> str:
    return " ".join(_clean(text).split())


def _top_five(title: str, counts: Counter) -> list[str]:
    if not counts:
        return []
    top = counts.most_common(5)
    width = max(len(name) for name, _ in top)
    return ["", title, *(f"   {name.ljust(width)}  {'▇' * min(n, 30)} {n}" for name, n in top)]


def format_stats(entries: list[Entry]) -> str:
    revived = sum(e.status == "revived" for e in entries)
    tags = Counter(_line(t).casefold() for e in entries for t in e.tags)
    # Areas are free text, and one entry can name several: "deps · requirements.txt".
    areas = Counter(_line(part) for e in entries for part in re.split(r"[,·]", e.area or "") if part.strip())
    return "\n".join(
        [
            f"🪦 {len(entries) - revived} dead · 🌱 {revived} revived",
            *_top_five("🏷  Most common tags", tags),
            *_top_five("👻 Most haunted", areas),
        ]
    )


def format_entry(entry: Entry, full: bool = False, color: bool = False) -> str:
    """One entry as a small block. `full` adds the error snippet and the exact time."""

    def paint(text, code):
        return f"\x1b[{code}m{text}\x1b[0m" if color else text

    revived = entry.status == "revived"
    icon = "🌱" if revived else "🪦"
    title = f"{icon} #{entry.id}  {_line(entry.attempt)}" + ("  (revived)" if revived else "")
    lines = [
        paint(title, GREEN if revived else BOLD),
        paint(f"   ✗ Why it failed: {_line(entry.why_failed)}", RED),
    ]
    if entry.area:
        lines.append(f"   📁 Area: {_line(entry.area)}")
    if entry.tags:
        lines.append(f"   🏷  tags: {_line(', '.join(entry.tags))}")
    if entry.note:
        lines.append(f"   📝 Note: {_line(entry.note)}")
    if full and entry.error_snippet:
        lines.append("   ⚠️  Error:")
        lines.append(paint(textwrap.indent(_clean(entry.error_snippet).rstrip(), "      "), DIM))
    when = _line(entry.created_at) if full else _line(entry.created_at)[:10]
    byline = f" · by {_line(entry.author)}" if entry.author else ""
    lines.append(paint(f"   🕐 {when}{byline}", DIM))
    return "\n".join(lines)
