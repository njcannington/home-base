"""Reading and writing the entries directory."""
from pathlib import Path

from homebase.entry import Entry, EntryParseError, parse_entry


class EntryNotFound(Exception):
    """No entry file with that id."""


def _path(entries_dir: Path, entry_id: str) -> Path:
    return entries_dir / f"{entry_id}.md"


def load_all(entries_dir: Path) -> tuple[list[Entry], list[str]]:
    """Load every entry. A broken file is skipped and reported, never fatal."""
    entries: list[Entry] = []
    errors: list[str] = []
    if not entries_dir.is_dir():
        return entries, errors
    try:
        paths = sorted(
            p for p in entries_dir.iterdir() if p.suffix == ".md"
        )
    except OSError as exc:
        errors.append(f"{entries_dir.name}: unreadable directory — {exc}")
        return entries, errors
    for path in paths:
        try:
            entries.append(parse_entry(path.read_text(), path.stem))
        except EntryParseError as exc:
            errors.append(str(exc))
        except UnicodeDecodeError as exc:
            errors.append(f"{path.stem}: invalid encoding — {exc}")
        except OSError as exc:
            errors.append(f"{path.stem}: unreadable — {exc}")
    return entries, errors


def load_one(entries_dir: Path, entry_id: str) -> Entry:
    path = _path(entries_dir, entry_id)
    if not path.is_file():
        raise EntryNotFound(entry_id)
    try:
        text = path.read_text()
    except UnicodeDecodeError as exc:
        raise EntryParseError(f"{entry_id}: invalid encoding — {exc}") from None
    return parse_entry(text, entry_id)


def save(entries_dir: Path, entry: Entry) -> None:
    """Write the entry, skipping the write if content is already identical
    (avoids pointless write amplification and mtime churn on every run)."""
    entries_dir.mkdir(parents=True, exist_ok=True)
    path = _path(entries_dir, entry.id)
    text = entry.to_text()
    if path.is_file():
        try:
            if path.read_text() == text:
                return
        except (OSError, UnicodeDecodeError):
            pass
    path.write_text(text)


def retire(entries_dir: Path, graveyard_dir: Path, entry_id: str) -> None:
    """Move an entry to the graveyard with state=dead. It never surfaces again."""
    entry = load_one(entries_dir, entry_id)
    entry.state = "dead"
    graveyard_dir.mkdir(parents=True, exist_ok=True)
    graveyard_path = _path(graveyard_dir, entry_id)
    graveyard_path.write_text(entry.to_text())
    try:
        _path(entries_dir, entry_id).unlink()
    except OSError:
        # Rollback: remove graveyard copy before re-raising
        graveyard_path.unlink(missing_ok=True)
        raise
