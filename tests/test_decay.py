import unittest
from datetime import date

from homebase.entry import Entry
from homebase.decay import apply_decay, wake_date

TODAY = date(2026, 10, 23)


def make(entry_id="x", **kw):
    defaults = dict(
        id=entry_id, name="X", kind="project", area="home",
        last_touched=TODAY, state="active", cadence_days=7,
    )
    defaults.update(kw)
    return Entry(**defaults)


class DecayTest(unittest.TestCase):
    def test_active_past_cadence_goes_idling(self):
        e = make(last_touched=date(2026, 10, 1), cadence_days=7)
        changed = apply_decay([e], TODAY)
        self.assertEqual(e.state, "idling")
        self.assertEqual(changed, [e])

    # Review Focus 4: the boundary. 7 days elapsed with cadence 7 is NOT decayed.
    def test_exactly_at_cadence_does_not_decay(self):
        e = make(last_touched=date(2026, 10, 16), cadence_days=7)
        self.assertEqual((TODAY - e.last_touched).days, 7)
        apply_decay([e], TODAY)
        self.assertEqual(e.state, "active")

    def test_one_day_past_cadence_decays(self):
        e = make(last_touched=date(2026, 10, 15), cadence_days=7)
        apply_decay([e], TODAY)
        self.assertEqual(e.state, "idling")

    # Review Focus 3: cadence 0 never decays
    def test_cadence_zero_never_decays(self):
        e = make(last_touched=date(2020, 1, 1), cadence_days=0)
        changed = apply_decay([e], TODAY)
        self.assertEqual(e.state, "active")
        self.assertEqual(changed, [])

    def test_idling_stays_idling(self):
        e = make(state="idling", last_touched=date(2020, 1, 1))
        changed = apply_decay([e], TODAY)
        self.assertEqual(e.state, "idling")
        self.assertEqual(changed, [])

    def test_dead_and_done_never_change(self):
        dead = make("d", state="dead", last_touched=date(2020, 1, 1))
        done = make("n", state="done", last_touched=date(2020, 1, 1))
        self.assertEqual(apply_decay([dead, done], TODAY), [])
        self.assertEqual(dead.state, "dead")
        self.assertEqual(done.state, "done")

    def test_waiting_does_not_decay_to_idling(self):
        e = make(state="waiting", last_touched=date(2026, 1, 1))
        apply_decay([e], TODAY)
        self.assertEqual(e.state, "waiting")

    def test_seasonal_wakes_on_its_month(self):
        e = make(state="seasonal", wake="october")
        changed = apply_decay([e], TODAY)
        self.assertEqual(e.state, "active")
        self.assertEqual(changed, [e])

    def test_seasonal_stays_asleep_before_its_month(self):
        e = make(state="seasonal", wake="june")
        apply_decay([e], TODAY)
        self.assertEqual(e.state, "seasonal")

    def test_seasonal_wakes_on_explicit_date(self):
        e = make(state="seasonal", wake="2026-10-20")
        apply_decay([e], TODAY)
        self.assertEqual(e.state, "active")

    def test_seasonal_with_no_wake_stays_asleep(self):
        e = make(state="seasonal", wake=None)
        apply_decay([e], TODAY)
        self.assertEqual(e.state, "seasonal")

    def test_seasonal_with_garbage_wake_stays_asleep(self):
        e = make(state="seasonal", wake="whenever")
        apply_decay([e], TODAY)
        self.assertEqual(e.state, "seasonal")


class WakeDateTest(unittest.TestCase):
    def test_month_name_this_year(self):
        self.assertEqual(wake_date("december", TODAY), date(2026, 12, 1))

    def test_month_name_is_case_insensitive(self):
        self.assertEqual(wake_date("JUNE", TODAY), wake_date("june", TODAY))
        self.assertEqual(wake_date("JUNE", TODAY).month, 6)

    def test_month_already_past_this_year_rolls_to_next_year(self):
        # June is behind us on 2026-10-23, so the league sleeps until 2027.
        self.assertEqual(wake_date("june", TODAY), date(2027, 6, 1))

    def test_current_month_resolves_to_this_year(self):
        self.assertEqual(wake_date("october", TODAY), date(2026, 10, 1))

    def test_iso_date(self):
        self.assertEqual(wake_date("2027-03-15", TODAY), date(2027, 3, 15))

    def test_garbage_returns_none(self):
        self.assertIsNone(wake_date("soon", TODAY))


if __name__ == "__main__":
    unittest.main()
