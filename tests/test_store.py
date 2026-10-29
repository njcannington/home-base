import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

from homebase.entry import Entry, EntryParseError
from homebase.store import load_all, load_one, save, retire, EntryNotFound


def make(entry_id, **kw):
    defaults = dict(
        id=entry_id, name=entry_id.title(), kind="project",
        area="home", last_touched=date(2026, 10, 1),
    )
    defaults.update(kw)
    return Entry(**defaults)


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.entries = Path(self.tmp.name) / "entries"
        self.graveyard = Path(self.tmp.name) / "graveyard"
        self.entries.mkdir()
        self.graveyard.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_then_load_round_trip(self):
        save(self.entries, make("painting", next_action="second coat"))
        entries, errors = load_all(self.entries)
        self.assertEqual(errors, [])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].id, "painting")
        self.assertEqual(entries[0].next_action, "second coat")

    def test_load_all_sorted_by_id(self):
        for name in ("zulu", "alpha", "mike"):
            save(self.entries, make(name))
        entries, _ = load_all(self.entries)
        self.assertEqual([e.id for e in entries], ["alpha", "mike", "zulu"])

    def test_empty_dir_is_not_an_error(self):
        entries, errors = load_all(self.entries)
        self.assertEqual(entries, [])
        self.assertEqual(errors, [])

    def test_missing_dir_is_not_an_error(self):
        entries, errors = load_all(Path(self.tmp.name) / "nope")
        self.assertEqual(entries, [])
        self.assertEqual(errors, [])

    # Review Focus 1: one broken file must not take down the brief
    def test_broken_file_is_skipped_and_reported(self):
        save(self.entries, make("good"))
        (self.entries / "broken.md").write_text('+++\nname = = "x"\n+++\n')
        entries, errors = load_all(self.entries)
        self.assertEqual([e.id for e in entries], ["good"])
        self.assertEqual(len(errors), 1)
        self.assertIn("broken", errors[0])

    def test_non_markdown_files_ignored(self):
        save(self.entries, make("good"))
        (self.entries / "README.txt").write_text("not an entry")
        entries, errors = load_all(self.entries)
        self.assertEqual([e.id for e in entries], ["good"])
        self.assertEqual(errors, [])

    def test_load_one(self):
        save(self.entries, make("garden"))
        self.assertEqual(load_one(self.entries, "garden").id, "garden")

    def test_load_one_missing_raises(self):
        with self.assertRaises(EntryNotFound):
            load_one(self.entries, "ghost")

    def test_retire_moves_file_and_sets_state(self):
        save(self.entries, make("treehouse"))
        retire(self.entries, self.graveyard, "treehouse")
        self.assertFalse((self.entries / "treehouse.md").exists())
        self.assertTrue((self.graveyard / "treehouse.md").exists())
        buried, _ = load_all(self.graveyard)
        self.assertEqual(buried[0].state, "dead")

    def test_retire_missing_raises(self):
        with self.assertRaises(EntryNotFound):
            retire(self.entries, self.graveyard, "ghost")

    def test_non_utf8_file_is_skipped_and_reported(self):
        save(self.entries, make("good"))
        (self.entries / "badencoding.md").write_bytes(b'+++\nname = "\xff\xfe"\n+++\n')
        entries, errors = load_all(self.entries)
        self.assertEqual([e.id for e in entries], ["good"])
        self.assertEqual(len(errors), 1)
        self.assertIn("badencoding", errors[0])

    # C3: load_one must raise EntryParseError on an encoding-broken file,
    # not let UnicodeDecodeError escape (the CLI only handles EntryParseError).
    def test_load_one_on_encoding_broken_file_raises_entry_parse_error(self):
        (self.entries / "badenc.md").write_bytes(b'+++\nname = "\xff\xfe"\n+++\n')
        with self.assertRaises(EntryParseError):
            load_one(self.entries, "badenc")

    # C3: save()'s pre-write "is it already identical" check must not crash
    # when the existing on-disk file is encoding-broken — it should just
    # treat it as different and overwrite, same as any other OSError.
    def test_save_overwrites_an_encoding_broken_existing_file(self):
        path = self.entries / "garden.md"
        path.write_bytes(b'+++\nname = "\xff\xfe"\n+++\n')
        save(self.entries, make("garden"))
        self.assertIn("Garden", path.read_text())

    def test_unreadable_entries_dir_is_reported(self):
        save(self.entries, make("good"))
        # Make directory completely unreadable so iterating fails
        os.chmod(self.entries, 0o000)
        try:
            entries, errors = load_all(self.entries)
            self.assertEqual(entries, [])
            self.assertEqual(len(errors), 1)
            self.assertIn("unreadable", errors[0])
        finally:
            # Restore permissions so cleanup can happen
            os.chmod(self.entries, 0o755)

    def test_save_skips_rewrite_when_content_is_unchanged(self):
        entry = make("garden")
        save(self.entries, entry)
        path = self.entries / "garden.md"
        past = date(2020, 1, 1).toordinal() * 86400  # arbitrary known-past epoch seconds
        os.utime(path, (past, past))
        before = os.stat(path).st_mtime
        save(self.entries, make("garden"))  # identical content, fresh object
        after = os.stat(path).st_mtime
        self.assertEqual(before, after)

    def test_save_rewrites_when_content_changed(self):
        save(self.entries, make("garden"))
        path = self.entries / "garden.md"
        past = date(2020, 1, 1).toordinal() * 86400
        os.utime(path, (past, past))
        before = os.stat(path).st_mtime
        save(self.entries, make("garden", next_action="ship it"))
        after = os.stat(path).st_mtime
        self.assertNotEqual(before, after)
        self.assertIn("ship it", path.read_text())

    def test_retire_cleans_up_graveyard_on_unlink_failure(self):
        save(self.entries, make("locked"))
        initial_mode = os.stat(self.entries).st_mode
        # Make entries directory read-only so unlink will fail
        os.chmod(self.entries, 0o555)
        try:
            # Attempt to retire - unlink will fail
            try:
                retire(self.entries, self.graveyard, "locked")
            except OSError:
                # Expected: unlink failed because directory is read-only
                pass
            # After rollback, graveyard should be cleaned up (no orphan)
            self.assertFalse((self.graveyard / "locked.md").exists())
        finally:
            # Restore permissions so original file can be deleted
            os.chmod(self.entries, initial_mode)


if __name__ == "__main__":
    unittest.main()
