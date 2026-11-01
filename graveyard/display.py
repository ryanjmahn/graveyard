"""Pretty printing. Color only reaches a real terminal, so piped output stays plain."""

import os
import re
import sys
import textwrap

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
