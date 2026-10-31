"""Part A of the setup and exit study: each definition of section 3.1, by hand.

The Step 5 fixtures supply a small calendar and leg bars. Each test pins one
quantity: the value at the closes, the cost of waiting for an exit fill, the
SPY move read from `C[-1]`, the thirds cut on the input alone, and the
single-mean bootstrap with its gaps.
"""

import unittest
from datetime import date
from decimal import Decimal

from options_alpha_lab import study_decomposition as sd
from options_alpha_lab import veto_exits as vx
from options_alpha_lab.evidence import Bar
from test_veto_exits import CALENDAR, DAYS, both, entry, merge, path, run


def bar(day: str, close: str) -> Bar:
    c = Decimal(close)
    return Bar(date.fromisoformat(day), c, c, c, c, Decimal("1"))


class BlockMean(unittest.TestCase):
    def test_a_constant_has_no_spread(self) -> None:
        m = sd.block_mean([2.0] * 30, repetitions=200)
        self.assertEqual((m.n, m.mean, m.low, m.high), (30, 2.0, 2.0, 2.0))

    def test_positions_outside_the_subset_or_without_a_value_are_gaps(self) -> None:
        values = [1.0, None, 100.0, 3.0] * 5
        subset = [True, True, False, True] * 5
        m = sd.block_mean(values, block=2, repetitions=200, subset=subset)
        self.assertEqual((m.n, m.missing, m.mean), (10, 5, 2.0))
        assert m.low is not None and m.high is not None
        self.assertTrue(1.0 <= m.low <= m.high <= 3.0)


class CloseValues(unittest.TestCase):
    def test_value_at_each_close_less_friction_and_debit(self) -> None:
        # Entry debit 3.00 + 0.05 central. Closes of 8, 9 and 12 Feb (13:00).
        bars = merge(both(DAYS[0], "15:55", 5.50, 2.00), both(DAYS[1], "15:45", 5.00, 2.00),
                     both(DAYS[2], "12:55", 4.00, 2.00))
        t = run(bars, "central")
        changes = sd.close_changes(entry(), t, path(bars), CALENDAR)
        self.assertEqual(changes, [40.0, -10.0, -110.0])

    def test_an_unmeasurable_close_is_none(self) -> None:
        # 9 Feb's last bar opens at 15:35: 25 minutes before the close, too old.
        bars = merge(both(DAYS[0], "15:55", 5.50, 2.00), both(DAYS[1], "15:35", 5.00, 2.00))
        t = run(bars, "central")
        self.assertEqual(sd.close_changes(entry(), t, path(bars), CALENDAR)[1:], [None, None])

    def test_no_path_gives_no_values(self) -> None:
        t = run({}, "central")
        self.assertEqual(sd.close_changes(entry(), t, None, CALENDAR), [None, None, None])


class ExitDelay(unittest.TestCase):
    def test_observations_waited_and_the_cost_of_waiting(self) -> None:
        # Step 5's stop-loss case: triggered at 10:15 on a value of 1.40,
        # filled at 10:25 at 1.30. Two observations, and 0.10 a share lost.
        bars = merge(both(DAYS[0], "10:10", 3.40, 2.00),
                     {"SPY240301C00495000": [(DAYS[0], "10:15", 3.30)]},
                     both(DAYS[0], "10:20", 3.30, 2.00))
        t = run(bars)
        d = sd.exit_delay(entry(), t, path(bars), CALENDAR)
        self.assertEqual((d.trigger, d.observations), ("stop_loss", 2))
        assert d.cost_usd is not None
        self.assertAlmostEqual(d.cost_usd, -10.0)

    def test_a_trigger_without_a_value_has_no_cost(self) -> None:
        # Session stop on 13 Feb with no bar in the 15 minutes before it.
        bars = merge(both(DAYS[3], "10:30", 5.10, 2.00))
        t = run(bars)
        self.assertEqual(t.trigger, "session_stop")
        d = sd.exit_delay(entry(), t, path(bars), CALENDAR)
        self.assertIsNone(d.cost_usd)
        self.assertGreater(d.observations, 2)


class SpyMove(unittest.TestCase):
    SPY = [bar("2024-02-07", "500"), bar("2024-02-08", "505"), bar("2024-02-09", "490"),
           bar("2024-02-12", "510")]

    def test_from_the_close_before_the_session_to_two_sessions_after(self) -> None:
        self.assertAlmostEqual(sd.spy_move("2024-02-08", self.SPY, "500") or 0.0, 2.0)

    def test_censored_when_c2_is_missing(self) -> None:
        self.assertIsNone(sd.spy_move("2024-02-09", self.SPY, "505"))

    def test_a_reference_that_is_not_c_minus_1_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            sd.spy_move("2024-02-08", self.SPY, "505")


class Thirds(unittest.TestCase):
    def test_cut_points_and_assignment(self) -> None:
        cuts = sd.thirds([float(x) for x in range(1, 10)])
        self.assertAlmostEqual(cuts[0], 1 + 8 / 3)
        self.assertEqual([sd.third_of(x, cuts) for x in (1.0, 5.0, 9.0)], list(sd.THIRDS))


class Report(unittest.TestCase):
    def test_groups_and_cases_come_from_the_rows(self) -> None:
        rows = [{"session": s, "group": g, "case": "central", "result_usd": r,
                 "trigger": "session_stop", "close_changes_usd": [r, r, r],
                 "delay": {"trigger": "session_stop", "observations": 1, "cost_usd": 0.0},
                 "spy_move_pct": float(i), "fill_minus_estimate_usd": -1.0,
                 "debit_to_width": 0.4}
                for i, (s, g, r) in enumerate([("a", "Permitted", -10.0),
                                               ("b", "Breadth-vetoed", 20.0),
                                               ("c", "Permitted", -30.0)])]
        # Spread over a 20-session sequence, longer than one block.
        index = {"a": 0, "b": 7, "c": 15}
        rep = sd.report(rows, index, 20, repetitions=100)
        self.assertEqual(rep["central"]["Permitted"]["result"]["mean"], -20.0)
        self.assertEqual(rep["central"]["both"]["trades"], 3)
        self.assertEqual(rep["central"]["both"]["A4"]["fill_above_estimate"], 0)
        self.assertEqual(rep["optimistic"]["both"]["trades"], 0)
        self.assertIn("A2 waited", sd.render(rep))
        self.assertEqual(vx.CLOSED, "closed")


if __name__ == "__main__":
    unittest.main()
