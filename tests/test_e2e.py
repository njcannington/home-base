"""End-to-end check over a small on-disk ledger.

Writes real entry files, loads them through the store, and builds a brief.
The fixture is chosen so filenames sort opposite to their urgency-correct
order — this is what catches alphabetical-not-urgent ordering inside
dated buckets.
"""
import tempfile
import unittest
from datetime import date
from pathlib import Path

from homebase.brief import build_brief
from homebase.store import load_all

TODAY = date(2026, 10, 23)

FIXTURE = {
    "birthday-party": """+++
name = "Birthday party"
kind = "commitment"
area = "family"
state = "active"
next = "order the cake"
cadence_days = 7
last_touched = 2026-10-23
due = 2026-11-01
+++
""",
    "contractor-quote": """+++
name = "Contractor quote"
kind = "thread"
area = "home"
state = "waiting"
next = "chase the quote or drop it"
cadence_days = 14
last_touched = 2026-10-01
waiting_on = "Contractor"
waiting_since = 2026-10-01
+++
""",
    "bike-tune-up": """+++
name = "Bike tune-up"
kind = "project"
area = "home"
state = "active"
next = "replace the chain"
cadence_days = 7
last_touched = 2026-09-01
+++
""",
    "attic-insulation": """+++
name = "Attic insulation"
kind = "project"
area = "home"
state = "active"
next = "measure the joist spacing"
cadence_days = 7
last_touched = 2026-10-06
+++
""",
}


class OnDiskLedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.entries = Path(self.tmp.name) / "entries"
        self.entries.mkdir()
        for entry_id, text in FIXTURE.items():
            (self.entries / f"{entry_id}.md").write_text(text)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ledger_brief_ordering(self):
        entries, errors = load_all(self.entries)
        self.assertEqual(errors, [])

        brief = build_brief(entries, TODAY)

        items = brief["items"]
        self.assertEqual(items[0]["id"], "birthday-party")
        self.assertEqual(items[0]["bucket"], "upcoming")
        self.assertEqual(items[0]["detail"], "9 days")

        self.assertEqual(items[1]["id"], "contractor-quote")
        self.assertEqual(items[1]["bucket"], "stale_waiting")


if __name__ == "__main__":
    unittest.main()
