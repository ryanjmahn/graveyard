"""The `graveyard` command."""

import argparse
import os
import sys

from . import display, search, storage

CLAUDE_SNIPPET = """\
## Graveyard (failed approaches)
- Before trying a fix or changing an area of the code, call `search_dead_ends` with relevant keywords.
- If an approach fails and you're switching to a different one, call `record_dead_end` with what you tried and why it failed.
- Don't retry anything listed as dead unless conditions have clearly changed. If you do, say why.
"""


def _print_entries(entries, full=False):
    color = display.use_color()
    print("\n\n".join(display.format_entry(e, full=full, color=color) for e in entries))


def cmd_init(args):
    root = storage.find_repo_root()
    existed = storage.store_dir(root).exists()
    storage.init_store(root, private=args.private)
    print(f"🪦 Graveyard {'already set up' if existed else 'created'} at {storage.store_dir(root)}")
    if args.private:
        print("Private: git will ignore .graveyard/. Anything already committed stays tracked.")
    else:
        print("Commit .graveyard/ so teammates and their agents share it. For a private one: graveyard init --private")
    print(f"\nPaste this into CLAUDE.md:\n\n{CLAUDE_SNIPPET}", end="")


def _ask(label, required=False):
    while True:
        value = input(f"{label}: ").strip()
        if value or not required:
            return value or None
        print(f"{label} is required.")


def _ask_snippet():
    # Read until a blank line, or a pasted multi-line error would spill into later prompts.
    print("Error snippet (optional, finish with an empty line):")
    lines = []
    while line := input():
        lines.append(line)
    return "\n".join(lines) or None


def _tags(text):
    return [t.strip() for t in (text or "").split(",") if t.strip()]


def cmd_add(args):
    root = storage.find_repo_root()
    # No flags at all means a person at a keyboard: offer every field, not just the required two.
    ask_all = args.attempt is None and args.why is None
    fields = {"area": args.area, "tags": args.tags, "error_snippet": args.error, "author": args.author, "note": args.note}
    try:
        attempt = args.attempt if args.attempt is not None else _ask("What did you try?", required=True)
        why_failed = args.why if args.why is not None else _ask("Why did it fail?", required=True)
        if ask_all:
            fields["area"] = fields["area"] or _ask("Area (files or subsystem, optional)")
            fields["tags"] = fields["tags"] or _ask("Tags (comma separated, optional)")
            fields["author"] = fields["author"] or _ask("Author (optional)")
            fields["note"] = fields["note"] or _ask("Note (optional)")
            fields["error_snippet"] = fields["error_snippet"] or _ask_snippet()
    except EOFError:
        print("graveyard: --attempt and --why are required when there's no one to ask.", file=sys.stderr)
        return 2
    fields["tags"] = _tags(fields["tags"])
    storage.init_store(root)  # so an entry added before `init` still gets the merge setting
    entry = storage.append_entry(root, attempt, why_failed, **fields)
    _print_entries([entry])


def cmd_list(args):
    root = storage.find_repo_root()
    entries = search.filter_entries(storage.read_entries(root), tag=args.tag, area=args.area)
    if not entries:
        print("🌱 No dead ends found.")
        return
    _print_entries(entries[: args.limit])
    if len(entries) > args.limit:
        print(f"\nShowing {args.limit} of {len(entries)}. Use --limit to see more.")


def cmd_show(args):
    root = storage.find_repo_root()
    # A list, because a git merge can leave two entries sharing an id.
    entries = [e for e in storage.read_entries(root) if e.id == args.id]
    if not entries:
        print(f"graveyard: no entry #{args.id}", file=sys.stderr)
        return 1
    _print_entries(entries, full=True)


def _positive_int(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return value


def _parser():
    parser = argparse.ArgumentParser(prog="graveyard", description="🪦 A log of failed approaches, so agents stop repeating them.")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    init = commands.add_parser("init", help="set up .graveyard/ in this repo and print the CLAUDE.md snippet")
    init.add_argument("--private", action="store_true", help="have git ignore the graveyard instead of sharing it")
    init.set_defaults(func=cmd_init)

    add = commands.add_parser("add", help="record a dead end (asks for anything you don't pass)")
    add.add_argument("--attempt", help="what was tried")
    add.add_argument("--why", help="why it failed")
    add.add_argument("--area", help="files, folders, or a subsystem name")
    add.add_argument("--tags", help="comma separated keywords")
    add.add_argument("--error", help="a few lines of the actual error")
    add.add_argument("--author", help="who tried it, e.g. claude-code")
    add.add_argument("--note", help="extra context")
    add.set_defaults(func=cmd_add)

    list_ = commands.add_parser("list", help="show recent entries, newest first")
    list_.add_argument("--tag", help="only entries with this tag")
    list_.add_argument("--area", help="only entries whose area contains this")
    list_.add_argument("-n", "--limit", type=_positive_int, default=20, help="how many to show (default 20)")
    list_.set_defaults(func=cmd_list)

    show = commands.add_parser("show", help="show one entry in full")
    show.add_argument("id", type=int)
    show.set_defaults(func=cmd_show)
    return parser


def main(argv=None):
    sys.stdout.reconfigure(errors="replace")  # a non-UTF-8 pipe shouldn't crash on 🪦
    args = _parser().parse_args(argv)
    try:
        code = args.func(args) or 0
        sys.stdout.flush()
        return code
    except storage.NotInRepoError as e:
        print(f"graveyard: {e}. Run this inside a git repo, or `git init` first.", file=sys.stderr)
    except ValueError as e:
        print(f"graveyard: {e}", file=sys.stderr)
    except BrokenPipeError:
        # Whatever read our output has gone away (`graveyard list | head`). Quiet the flush at shutdown.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except KeyboardInterrupt:
        print()
        return 130
    except OSError as e:
        print(f"graveyard: {e}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
