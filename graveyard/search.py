"""Finding entries."""

import re

from .models import Entry

_WORD_RE = re.compile(r"\w+")
# Agents search in sentences; these would otherwise match nearly every entry.
_STOPWORDS = frozenset("a an and are as at be but by for from if in into is it not of on or that the this to was with".split())
# Short, precise fields count for more than long free text.
_WEIGHTS = {"tags": 8, "area": 6, "attempt": 3, "why_failed": 2, "error_snippet": 1}


def _terms(query: str) -> list[str]:
    words = _WORD_RE.findall(query.casefold())
    # A query of nothing but stopwords ("the") still means something to whoever typed it.
    return list(dict.fromkeys(w for w in words if w not in _STOPWORDS)) or list(dict.fromkeys(words))


def _field_text(entry: Entry, name: str) -> str:
    return " ".join(entry.tags) if name == "tags" else getattr(entry, name) or ""


def _term_score(term: str, entry: Entry) -> float:
    """The term's best match in the entry: a whole word counts fully, part of a word half."""
    best = 0.0
    for name, weight in _WEIGHTS.items():
        text = _field_text(entry, name).casefold()
        if term in _WORD_RE.findall(text):
            best = max(best, weight)
        # Too short to trust inside a word: "ci" is in "decision".
        elif len(term) >= 3 and term in text:
            best = max(best, weight / 2)
    return best


def search_entries(entries: list[Entry], query: str, area: str | None = None, tags: list[str] | None = None) -> list[Entry]:
    """Entries matching any query word: most words matched first, then best fields, then newest."""
    entries = filter_entries(entries, area=area)
    if tags:
        wanted = {t.casefold() for t in tags}
        entries = [e for e in entries if wanted & {t.casefold() for t in e.tags}]
    terms = _terms(query)
    scored = []
    for entry in entries:
        scores = [s for s in (_term_score(term, entry) for term in terms) if s]
        if scores:
            scored.append((len(scores), sum(scores), entry))
    # sorted() is stable, so equal scores stay newest first from filter_entries.
    return [entry for _, _, entry in sorted(scored, key=lambda s: s[:2], reverse=True)]


def filter_entries(entries: list[Entry], tag: str | None = None, area: str | None = None) -> list[Entry]:
    """Newest first. Tags match exactly and areas by substring, both ignoring case."""
    if tag:
        entries = [e for e in entries if tag.casefold() in (t.casefold() for t in e.tags)]
    if area:
        entries = [e for e in entries if area.casefold() in (e.area or "").casefold()]
    # Timestamps, not file order: a git merge can shuffle the lines.
    return sorted(entries, key=lambda e: (e.created_at, e.id), reverse=True)
