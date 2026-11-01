"""Read and write .graveyard/entries.jsonl. Nothing here may lose an entry."""

import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .models import Entry

try:
    import fcntl
except ImportError:
    fcntl = None  # shortcut: no locking on Windows, use msvcrt if anyone runs it there


class NotInRepoError(Exception):
    pass


def find_repo_root(start: Path | None = None) -> Path:
    start = Path(start or Path.cwd()).resolve()
    for folder in (start, *start.parents):
        # exists(), not is_dir(): .git is a file inside worktrees and submodules.
        if (folder / ".git").exists():
            return folder
    raise NotInRepoError(f"no .git folder found at or above {start}")


def store_dir(root: Path) -> Path:
    return Path(root) / ".graveyard"


def entries_path(root: Path) -> Path:
    return store_dir(root) / "entries.jsonl"


@contextmanager
def _locked(root: Path):
    """Hold an exclusive lock so two agents can't claim the same id or clobber a revive."""
    folder = store_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    if fcntl is None:
        yield
        return
    # Lock the folder, not the file: revive swaps the file out, which would orphan its lock.
    fd = os.open(folder, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _read_lines(path: Path) -> list[str]:
    # newline="\n" splits on \n only, so odd characters in a snippet can't break a record.
    try:
        with open(path, encoding="utf-8", newline="\n") as f:
            return list(f)
    except FileNotFoundError:
        return []


def _parse(line: str) -> dict | None:
    try:
        data = json.loads(line)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False) + "\n"


def read_entries(root: Path) -> list[Entry]:
    """Every valid entry in file order. Bad lines are skipped with a warning, never removed."""
    entries = []
    for number, line in enumerate(_read_lines(entries_path(root)), start=1):
        if not line.strip():
            continue
        try:
            entries.append(Entry.from_dict(_parse(line) or {}))
        except (TypeError, ValueError) as e:
            # stderr, because stdout will carry the MCP protocol.
            print(f"graveyard: skipping bad line {number}: {e}", file=sys.stderr)
    return entries


def append_entry(root: Path, attempt: str, why_failed: str, **fields) -> Entry:
    path = entries_path(root)
    with _locked(root):
        lines = _read_lines(path)
        ids = [d.get("id") for d in map(_parse, lines) if d]
        next_id = max((i for i in ids if type(i) is int), default=0) + 1
        entry = Entry(id=next_id, attempt=attempt, why_failed=why_failed, **fields)
        # A crash mid-write can leave no final newline; don't glue this entry onto that line.
        prefix = "\n" if lines and not lines[-1].endswith("\n") else ""
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(prefix + _dumps(entry.to_dict()))
            f.flush()
            os.fsync(f.fileno())
    return entry


def update_entry(root: Path, entry_id: int, **changes) -> Entry:
    """Change one entry and leave every other line byte-for-byte, even ones we can't parse."""
    path = entries_path(root)
    with _locked(root):
        lines = _read_lines(path)
        matches = [i for i, line in enumerate(lines) if (_parse(line) or {}).get("id") == entry_id]
        if not matches:
            raise KeyError(entry_id)
        # Branches that each added an entry can merge into two entries with one id.
        if len(matches) > 1:
            raise ValueError(f"id {entry_id} appears {len(matches)} times; fix {path} by hand")
        merged = {**_parse(lines[matches[0]]), **changes}
        entry = Entry.from_dict(merged)  # validates before anything touches the disk
        lines[matches[0]] = _dumps(merged)
        _replace_file(path, lines)
    return entry


def _replace_file(path: Path, lines: list[str]) -> None:
    """Write to a temp file, then rename: a crash leaves the old file or the new one, never half."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".entries-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.writelines(lines)
            f.flush()
            os.fsync(f.fileno())
        shutil.copymode(path, tmp)  # mkstemp makes it private; keep the original permissions
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
