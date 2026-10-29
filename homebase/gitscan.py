"""Touching entries from git history, so the ledger watches instead of being fed."""
import subprocess
from datetime import date
from pathlib import Path

from homebase.entry import Entry


def last_commit_date(repo: Path) -> date | None:
    """Date of the newest commit, or None if this is not a usable git repo."""
    repo = Path(repo).expanduser()
    if not repo.is_dir():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "log", "-1", "--format=%cs"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    stamp = result.stdout.strip()
    try:
        return date.fromisoformat(stamp)
    except ValueError:
        return None


def scan(entries: list[Entry]) -> list[Entry]:
    """Set last_touched and repo_is_git from git. Never moves a date backwards."""
    changed: list[Entry] = []
    for entry in entries:
        if not entry.repo:
            continue
        committed = last_commit_date(Path(entry.repo))
        if committed is None:
            if entry.repo_is_git:
                entry.repo_is_git = False
                changed.append(entry)
            continue
        entry.repo_is_git = True
        if committed > entry.last_touched:
            entry.last_touched = committed
            changed.append(entry)
    return changed
