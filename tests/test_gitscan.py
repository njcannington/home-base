import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path

from homebase.entry import Entry
from homebase.gitscan import last_commit_date, scan


def git_repo_with_commit(path: Path, when: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    run = lambda *a: subprocess.run(
        ["git", *a], cwd=path, check=True, capture_output=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(path),
             "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when,
             "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t"},
    )
    run("init", "-q")
    (path / "f.txt").write_text("x")
    run("add", "f.txt")
    run("commit", "-q", "-m", "c")


def make(entry_id, repo=None, **kw):
    defaults = dict(
        id=entry_id, name="X", kind="project", area="software",
        last_touched=date(2020, 1, 1), repo=str(repo) if repo else None,
    )
    defaults.update(kw)
    return Entry(**defaults)


class GitScanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_last_commit_date(self):
        repo = self.root / "live"
        git_repo_with_commit(repo, "2026-10-06T12:00:00")
        self.assertEqual(last_commit_date(repo), date(2026, 10, 6))

    # Review Focus 2: garden is exactly this
    def test_plain_directory_returns_none(self):
        plain = self.root / "garden"
        plain.mkdir()
        self.assertIsNone(last_commit_date(plain))

    def test_missing_directory_returns_none(self):
        self.assertIsNone(last_commit_date(self.root / "gone"))

    def test_repo_with_no_commits_returns_none(self):
        empty = self.root / "empty"
        empty.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=empty, check=True,
                       capture_output=True)
        self.assertIsNone(last_commit_date(empty))

    def test_scan_touches_entry_from_commit(self):
        repo = self.root / "live"
        git_repo_with_commit(repo, "2026-10-06T12:00:00")
        e = make("sfn", repo=repo)
        changed = scan([e])
        self.assertEqual(e.last_touched, date(2026, 10, 6))
        self.assertTrue(e.repo_is_git)
        self.assertEqual(changed, [e])

    def test_scan_marks_non_git_repo_and_does_not_crash(self):
        plain = self.root / "garden"
        plain.mkdir()
        e = make("garden", repo=plain)
        changed = scan([e])
        self.assertFalse(e.repo_is_git)
        self.assertEqual(e.last_touched, date(2020, 1, 1))
        self.assertEqual(changed, [e])

    def test_scan_ignores_entries_without_a_repo(self):
        e = make("painting")
        self.assertEqual(scan([e]), [])
        self.assertTrue(e.repo_is_git)

    def test_scan_does_not_move_last_touched_backwards(self):
        repo = self.root / "old"
        git_repo_with_commit(repo, "2026-01-01T12:00:00")
        e = make("sfn", repo=repo, last_touched=date(2026, 10, 1))
        scan([e])
        self.assertEqual(e.last_touched, date(2026, 10, 1))

    def test_scan_expands_tilde_in_repo_path(self):
        e = make("x", repo="~/definitely-not-a-real-dir-xyz")
        scan([e])
        self.assertFalse(e.repo_is_git)


if __name__ == "__main__":
    unittest.main()
