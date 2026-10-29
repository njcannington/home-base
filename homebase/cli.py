"""Command dispatch. The only module allowed to print or touch the clock."""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from homebase.brief import build_brief
from homebase.decay import MONTHS, apply_decay
from homebase.entry import AREAS, KINDS, STATES, Entry, EntryParseError
from homebase.gitscan import scan
from homebase.store import EntryNotFound, load_all, load_one, retire, save


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "entry"


def _dirs(root: Path) -> tuple[Path, Path]:
    return root / "entries", root / "graveyard"


def _wake_value(value: str) -> str:
    """Accept a month name (case-insensitive, from decay.MONTHS) or an ISO
    date. Anything else is rejected here, at the boundary, exactly like
    --due — a bad wake must never reach disk unparsed."""
    if value.strip().lower() in MONTHS:
        return value
    try:
        date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a month name or an ISO date (YYYY-MM-DD)"
        ) from None
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hb")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("brief")
    sub.add_parser("scan")

    p_list = sub.add_parser("list")
    p_list.add_argument("--area", choices=sorted(AREAS))
    p_list.add_argument("--state", choices=sorted(STATES))

    p_add = sub.add_parser("add")
    p_add.add_argument("name")
    p_add.add_argument("--kind", choices=sorted(KINDS), required=True)
    p_add.add_argument("--area", choices=sorted(AREAS), required=True)
    p_add.add_argument("--cadence", type=int, default=7)
    p_add.add_argument("--due", type=date.fromisoformat)
    p_add.add_argument("--repo")
    p_add.add_argument("--next", dest="next_action")

    p_touch = sub.add_parser("touch")
    p_touch.add_argument("entry_id")
    p_touch.add_argument("--next", dest="next_action")

    p_state = sub.add_parser("state")
    p_state.add_argument("entry_id")
    p_state.add_argument("new_state", choices=sorted(STATES))

    p_set = sub.add_parser("set")
    p_set.add_argument("entry_id")
    p_set.add_argument("--waiting-on")
    p_set.add_argument("--waiting-since", type=date.fromisoformat)
    p_set.add_argument("--wake", type=_wake_value)
    p_set.add_argument("--due", type=date.fromisoformat)
    p_set.add_argument("--repo")
    p_set.add_argument("--cadence", type=int)
    p_set.add_argument("--next", dest="next_action")

    for name in ("retire", "done"):
        p = sub.add_parser(name)
        p.add_argument("entry_id")

    return parser


# Fields hb set can change, and how each maps onto an Entry attribute.
# dest name == attribute name for every one of them except "cadence".
_SET_FIELDS = ("waiting_on", "waiting_since", "wake", "due", "repo", "cadence", "next_action")


def main(argv: list[str], root: Path, today: date) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    entries_dir, graveyard_dir = _dirs(root)

    if args.command == "add":
        entry_id = slugify(args.name)
        if (entries_dir / f"{entry_id}.md").exists():
            print(f"hb: {entry_id} already exists", file=sys.stderr)
            return 1
        entry = Entry(
            id=entry_id, name=args.name, kind=args.kind, area=args.area,
            last_touched=today, cadence_days=args.cadence,
            next_action=args.next_action, repo=args.repo,
            due=args.due,
        )
        save(entries_dir, entry)
        print(entry_id)
        return 0

    if args.command in ("touch", "state", "done"):
        try:
            entry = load_one(entries_dir, args.entry_id)
        except EntryNotFound:
            print(f"hb: no entry {args.entry_id!r}", file=sys.stderr)
            return 1
        except EntryParseError as exc:
            print(f"hb: {exc}", file=sys.stderr)
            return 1
        if args.command == "touch":
            entry.last_touched = today
            if entry.state == "idling":
                entry.state = "active"
            if args.next_action is not None:
                entry.next_action = args.next_action
        elif args.command == "state":
            entry.state = args.new_state
            # The handoff clock starts the moment something becomes "waiting".
            # If it is already set, it belongs to the original handoff, not
            # to the most recent re-marking.
            if args.new_state == "waiting" and entry.waiting_since is None:
                entry.waiting_since = today
        else:
            entry.state = "done"
        save(entries_dir, entry)
        return 0

    if args.command == "set":
        if all(getattr(args, field) is None for field in _SET_FIELDS):
            print("hb: set requires at least one field", file=sys.stderr)
            return 2
        try:
            entry = load_one(entries_dir, args.entry_id)
        except EntryNotFound:
            print(f"hb: no entry {args.entry_id!r}", file=sys.stderr)
            return 1
        except EntryParseError as exc:
            print(f"hb: {exc}", file=sys.stderr)
            return 1
        if args.waiting_on is not None:
            entry.waiting_on = args.waiting_on
        if args.waiting_since is not None:
            entry.waiting_since = args.waiting_since
        if args.wake is not None:
            entry.wake = args.wake
        if args.due is not None:
            entry.due = args.due
        if args.repo is not None:
            entry.repo = args.repo
        if args.cadence is not None:
            entry.cadence_days = args.cadence
        if args.next_action is not None:
            entry.next_action = args.next_action
        save(entries_dir, entry)
        return 0

    if args.command == "retire":
        try:
            retire(entries_dir, graveyard_dir, args.entry_id)
        except EntryNotFound:
            print(f"hb: no entry {args.entry_id!r}", file=sys.stderr)
            return 1
        except EntryParseError as exc:
            print(f"hb: {exc}", file=sys.stderr)
            return 1
        return 0

    entries, errors = load_all(entries_dir)

    if args.command == "list":
        for entry in entries:
            if args.area and entry.area != args.area:
                continue
            if args.state and entry.state != args.state:
                continue
            print(f"{entry.id:28} {entry.state:9} {entry.area:9} "
                  f"{entry.next_action or '-'}")
        for problem in errors:
            print(f"hb: {problem}", file=sys.stderr)
        return 0

    # brief and scan both reconcile state before anything else
    changed = scan(entries)
    changed += [e for e in apply_decay(entries, today) if e not in changed]
    for entry in changed:
        save(entries_dir, entry)

    if args.command == "scan":
        for entry in changed:
            print(entry.id)
        return 0

    print(json.dumps(build_brief(entries, today, errors), indent=2))
    return 0
