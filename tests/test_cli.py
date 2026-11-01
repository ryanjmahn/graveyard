import io
import subprocess

import pytest

from graveyard import cli, display
from graveyard.models import Entry
from graveyard.storage import append_entry, entries_path, read_entries, store_dir, update_entry


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q", "-b", "main")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def git(cwd, *args):
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    return subprocess.run(["git", *identity, *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def add_dated(root, attempt, created_at, **fields):
    return append_entry(root, attempt, "broke", created_at=created_at, **fields)


# init


def test_init_creates_store_and_prints_snippet(repo, capsys):
    assert cli.main(["init"]) == 0
    assert entries_path(repo).exists()
    out = capsys.readouterr().out
    assert "created" in out and "search_dead_ends" in out and "record_dead_end" in out


def test_init_twice_keeps_entries(repo, capsys):
    cli.main(["init"])
    append_entry(repo, "a", "b")
    assert cli.main(["init"]) == 0
    assert "already set up" in capsys.readouterr().out
    assert len(read_entries(repo)) == 1


def test_init_outside_repo_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["init"]) == 1
    assert "git repo" in capsys.readouterr().err
    assert not store_dir(tmp_path).exists()


def test_init_leaves_the_repos_own_git_files_alone(repo):
    cli.main(["init", "--private"])
    assert not (repo / ".gitignore").exists() and not (repo / ".gitattributes").exists()


def test_private_store_is_ignored_by_git(git_repo):
    cli.main(["init", "--private"])
    append_entry(git_repo, "a", "b")
    assert git(git_repo, "status", "--porcelain") == ""


def test_shared_store_is_visible_to_git(git_repo):
    cli.main(["init"])
    assert ".graveyard/" in git(git_repo, "status", "--porcelain")


def test_branches_adding_entries_merge_without_conflict(git_repo):
    cli.main(["init"])
    git(git_repo, "add", ".")
    git(git_repo, "commit", "-qm", "init")

    git(git_repo, "checkout", "-qb", "other")
    append_entry(git_repo, "from other", "x")
    git(git_repo, "commit", "-qam", "other")

    git(git_repo, "checkout", "-q", "main")
    append_entry(git_repo, "from main", "x")
    git(git_repo, "commit", "-qam", "main")

    git(git_repo, "merge", "-q", "--no-edit", "other")  # check=True fails this test on a conflict
    assert {e.attempt for e in read_entries(git_repo)} == {"from main", "from other"}


# add


def test_add_with_flags(repo, capsys):
    code = cli.main(
        ["add", "--attempt", "Bumped numpy", "--why", "broke torch", "--area", "deps", "--tags", "numpy, torch,,",
         "--error", "line 1\nline 2", "--author", "claude-code", "--note", "maybe later"]
    )
    assert code == 0
    entry = read_entries(repo)[0]
    assert entry.tags == ["numpy", "torch"]
    assert (entry.area, entry.author, entry.note) == ("deps", "claude-code", "maybe later")
    assert entry.error_snippet == "line 1\nline 2"
    assert "🪦 #1  Bumped numpy" in capsys.readouterr().out


def test_add_from_subfolder_writes_to_repo_root(repo, monkeypatch):
    (repo / "src").mkdir()
    monkeypatch.chdir(repo / "src")
    cli.main(["add", "--attempt", "a", "--why", "b"])
    assert len(read_entries(repo)) == 1
    assert not (repo / "src" / ".graveyard").exists()


def test_add_before_init_still_sets_up_merging(repo):
    cli.main(["add", "--attempt", "a", "--why", "b"])
    assert (store_dir(repo) / ".gitattributes").exists()


def test_add_interactive_asks_every_field(repo, monkeypatch):
    answers = "try\nwhy\nsrc/\nnumpy, torch\nme\nsome note\nerr 1\nerr 2\n\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(answers))
    assert cli.main(["add"]) == 0
    e = read_entries(repo)[0]
    assert (e.attempt, e.why_failed, e.area, e.author, e.note) == ("try", "why", "src/", "me", "some note")
    assert e.tags == ["numpy", "torch"]
    assert e.error_snippet == "err 1\nerr 2"


def test_add_interactive_reasks_blank_required_field(repo, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("\n  \ntry\nwhy\n\n\n\n\n\n"))
    assert cli.main(["add"]) == 0
    assert read_entries(repo)[0].attempt == "try"


def test_add_only_asks_for_the_missing_required_field(repo, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("why\n"))
    assert cli.main(["add", "--attempt", "try"]) == 0
    assert read_entries(repo)[0].why_failed == "why"


def test_add_with_no_input_saves_nothing(repo, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert cli.main(["add"]) == 2
    assert "required" in capsys.readouterr().err
    assert read_entries(repo) == []


def test_add_blank_flag_is_rejected(repo, capsys):
    assert cli.main(["add", "--attempt", "  ", "--why", "b"]) == 1
    assert "attempt is required" in capsys.readouterr().err
    assert read_entries(repo) == []


# list


def test_list_newest_first_regardless_of_file_order(repo, capsys):
    add_dated(repo, "newest", "2026-03-01T00:00:00+00:00")
    add_dated(repo, "oldest", "2026-01-01T00:00:00+00:00")
    add_dated(repo, "middle", "2026-02-01T00:00:00+00:00")
    cli.main(["list"])
    out = capsys.readouterr().out
    assert out.index("newest") < out.index("middle") < out.index("oldest")


def test_list_filters_ignore_case(repo, capsys):
    append_entry(repo, "numpy one", "x", tags=["NumPy"], area="deps · requirements.txt")
    append_entry(repo, "other one", "x", tags=["numpy2"], area="src/api")
    cli.main(["list", "--tag", "numpy"])
    out = capsys.readouterr().out
    assert "numpy one" in out and "other one" not in out
    cli.main(["list", "--area", "REQUIREMENTS"])
    out = capsys.readouterr().out
    assert "numpy one" in out and "other one" not in out


def test_list_limit_says_what_it_hid(repo, capsys):
    for i in range(3):
        append_entry(repo, f"try {i}", "x")
    cli.main(["list", "-n", "2"])
    out = capsys.readouterr().out
    assert out.count("🪦") == 2 and "Showing 2 of 3" in out


def test_list_rejects_zero_limit(repo, capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["list", "-n", "0"])
    assert e.value.code == 2


def test_list_empty(repo, capsys):
    assert cli.main(["list"]) == 0
    assert "No dead ends" in capsys.readouterr().out


# show


def test_show_includes_what_list_leaves_out(repo, capsys):
    append_entry(repo, "a", "b", error_snippet="boom\nbang")
    cli.main(["list"])
    listed = capsys.readouterr().out
    assert cli.main(["show", "1"]) == 0
    shown = capsys.readouterr().out
    assert "boom" not in listed
    assert "      boom\n      bang" in shown


def test_show_missing_id(repo, capsys):
    assert cli.main(["show", "9"]) == 1
    assert "no entry #9" in capsys.readouterr().err


def test_show_revived_entry(repo, capsys):
    append_entry(repo, "a", "b")
    update_entry(repo, 1, status="revived", note="works now")
    cli.main(["show", "1"])
    out = capsys.readouterr().out
    assert "🌱 #1" in out and "(revived)" in out and "works now" in out


# display


def test_piped_output_has_no_color_codes(repo, capsys):
    append_entry(repo, "a", "b")
    cli.main(["list"])
    assert "\x1b" not in capsys.readouterr().out


def test_no_color_env_wins_over_terminal(monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert display.use_color()
    monkeypatch.setenv("NO_COLOR", "1")
    assert not display.use_color()


def test_format_strips_escape_codes_from_stored_text():
    entry = Entry(id=1, attempt="\x1b[31mred\x1b[0m\x07 thing\nsecond", why_failed="\x1b]0;hacked\x07why", error_snippet="\x1b[1mboom\x1b[0m\nbang")
    out = display.format_entry(entry, full=True)
    assert "\x1b" not in out and "\x07" not in out
    assert "red thing second" in out and "hacked" not in out
    assert "      boom\n      bang" in out


def test_format_color_only_when_asked():
    entry = Entry(id=1, attempt="a", why_failed="b")
    assert "\x1b[" in display.format_entry(entry, color=True)
    assert "\x1b[" not in display.format_entry(entry)
