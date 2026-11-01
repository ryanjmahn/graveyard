"""Finding entries."""

from .models import Entry


def filter_entries(entries: list[Entry], tag: str | None = None, area: str | None = None) -> list[Entry]:
    """Newest first. Tags match exactly and areas by substring, both ignoring case."""
    if tag:
        entries = [e for e in entries if tag.casefold() in (t.casefold() for t in e.tags)]
    if area:
        entries = [e for e in entries if area.casefold() in (e.area or "").casefold()]
    # Timestamps, not file order: a git merge can shuffle the lines.
    return sorted(entries, key=lambda e: (e.created_at, e.id), reverse=True)
