import unittest
from datetime import date
from homebase.entry import Entry, parse_entry, EntryParseError

FULL = """+++
name = "Side Project"
kind = "project"
area = "software"
state = "active"
next = "write the first draft of the spec"
cadence_days = 7
last_touched = 2026-10-06
repo = "/home/user/code/side-project"
links = ["docs/prd.md"]
+++

A weekend project. Mostly notes.
"""


class TestParse(unittest.TestCase):
    def test_parses_all_fields(self):
        e = parse_entry(FULL, "side-project")
        self.assertEqual(e.id, "side-project")
        self.assertEqual(e.name, "Side Project")
        self.assertEqual(e.kind, "project")
        self.assertEqual(e.state, "active")
        self.assertEqual(e.next_action, "write the first draft of the spec")
        self.assertEqual(e.cadence_days, 7)
        self.assertEqual(e.last_touched, date(2026, 10, 6))
        self.assertEqual(e.links, ["docs/prd.md"])
        self.assertIn("Mostly notes.", e.body)

    def test_minimal_entry_gets_defaults(self):
        text = '+++\nname = "Reading"\nkind = "project"\narea = "faith"\nlast_touched = 2026-10-23\n+++\n'
        e = parse_entry(text, "reading")
        self.assertEqual(e.state, "active")
        self.assertEqual(e.cadence_days, 7)
        self.assertIsNone(e.next_action)
        self.assertEqual(e.links, [])
        self.assertEqual(e.body, "")

    def test_missing_delimiter_raises(self):
        with self.assertRaises(EntryParseError):
            parse_entry('name = "x"\n', "x")

    def test_bad_toml_raises(self):
        with self.assertRaises(EntryParseError):
            parse_entry('+++\nname = = "x"\n+++\n', "x")

    def test_bad_enum_raises(self):
        text = '+++\nname = "x"\nkind = "wat"\narea = "home"\nlast_touched = 2026-10-23\n+++\n'
        with self.assertRaises(EntryParseError):
            parse_entry(text, "x")


class TestRoundTrip(unittest.TestCase):
    def test_round_trip_preserves_everything(self):
        original = parse_entry(FULL, "side-project")
        again = parse_entry(original.to_text(), "side-project")
        self.assertEqual(original, again)

    def test_round_trip_with_quotes_in_text(self):
        e = parse_entry(FULL, "x")
        e.next_action = 'ask "what now" \\ then stop'
        again = parse_entry(e.to_text(), "x")
        self.assertEqual(again.next_action, 'ask "what now" \\ then stop')

    def test_round_trip_optional_dates(self):
        e = parse_entry(FULL, "x")
        e.due = date(2026, 11, 1)
        e.waiting_since = date(2026, 10, 2)
        e.waiting_on = "Sam @ the shop"
        again = parse_entry(e.to_text(), "x")
        self.assertEqual(again.due, date(2026, 11, 1))
        self.assertEqual(again.waiting_since, date(2026, 10, 2))
        self.assertEqual(again.waiting_on, "Sam @ the shop")

    def test_round_trip_with_newline_in_next_action(self):
        """Verify literal newlines in string fields survive round-trip."""
        e = parse_entry(FULL, "x")
        e.next_action = "first line\nsecond line"
        again = parse_entry(e.to_text(), "x")
        self.assertEqual(again.next_action, "first line\nsecond line")

    def test_round_trip_with_control_characters(self):
        """Verify control chars (\\r, tab, etc.) survive round-trip."""
        e = parse_entry(FULL, "x")
        e.waiting_on = "contact\rCarriage\treturn\x07bell"
        again = parse_entry(e.to_text(), "x")
        self.assertEqual(again.waiting_on, "contact\rCarriage\treturn\x07bell")

    def test_round_trip_with_newline_in_links(self):
        """Verify newlines in list elements survive round-trip."""
        e = parse_entry(FULL, "x")
        e.links = ["docs/prd.md", "notes\nwith newline"]
        again = parse_entry(e.to_text(), "x")
        self.assertEqual(again.links, ["docs/prd.md", "notes\nwith newline"])


if __name__ == "__main__":
    unittest.main()
