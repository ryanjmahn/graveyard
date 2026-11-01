"""The shape of a dead-end entry, and the rules it has to follow."""

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone

STATUSES = ("dead", "revived")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Entry:
    id: int
    attempt: str
    why_failed: str
    created_at: str = field(default_factory=now_iso)
    status: str = "dead"
    area: str | None = None
    tags: list[str] = field(default_factory=list)
    error_snippet: str | None = None
    author: str | None = None
    note: str | None = None

    def __post_init__(self):
        if type(self.id) is not int or self.id < 1:
            raise ValueError(f"id must be a positive integer, got {self.id!r}")
        for name in ("attempt", "why_failed"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")
        if self.status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}, got {self.status!r}")
        if not isinstance(self.tags, list) or not all(isinstance(t, str) for t in self.tags):
            raise ValueError("tags must be a list of strings")

    @classmethod
    def from_dict(cls, data: dict) -> "Entry":
        # Ignore unknown keys so an older install can still read a newer file.
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> dict:
        # Leave out empty optional fields to keep lines short and diffs readable.
        return {k: v for k, v in asdict(self).items() if v not in (None, [])}
