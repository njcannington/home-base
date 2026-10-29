import unittest
from datetime import date, timedelta

from homebase.entry import Entry
from homebase.brief import build_brief, BUCKET_ORDER, STALE_WAITING_DAYS, UPCOMING_DAYS
from homebase.decay import apply_decay

TODAY = date(2026, 10, 23)


def make(entry_id, **kw):
    defaults = dict(
        id=entry_id, name=entry_id.title(), kind="project", area="home",
        last_touched=TODAY, state="active", cadence_days=7,
    )
    defaults.update(kw)
    return Entry(**defaults)


def ids(brief):
    return [i["id"] for i in brief["items"]]


class SilenceTest(unittest.TestCase):
    # Review Focus 5
    def test_empty_ledger_is_silent(self):
        brief = build_brief([], TODAY)
        self.assertTrue(brief["silent"])
        self.assertEqual(brief["items"], [])

    def test_all_dead_or_done_is_silent(self):
        entries = [make("a", state="dead"), make("b", kind="commitment", state="done")]
        self.assertTrue(build_brief(entries, TODAY)["silent"])

    def test_active_with_no_next_is_silent(self):
        self.assertTrue(build_brief([make("a")], TODAY)["silent"])

    def test_errors_break_silence(self):
        brief = build_brief([], TODAY, errors=["broken: bad TOML"])
        self.assertFalse(brief["silent"])


class SelectionTest(unittest.TestCase):
    # Review Focus 3: cadence 0 never surfaces
    def test_cadence_zero_never_surfaces(self):
        entries = [
            make("journal", cadence_days=0, state="idling", next_action="log today"),
            make("reading", cadence_days=0, state="active"),
        ]
        self.assertEqual(ids(build_brief(entries, TODAY)), [])

    def test_cadence_zero_surfaces_when_given_a_due_date(self):
        e = make("journal", cadence_days=0, kind="commitment", due=date(2026, 10, 24))
        self.assertEqual(ids(build_brief([e], TODAY)), ["journal"])

    def test_overdue_commitment(self):
        e = make("dinner", kind="commitment", due=date(2026, 10, 20))
        brief = build_brief([e], TODAY)
        self.assertEqual(brief["items"][0]["bucket"], "overdue")
        self.assertIn("3 days", brief["items"][0]["detail"])

    def test_due_within_three_days(self):
        e = make("dinner", kind="commitment", due=date(2026, 10, 26))
        self.assertEqual(build_brief([e], TODAY)["items"][0]["bucket"], "due_soon")

    def test_due_beyond_upcoming_window_not_shown(self):
        # Beyond 14 days out, entries stay invisible (only upcoming within 14 days shows)
        e = make("future", kind="commitment", due=date(2026, 11, 7))
        self.assertEqual(ids(build_brief([e], TODAY)), [])

    def test_upcoming_due_in_nine_days_with_no_next_action(self):
        # Dinner club on 2026-11-01, today is 2026-10-23 (9 days away)
        # This was the real defect: due dates 4-14 days away should surface
        e = make("dinner-club", kind="commitment", due=date(2026, 11, 1))
        item = build_brief([e], TODAY)["items"][0]
        self.assertEqual(item["bucket"], "upcoming")
        self.assertEqual(item["detail"], "9 days")

    def test_upcoming_due_in_nine_days_with_next_action_still_upcoming(self):
        # Even with a next_action, a dated commitment still lands in upcoming
        e = make("dinner-club", kind="commitment", due=date(2026, 11, 1),
                 next_action="buy groceries")
        item = build_brief([e], TODAY)["items"][0]
        self.assertEqual(item["bucket"], "upcoming")
        self.assertEqual(item["detail"], "9 days")

    def test_upcoming_due_in_20_days_is_invisible(self):
        # Beyond UPCOMING_DAYS (14), entries stay invisible
        e = make("far_future", kind="commitment", due=date(2026, 11, 12))
        self.assertEqual(ids(build_brief([e], TODAY)), [])

    def test_due_soon_boundary_two_days_not_upcoming(self):
        # 2 days away is due_soon, not upcoming
        e = make("soon", kind="commitment", due=date(2026, 10, 25))
        self.assertEqual(build_brief([e], TODAY)["items"][0]["bucket"], "due_soon")

    def test_due_in_exactly_three_days_is_due_soon(self):
        # The due_soon/upcoming edge: days_until == DUE_SOON_DAYS (3) is still due_soon.
        e = make("edge", kind="commitment", due=date(2026, 10, 26))
        self.assertEqual(build_brief([e], TODAY)["items"][0]["bucket"], "due_soon")

    def test_due_in_exactly_four_days_is_upcoming(self):
        # One day past the due_soon/upcoming edge: days_until == 4 is upcoming.
        e = make("edge", kind="commitment", due=date(2026, 10, 27))
        self.assertEqual(build_brief([e], TODAY)["items"][0]["bucket"], "upcoming")

    def test_due_in_exactly_fourteen_days_is_upcoming(self):
        # The upcoming/invisible edge: days_until == UPCOMING_DAYS (14) is still upcoming.
        e = make("edge", kind="commitment", due=date(2026, 11, 6))
        self.assertEqual(build_brief([e], TODAY)["items"][0]["bucket"], "upcoming")

    def test_due_in_exactly_fifteen_days_is_invisible(self):
        # One day past the upcoming/invisible edge: days_until == 15 is invisible.
        e = make("edge", kind="commitment", due=date(2026, 11, 7))
        self.assertEqual(ids(build_brief([e], TODAY)), [])

    def test_waiting_with_no_waiting_since_is_invisible(self):
        # A "waiting" entry whose waiting_since was never set (e.g. hand-edited
        # or set via a path that skips the CLI's auto-stamp) must not crash
        # and must not surface — there's no way to compute staleness.
        e = make("probe", kind="thread", state="waiting", waiting_on="Alex",
                 waiting_since=None)
        self.assertEqual(ids(build_brief([e], TODAY)), [])

    def test_upcoming_outranks_stale_waiting_and_idling(self):
        # upcoming should sort before stale_waiting and idling
        entries = [
            make("idle", state="idling", next_action="go"),
            make("waiting", kind="thread", state="waiting",
                 waiting_on="Someone", waiting_since=date(2026, 10, 2)),
            make("due", kind="commitment", due=date(2026, 11, 1)),
        ]
        brief = build_brief(entries, TODAY)
        self.assertEqual(ids(brief), ["due", "waiting", "idle"])

    def test_idling_sorted_by_last_touched_most_recent_first(self):
        # When multiple idling entries exist, most recently touched should come first
        entries = [
            make("old", state="idling", last_touched=date(2026, 8, 10)),  # 74 days ago
            make("recent", state="idling", last_touched=date(2026, 10, 20)),  # 3 days ago
            make("middle", state="idling", last_touched=date(2026, 9, 20)),  # 33 days ago
        ]
        brief = build_brief(entries, TODAY)
        self.assertEqual(ids(brief), ["recent", "middle", "old"])

    def test_cadence_zero_with_upcoming_due_date_surfaces(self):
        # Even with cadence_days=0, a due date in upcoming window surfaces
        e = make("unused", cadence_days=0, kind="commitment", due=date(2026, 11, 1))
        item = build_brief([e], TODAY)["items"][0]
        self.assertEqual(item["bucket"], "upcoming")

    def test_done_commitment_never_shown_even_if_overdue(self):
        e = make("old", kind="commitment", state="done", due=date(2020, 1, 1))
        self.assertEqual(ids(build_brief([e], TODAY)), [])

    def test_stale_waiting_thread(self):
        e = make("sam", kind="thread", state="waiting",
                 waiting_on="Sam", waiting_since=date(2026, 10, 2))
        item = build_brief([e], TODAY)["items"][0]
        self.assertEqual(item["bucket"], "stale_waiting")
        self.assertIn("21 days", item["detail"])

    def test_fresh_waiting_thread_not_shown(self):
        e = make("sam", kind="thread", state="waiting",
                 waiting_since=TODAY - timedelta(days=STALE_WAITING_DAYS))
        self.assertEqual(ids(build_brief([e], TODAY)), [])

    def test_idling_with_next_is_shown(self):
        e = make("painting", state="idling", next_action="second coat")
        self.assertEqual(build_brief([e], TODAY)["items"][0]["bucket"], "idling")

    def test_idling_without_next_is_shown_as_needing_one(self):
        e = make("painting", state="idling")
        item = build_brief([e], TODAY)["items"][0]
        self.assertEqual(item["bucket"], "idling")
        self.assertIsNone(item["next"])

    def test_active_with_next_is_shown_last(self):
        e = make("sfn", state="active", next_action="dashboard")
        self.assertEqual(build_brief([e], TODAY)["items"][0]["bucket"], "active")

    def test_waking_seasonal_with_no_next_action(self):
        # October is current month, so October won't wake until next year.
        # June has already passed, so it's waiting for next June.
        # Need a month that's in the future: November or later.
        e = make("league", state="active", wake="november")
        # November hasn't arrived yet (today is October 23)
        self.assertEqual(ids(build_brief([e], TODAY)), [])

    def test_waking_seasonal_when_wake_arrives_and_no_next_action(self):
        # Create a seasonal entry that has woken (state=active, wake set)
        e = make("league", state="active", wake="october")
        # October has arrived (today is October 23)
        item = build_brief([e], TODAY)["items"][0]
        self.assertEqual(item["bucket"], "waking")
        self.assertEqual(item["detail"], "october reached")

    def test_waking_entry_with_next_action_lands_in_active_not_waking(self):
        # If a woken entry has a next_action, it should be active, not waking
        e = make("league", state="active", wake="october", next_action="schedule game")
        item = build_brief([e], TODAY)["items"][0]
        self.assertEqual(item["bucket"], "active")

    def test_waking_scenario_end_to_end_with_apply_decay(self):
        # Real scenario: seasonal entry with wake="june", no next_action
        # Run it through apply_decay then build_brief
        # For this test, use a date in June so apply_decay will wake it
        june_date = date(2026, 6, 15)
        e = make("gutters", state="seasonal", wake="june")
        # Apply decay at June date - should convert to active
        apply_decay([e], june_date)
        self.assertEqual(e.state, "active")
        # Now build_brief should show it as waking since wake has been reached
        item = build_brief([e], june_date)["items"][0]
        self.assertEqual(item["bucket"], "waking")

    def test_cadence_zero_with_reached_wake_but_no_due_stays_invisible(self):
        # cadence_days=0 with wake that has arrived but no due date should stay invisible
        e = make("unused", cadence_days=0, state="active", wake="october")
        self.assertEqual(ids(build_brief([e], TODAY)), [])

    def test_raw_seasonal_with_reached_wake_surfaces_as_waking(self):
        # Critical test: raw state="seasonal" entry (not yet converted by apply_decay)
        # with a reached wake and no next_action must still surface as waking.
        # This tests that waking is independent of entry.state.
        e = make("league", state="seasonal", wake="october")
        item = build_brief([e], TODAY)["items"][0]
        self.assertEqual(item["bucket"], "waking")
        self.assertEqual(item["detail"], "october reached")


class OrderingTest(unittest.TestCase):
    def test_bucket_order_is_fixed(self):
        self.assertEqual(
            BUCKET_ORDER,
            ["overdue", "due_soon", "upcoming", "stale_waiting", "idling", "waking", "active"],
        )

    def test_items_come_back_in_bucket_order(self):
        entries = [
            make("act", state="active", next_action="go"),
            make("idle", state="idling", next_action="go"),
            make("over", kind="commitment", due=date(2026, 10, 1)),
        ]
        self.assertEqual(ids(build_brief(entries, TODAY)), ["over", "idle", "act"])


class CapTest(unittest.TestCase):
    def test_caps_at_seven_and_counts_the_rest(self):
        entries = [make(f"e{n}", state="idling", next_action="go") for n in range(10)]
        brief = build_brief(entries, TODAY)
        self.assertEqual(len(brief["items"]), 7)
        self.assertEqual(brief["suppressed"]["idling"], 3)

    def test_under_cap_suppresses_nothing(self):
        entries = [make(f"e{n}", state="idling", next_action="go") for n in range(3)]
        self.assertEqual(build_brief(entries, TODAY)["suppressed"], {})

    def test_cap_keeps_the_most_urgent(self):
        entries = [make(f"i{n}", state="idling", next_action="go") for n in range(7)]
        entries.append(make("urgent", kind="commitment", due=date(2026, 10, 1)))
        self.assertIn("urgent", ids(build_brief(entries, TODAY)))


class FlagTest(unittest.TestCase):
    def test_repo_not_git_is_flagged(self):
        e = make("garden", repo="/home/user/code/garden", repo_is_git=False)
        brief = build_brief([e], TODAY)
        self.assertEqual(brief["flags"], [{"id": "garden", "flag": "repo_not_git"}])
        self.assertFalse(brief["silent"])

    def test_flags_do_not_consume_the_item_cap(self):
        entries = [make(f"e{n}", state="idling", next_action="go") for n in range(7)]
        entries.append(make("garden", repo="/x", repo_is_git=False))
        brief = build_brief(entries, TODAY)
        self.assertEqual(len(brief["items"]), 7)
        self.assertEqual(len(brief["flags"]), 1)

    # C1(b): a seasonal entry with no wake at all vanishes silently without this.
    def test_seasonal_entry_with_no_wake_is_flagged_unresolvable(self):
        e = make("gutter-cleaning", kind="recurring", state="seasonal", wake=None)
        brief = build_brief([e], TODAY)
        self.assertEqual(brief["flags"], [{"id": "gutter-cleaning", "flag": "wake_unresolvable"}])
        self.assertFalse(brief["silent"])

    # C1(b): a hand-edited wake value that isn't a MONTHS name or ISO date.
    def test_seasonal_entry_with_garbage_wake_is_flagged_unresolvable(self):
        e = make("gutter-cleaning", kind="recurring", state="seasonal", wake="next June")
        brief = build_brief([e], TODAY)
        self.assertEqual(brief["flags"], [{"id": "gutter-cleaning", "flag": "wake_unresolvable"}])

    def test_seasonal_entry_with_valid_wake_is_not_flagged(self):
        e = make("gutter-cleaning", kind="recurring", state="seasonal", wake="june")
        self.assertEqual(build_brief([e], TODAY)["flags"], [])

    def test_wake_unresolvable_not_flagged_for_dead_or_done(self):
        # Hidden states are excluded, same as repo_not_git.
        e = make("gutter-cleaning", kind="recurring", state="dead", wake=None)
        self.assertEqual(build_brief([e], TODAY)["flags"], [])


class UrgencyOrderingTest(unittest.TestCase):
    # C5: within a dated bucket, order by due ascending (most urgent first),
    # not by filename/insertion order.
    def test_overdue_bucket_orders_by_most_overdue_first(self):
        entries = [
            make("mango-overdue-1", kind="commitment", due=date(2026, 10, 22)),
            make("beta-overdue-20", kind="commitment", due=date(2026, 10, 3)),
        ]
        self.assertEqual(ids(build_brief(entries, TODAY)), ["beta-overdue-20", "mango-overdue-1"])

    def test_due_soon_bucket_orders_by_due_ascending(self):
        entries = [
            make("zulu", kind="commitment", due=date(2026, 10, 26)),
            make("alpha", kind="commitment", due=date(2026, 10, 24)),
        ]
        self.assertEqual(ids(build_brief(entries, TODAY)), ["alpha", "zulu"])

    def test_upcoming_bucket_orders_by_due_ascending(self):
        entries = [
            make("zulu", kind="commitment", due=date(2026, 11, 5)),
            make("alpha", kind="commitment", due=date(2026, 10, 30)),
        ]
        self.assertEqual(ids(build_brief(entries, TODAY)), ["alpha", "zulu"])

    def test_stale_waiting_bucket_orders_by_wait_descending(self):
        entries = [
            make("zulu", kind="thread", state="waiting", waiting_on="A",
                 waiting_since=date(2026, 10, 1)),   # waited 22 days
            make("alpha", kind="thread", state="waiting", waiting_on="B",
                 waiting_since=date(2026, 9, 1)),    # waited 52 days, more stale
        ]
        self.assertEqual(ids(build_brief(entries, TODAY)), ["alpha", "zulu"])


if __name__ == "__main__":
    unittest.main()
