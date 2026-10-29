"""Automatic state transitions. Nothing here asks the user anything."""
from datetime import date

from homebase.entry import Entry

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def wake_date(wake: str, today: date) -> date | None:
    """Resolve a wake field to a date. A month name means the 1st of that
    month's NEXT occurrence: this year if the month has not finished yet,
    otherwise next year. Anything unparseable returns None — the entry stays
    asleep, which is the safe direction for a field the user hand-edits."""
    if not wake:
        return None
    key = wake.strip().lower()
    if key in MONTHS:
        month = MONTHS[key]
        year = today.year if month >= today.month else today.year + 1
        return date(year, month, 1)
    try:
        return date.fromisoformat(key)
    except ValueError:
        return None


def apply_decay(entries: list[Entry], today: date) -> list[Entry]:
    """Mutate entries in place; return only those that changed."""
    changed: list[Entry] = []
    for entry in entries:
        if entry.state == "active" and entry.cadence_days > 0:
            if (today - entry.last_touched).days > entry.cadence_days:
                entry.state = "idling"
                changed.append(entry)
        elif entry.state == "seasonal":
            when = wake_date(entry.wake, today) if entry.wake else None
            if when is not None and when <= today:
                entry.state = "active"
                changed.append(entry)
    return changed
