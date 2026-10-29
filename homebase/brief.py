"""Deciding what needs you today. Pure selection and ordering — no prose."""
from datetime import date

from homebase.entry import Entry
from homebase.decay import wake_date

BUCKET_ORDER = ["overdue", "due_soon", "upcoming", "stale_waiting", "idling", "waking", "active"]
DUE_SOON_DAYS = 3
UPCOMING_DAYS = 14
STALE_WAITING_DAYS = 14
HIDDEN_STATES = {"dead", "done"}


def _bucket(entry: Entry, today: date) -> tuple[str, str] | None:
    """Return (bucket, detail) or None if this entry needs nothing today."""
    if entry.state in HIDDEN_STATES:
        return None

    if entry.due is not None:
        overdue_by = (today - entry.due).days
        if overdue_by > 0:
            return "overdue", f"{overdue_by} days overdue"
        days_until = (entry.due - today).days
        if days_until <= DUE_SOON_DAYS:
            return "due_soon", "due today" if days_until == 0 else f"{days_until} days"
        if days_until <= UPCOMING_DAYS:
            return "upcoming", f"{days_until} days"

    # cadence 0 means no pressure: a due date can still surface it, nothing else can.
    if entry.cadence_days == 0:
        return None

    if entry.state == "waiting":
        if entry.waiting_since is None:
            return None
        waited = (today - entry.waiting_since).days
        if waited > STALE_WAITING_DAYS:
            who = entry.waiting_on or "them"
            return "stale_waiting", f"{waited} days, waiting on {who}"
        return None

    if entry.state == "idling":
        idle = (today - entry.last_touched).days
        return "idling", f"idle {idle} days"

    if entry.wake and not entry.next_action:
        when = wake_date(entry.wake, today)
        if when is not None and when <= today:
            return "waking", f"{entry.wake} reached"

    if entry.state == "active" and entry.next_action:
        return "active", f"touched {(today - entry.last_touched).days} days ago"

    return None


def _urgency_key(bucket: str, entry: Entry, today: date) -> int:
    """Secondary sort key within a bucket. Lower sorts first."""
    if bucket in ("overdue", "due_soon", "upcoming"):
        return entry.due.toordinal()
    if bucket == "stale_waiting":
        return -(today - entry.waiting_since).days
    if bucket == "idling":
        return -entry.last_touched.toordinal()
    return 0


def build_brief(
    entries: list[Entry],
    today: date,
    errors: list[str] | None = None,
    cap: int = 7,
) -> dict:
    errors = list(errors or [])

    bucketed: list[tuple[dict, Entry]] = []
    for entry in entries:
        result = _bucket(entry, today)
        if result is None:
            continue
        bucket, detail = result
        item = {
            "id": entry.id,
            "name": entry.name,
            "area": entry.area,
            "kind": entry.kind,
            "state": entry.state,
            "bucket": bucket,
            "next": entry.next_action,
            "detail": detail,
        }
        bucketed.append((item, entry))

    # Sort by bucket order, then by a per-bucket urgency key. Dated buckets
    # (overdue/due_soon/upcoming) order by due ascending — earliest due date
    # first, which for overdue also means "most overdue" first. stale_waiting
    # orders by how long it has waited, descending (most stale first).
    # idling orders by last_touched, most recent first.
    bucketed.sort(key=lambda x: (
        BUCKET_ORDER.index(x[0]["bucket"]),
        _urgency_key(x[0]["bucket"], x[1], today),
    ))

    items = [item for item, _ in bucketed[:cap]]
    overflow = [item for item, _ in bucketed[cap:]]

    suppressed: dict[str, int] = {}
    for item in overflow:
        suppressed[item["bucket"]] = suppressed.get(item["bucket"], 0) + 1

    flags: list[dict] = []
    for e in entries:
        if e.state in HIDDEN_STATES:
            continue
        if e.repo and not e.repo_is_git:
            flags.append({"id": e.id, "flag": "repo_not_git"})
        if e.state == "seasonal" and wake_date(e.wake, today) is None:
            flags.append({"id": e.id, "flag": "wake_unresolvable"})

    return {
        "items": items,
        "suppressed": suppressed,
        "flags": flags,
        "errors": errors,
        "silent": not items and not flags and not errors,
    }
