import json
import multiprocessing
import stat

import pytest

from graveyard.models import Entry
from graveyard.storage import (
    NotInRepoError,
    append_entry,
    entries_path,
    find_repo_root,
    read_entries,
    update_entry,
)


def add(root, n=1):
    return [append_entry(root, f"try {i}", "broke") for i in range(n)]


def test_find_repo_root_walks_up(tmp_path):
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert find_repo_root(nested) == tmp_path.resolve()


def test_find_repo_root_accepts_git_file(tmp_path):
    (tmp_path / ".git").write_text("gitdir: elsewhere\n")  # how worktrees look
    assert find_repo_root(tmp_path) == tmp_path.resolve()


def test_find_repo_root_outside_repo(tmp_path):
    # tmp dirs live outside any repo on a normal machine
    with pytest.raises(NotInRepoError):
        find_repo_root(tmp_path)


@pytest.mark.parametrize(
    "bad",
    [
        {"attempt": " ", "why_failed": "x"},
        {"attempt": "x", "why_failed": ""},
        {"attempt": "x", "why_failed": "y", "status": "zombie"},
        {"attempt": "x", "why_failed": "y", "tags": "numpy"},
    ],
)
def test_entry_validation(bad):
    with pytest.raises(ValueError):
        Entry(id=1, **bad)


def test_read_missing_file_is_empty(tmp_path):
    assert read_entries(tmp_path) == []


def test_append_numbers_entries_and_round_trips(tmp_path):
    first = append_entry(
        tmp_path,
        "Bumped numpy to 2.x",
        "broke torch 2.1",
        area="requirements.txt",
        tags=["numpy", "torch"],
        error_snippet="line one\nline two café",
        author="claude-code",
    )
    second = append_entry(tmp_path, "b", "c")
    assert (first.id, second.id) == (1, 2)
    assert read_entries(tmp_path) == [first, second]
    assert len(entries_path(tmp_path).read_text(encoding="utf-8").strip().split("\n")) == 2


def test_empty_optional_fields_stay_out_of_the_file(tmp_path):
    add(tmp_path)
    saved = json.loads(entries_path(tmp_path).read_text())
    assert set(saved) == {"id", "attempt", "why_failed", "created_at", "status"}


def test_append_survives_crash_truncated_last_line(tmp_path):
    add(tmp_path)
    with open(entries_path(tmp_path), "a") as f:
        f.write('{"id": 2, "attempt": "half wri')
    new = append_entry(tmp_path, "after crash", "x")
    assert new.id == 2
    assert [e.attempt for e in read_entries(tmp_path)] == ["try 0", "after crash"]
    assert '"half wri' in entries_path(tmp_path).read_text()


def test_bad_lines_warn_and_are_skipped(tmp_path, capsys):
    add(tmp_path)
    with open(entries_path(tmp_path), "a") as f:
        f.write('not json\n[1, 2]\n{"id": 9}\n\n')
    assert len(read_entries(tmp_path)) == 1
    assert capsys.readouterr().err.count("skipping bad line") == 3


def test_update_touches_only_the_target_line(tmp_path):
    add(tmp_path, 3)
    path = entries_path(tmp_path)
    with open(path, "a") as f:
        f.write('not json\n{"id": 4, "attempt": "a", "why_failed": "b", "from_the_future": 1}\n')
    before = path.read_text().splitlines()

    updated = update_entry(tmp_path, 2, status="revived", note="works on torch 2.3")

    after = path.read_text().splitlines()
    assert (updated.status, updated.note) == ("revived", "works on torch 2.3")
    assert [i for i, (a, b) in enumerate(zip(before, after)) if a != b] == [1]
    assert len(after) == len(before)


def test_update_keeps_unknown_fields_on_the_target(tmp_path):
    add(tmp_path)
    path = entries_path(tmp_path)
    data = json.loads(path.read_text())
    path.write_text(json.dumps({**data, "from_the_future": 1}) + "\n")
    update_entry(tmp_path, 1, note="n")
    assert json.loads(path.read_text())["from_the_future"] == 1


def test_update_keeps_file_permissions(tmp_path):
    add(tmp_path)
    path = entries_path(tmp_path)
    path.chmod(0o644)
    update_entry(tmp_path, 1, note="n")
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_update_rejects_invalid_change_without_touching_file(tmp_path):
    add(tmp_path)
    before = entries_path(tmp_path).read_text()
    with pytest.raises(ValueError):
        update_entry(tmp_path, 1, status="zombie")
    assert entries_path(tmp_path).read_text() == before


def test_update_missing_id(tmp_path):
    add(tmp_path)
    with pytest.raises(KeyError):
        update_entry(tmp_path, 99, note="n")


def test_update_refuses_duplicate_ids(tmp_path):
    add(tmp_path)
    path = entries_path(tmp_path)
    before = path.read_text()
    path.write_text(before + before)
    with pytest.raises(ValueError, match="2 times"):
        update_entry(tmp_path, 1, note="n")
    assert path.read_text() == before + before


def test_failed_replace_leaves_no_temp_file(tmp_path, monkeypatch):
    add(tmp_path)
    def boom(*a):
        raise OSError("disk full")
    monkeypatch.setattr("graveyard.storage.os.replace", boom)
    with pytest.raises(OSError):
        update_entry(tmp_path, 1, note="n")
    assert [p.name for p in entries_path(tmp_path).parent.iterdir()] == ["entries.jsonl"]


def _worker(root):
    for _ in range(20):
        append_entry(root, "a", "b")


def test_concurrent_appends_get_unique_ids(tmp_path):
    procs = [multiprocessing.Process(target=_worker, args=(tmp_path,)) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    assert sorted(e.id for e in read_entries(tmp_path)) == list(range(1, 81))
