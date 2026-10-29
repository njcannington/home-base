import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

from homebase.cli import main

TODAY = date(2026, 10, 23)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "entries").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(list(args), self.root, TODAY)
        return code, buf.getvalue()

    def test_add_creates_a_file(self):
        code, _ = self.run_cli("add", "Ceiling painting", "--kind", "project",
                               "--area", "home")
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "entries" / "ceiling-painting.md").exists())

    def test_add_slugifies_the_name(self):
        self.run_cli("add", "Dinner Club: November 1st", "--kind", "commitment",
                     "--area", "family", "--due", "2026-11-01")
        self.assertTrue((self.root / "entries" / "dinner-club-november-1st.md").exists())

    def test_add_rejects_a_duplicate_id(self):
        self.run_cli("add", "Garden", "--kind", "project", "--area", "software")
        code, _ = self.run_cli("add", "Garden", "--kind", "project", "--area", "software")
        self.assertEqual(code, 1)

    def test_add_rejects_a_bad_area(self):
        code, _ = self.run_cli("add", "X", "--kind", "project", "--area", "wat")
        self.assertEqual(code, 2)

    def test_brief_emits_only_json(self):
        self.run_cli("add", "Dinner", "--kind", "commitment", "--area", "family",
                     "--due", "2026-10-24")
        code, out = self.run_cli("brief")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["items"][0]["id"], "dinner")

    def test_brief_on_empty_ledger_is_silent_json(self):
        code, out = self.run_cli("brief")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["silent"])

    def test_brief_persists_decay(self):
        self.run_cli("add", "Painting", "--kind", "project", "--area", "home",
                     "--cadence", "1")
        path = self.root / "entries" / "painting.md"
        path.write_text(path.read_text().replace("2026-10-23", "2026-10-01"))
        self.run_cli("brief")
        self.assertIn('state = "idling"', path.read_text())

    def test_touch_updates_date_and_next(self):
        self.run_cli("add", "Painting", "--kind", "project", "--area", "home")
        self.run_cli("touch", "painting", "--next", "second coat")
        body = (self.root / "entries" / "painting.md").read_text()
        self.assertIn("last_touched = 2026-10-23", body)
        self.assertIn('next = "second coat"', body)

    def test_touch_revives_an_idling_entry(self):
        self.run_cli("add", "Painting", "--kind", "project", "--area", "home")
        self.run_cli("state", "painting", "idling")
        self.run_cli("touch", "painting")
        self.assertIn('state = "active"',
                      (self.root / "entries" / "painting.md").read_text())

    def test_touch_unknown_id_fails(self):
        code, _ = self.run_cli("touch", "ghost")
        self.assertEqual(code, 1)

    def test_state_rejects_an_invalid_state(self):
        self.run_cli("add", "X", "--kind", "project", "--area", "home")
        code, _ = self.run_cli("state", "x", "sleepy")
        self.assertEqual(code, 2)

    def test_retire_moves_to_graveyard(self):
        self.run_cli("add", "Treehouse", "--kind", "project", "--area", "software")
        code, _ = self.run_cli("retire", "treehouse")
        self.assertEqual(code, 0)
        self.assertFalse((self.root / "entries" / "treehouse.md").exists())
        self.assertTrue((self.root / "graveyard" / "treehouse.md").exists())

    def test_retired_entry_never_appears_in_brief(self):
        self.run_cli("add", "Treehouse", "--kind", "project", "--area", "software")
        self.run_cli("touch", "treehouse", "--next", "finish it")
        self.run_cli("retire", "treehouse")
        _, out = self.run_cli("brief")
        self.assertEqual(json.loads(out)["items"], [])

    def test_done_marks_a_commitment(self):
        self.run_cli("add", "Dinner", "--kind", "commitment", "--area", "family",
                     "--due", "2026-10-24")
        self.run_cli("done", "dinner")
        _, out = self.run_cli("brief")
        self.assertTrue(json.loads(out)["silent"])

    def test_list_is_plain_text(self):
        self.run_cli("add", "Painting", "--kind", "project", "--area", "home")
        code, out = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("painting", out)

    def test_list_filters_by_area(self):
        self.run_cli("add", "Painting", "--kind", "project", "--area", "home")
        self.run_cli("add", "Garden", "--kind", "project", "--area", "software")
        _, out = self.run_cli("list", "--area", "home")
        self.assertIn("painting", out)
        self.assertNotIn("garden", out)

    def test_list_filters_by_state(self):
        self.run_cli("add", "Painting", "--kind", "project", "--area", "home")
        self.run_cli("add", "Garden", "--kind", "project", "--area", "software")
        self.run_cli("state", "garden", "idling")
        _, out = self.run_cli("list", "--state", "idling")
        self.assertIn("garden", out)
        self.assertNotIn("painting", out)

    # Review Focus 1, end to end
    def test_a_broken_file_does_not_break_brief(self):
        self.run_cli("add", "Good", "--kind", "project", "--area", "home")
        (self.root / "entries" / "broken.md").write_text('+++\nname = = "x"\n+++\n')
        code, out = self.run_cli("brief")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(len(payload["errors"]), 1)
        self.assertFalse(payload["silent"])

    # Review findings on Task 6
    def test_help_does_not_count_as_an_error(self):
        code, _ = self.run_cli("brief", "--help")
        self.assertEqual(code, 0)

    def test_add_rejects_a_malformed_due_date(self):
        code, _ = self.run_cli("add", "X", "--kind", "project", "--area", "home",
                               "--due", "not-a-date")
        self.assertEqual(code, 2)

    def _write_broken_entry(self):
        (self.root / "entries" / "broken.md").write_text('+++\nname = = "x"\n+++\n')

    def _write_bad_encoding_entry(self):
        (self.root / "entries" / "badenc.md").write_bytes(b'+++\nname = "\xff\xfe"\n+++\n')

    def test_touch_on_a_corrupt_entry_fails_cleanly(self):
        self._write_broken_entry()
        code, _ = self.run_cli("touch", "broken")
        self.assertEqual(code, 1)

    def test_state_on_a_corrupt_entry_fails_cleanly(self):
        self._write_broken_entry()
        code, _ = self.run_cli("state", "broken", "idling")
        self.assertEqual(code, 1)

    def test_done_on_a_corrupt_entry_fails_cleanly(self):
        self._write_broken_entry()
        code, _ = self.run_cli("done", "broken")
        self.assertEqual(code, 1)

    def test_retire_on_a_corrupt_entry_fails_cleanly(self):
        self._write_broken_entry()
        code, _ = self.run_cli("retire", "broken")
        self.assertEqual(code, 1)

    # Task 8 gap: fields with no CLI path, and the waiting trap
    def test_set_persists_each_of_the_seven_fields(self):
        self.run_cli("add", "Probe", "--kind", "thread", "--area", "money")
        self.run_cli(
            "set", "probe",
            "--waiting-on", "Alex",
            "--waiting-since", "2026-10-01",
            "--wake", "november",
            "--due", "2026-12-01",
            "--repo", "/some/repo",
            "--cadence", "3",
            "--next", "ping them",
        )
        from homebase.store import load_one
        entry = load_one(self.root / "entries", "probe")
        self.assertEqual(entry.waiting_on, "Alex")
        self.assertEqual(entry.waiting_since, date(2026, 10, 1))
        self.assertEqual(entry.wake, "november")
        self.assertEqual(entry.due, date(2026, 12, 1))
        self.assertEqual(entry.repo, "/some/repo")
        self.assertEqual(entry.cadence_days, 3)
        self.assertEqual(entry.next_action, "ping them")

    def test_set_cadence_zero_persists(self):
        # cadence_days=0 ("tracked without pressure") is the single most
        # meaningful value this field takes. A truthy check (`if
        # args.cadence:`) would silently treat 0 as "not given" and leave
        # the previous cadence in place — this test must fail if that
        # regression is introduced.
        self.run_cli("add", "Probe", "--kind", "project", "--area", "home",
                     "--cadence", "7")
        self.run_cli("set", "probe", "--cadence", "0")
        from homebase.store import load_one
        entry = load_one(self.root / "entries", "probe")
        self.assertEqual(entry.cadence_days, 0)

    def test_set_next_empty_string_persists(self):
        # An empty string is a legitimate value for --next (clearing it),
        # not "omitted". A truthy check would drop it silently.
        self.run_cli("add", "Probe", "--kind", "project", "--area", "home",
                     "--next", "do the thing")
        self.run_cli("set", "probe", "--next", "")
        from homebase.store import load_one
        entry = load_one(self.root / "entries", "probe")
        self.assertEqual(entry.next_action, "")

    def test_set_omitted_flag_leaves_existing_value_unchanged(self):
        self.run_cli("add", "Probe", "--kind", "thread", "--area", "money")
        self.run_cli("set", "probe", "--waiting-on", "Alex")
        self.run_cli("set", "probe", "--due", "2026-12-01")
        from homebase.store import load_one
        entry = load_one(self.root / "entries", "probe")
        self.assertEqual(entry.waiting_on, "Alex")
        self.assertEqual(entry.due, date(2026, 12, 1))

    def test_set_with_no_flags_is_a_usage_error(self):
        self.run_cli("add", "Probe", "--kind", "thread", "--area", "money")
        code, _ = self.run_cli("set", "probe")
        self.assertEqual(code, 2)

    def test_set_unknown_id_fails(self):
        code, _ = self.run_cli("set", "ghost", "--waiting-on", "Alex")
        self.assertEqual(code, 1)

    def test_set_on_a_corrupt_entry_fails_cleanly(self):
        self._write_broken_entry()
        code, _ = self.run_cli("set", "broken", "--waiting-on", "Alex")
        self.assertEqual(code, 1)

    def test_set_rejects_a_malformed_due_date(self):
        self.run_cli("add", "Probe", "--kind", "thread", "--area", "money")
        code, _ = self.run_cli("set", "probe", "--due", "not-a-date")
        self.assertEqual(code, 2)

    def test_state_waiting_defaults_waiting_since_to_today(self):
        self.run_cli("add", "Probe", "--kind", "thread", "--area", "money")
        self.run_cli("state", "probe", "waiting")
        from homebase.store import load_one
        entry = load_one(self.root / "entries", "probe")
        self.assertEqual(entry.waiting_since, TODAY)

    def test_state_waiting_leaves_existing_waiting_since_alone(self):
        self.run_cli("add", "Probe", "--kind", "thread", "--area", "money")
        self.run_cli("set", "probe", "--waiting-since", "2026-09-01")
        self.run_cli("state", "probe", "waiting")
        from homebase.store import load_one
        entry = load_one(self.root / "entries", "probe")
        self.assertEqual(entry.waiting_since, date(2026, 9, 1))

    def test_waiting_thread_surfaces_once_stale(self):
        self.run_cli("add", "Probe thread", "--kind", "thread", "--area", "money")
        self.run_cli("state", "probe-thread", "waiting")
        self.run_cli("set", "probe-thread", "--waiting-since", "2026-09-01")
        code, out = self.run_cli("brief")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["items"][0]["bucket"], "stale_waiting")

    # C1(a): --wake must be validated at the CLI boundary, exactly like --due.
    def test_set_wake_rejects_garbage(self):
        self.run_cli("add", "Gutter cleaning", "--kind", "recurring", "--area", "home")
        code, _ = self.run_cli("set", "gutter-cleaning", "--wake", "next June")
        self.assertEqual(code, 2)
        from homebase.store import load_one
        entry = load_one(self.root / "entries", "gutter-cleaning")
        self.assertIsNone(entry.wake)

    def test_set_wake_accepts_month_name_case_insensitive(self):
        self.run_cli("add", "Gutter cleaning", "--kind", "recurring", "--area", "home")
        code, _ = self.run_cli("set", "gutter-cleaning", "--wake", "JUNE")
        self.assertEqual(code, 0)
        from homebase.store import load_one
        entry = load_one(self.root / "entries", "gutter-cleaning")
        self.assertEqual(entry.wake, "JUNE")

    def test_set_wake_accepts_iso_date(self):
        self.run_cli("add", "Gutter cleaning", "--kind", "recurring", "--area", "home")
        code, _ = self.run_cli("set", "gutter-cleaning", "--wake", "2027-06-01")
        self.assertEqual(code, 0)

    # C1(b): a seasonal entry with no wake at all must not vanish silently —
    # this is the exact sequence from the review: state -> seasonal, no wake set.
    def test_seasonal_entry_with_no_wake_is_flagged_not_silent(self):
        self.run_cli("add", "Gutter cleaning", "--kind", "recurring", "--area", "home")
        self.run_cli("state", "gutter-cleaning", "seasonal")
        code, out = self.run_cli("brief")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertIn({"id": "gutter-cleaning", "flag": "wake_unresolvable"}, payload["flags"])
        self.assertFalse(payload["silent"])

    # C3: touch on an encoding-broken entry must fail cleanly, not traceback.
    def test_touch_on_an_encoding_broken_entry_fails_cleanly(self):
        self._write_bad_encoding_entry()
        code, _ = self.run_cli("touch", "badenc")
        self.assertEqual(code, 1)

    # hb scan: zero CLI-level coverage before this review, despite writing to disk.
    def test_scan_with_no_repos_does_nothing(self):
        self.run_cli("add", "Painting", "--kind", "project", "--area", "home")
        code, out = self.run_cli("scan")
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_scan_updates_last_touched_from_git_and_prints_the_id(self):
        import subprocess
        repo_dir = self.root / "repo"
        repo_dir.mkdir()
        run = lambda *a: subprocess.run(
            ["git", *a], cwd=repo_dir, check=True, capture_output=True,
            env={"PATH": "/usr/bin:/bin", "HOME": str(repo_dir),
                 "GIT_AUTHOR_DATE": "2026-10-20T12:00:00",
                 "GIT_COMMITTER_DATE": "2026-10-20T12:00:00",
                 "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t",
                 "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t"},
        )
        run("init", "-q")
        (repo_dir / "f.txt").write_text("x")
        run("add", "f.txt")
        run("commit", "-q", "-m", "c")

        self.run_cli("add", "Garden", "--kind", "project", "--area", "software",
                     "--repo", str(repo_dir))
        path = self.root / "entries" / "garden.md"
        path.write_text(path.read_text().replace("2026-10-23", "2026-01-01"))

        code, out = self.run_cli("scan")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "garden")
        self.assertIn("last_touched = 2026-10-20", path.read_text())


if __name__ == "__main__":
    unittest.main()
