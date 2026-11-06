"""Part B of the setup and exit study: the variant mechanics, on synthetic data."""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from options_alpha_lab import components, exits
from options_alpha_lab import study_variants as sv
from options_alpha_lab import veto_exits as vx
from options_alpha_lab import veto_replay as vr
from options_alpha_lab.architecture.contracts import Direction, PriceSource
from options_alpha_lab.study_decomposition import Mean


def trade(session: str, result: float | None, case: str = "central",
          group: str = vr.PERMITTED) -> vx.Trade:
    status = vx.CLOSED if result is not None else vx.NO_TRIGGER
    return vx.Trade(session, group, case, "2.00", "5.00", status, result_usd=result)


def state(**overrides: object) -> exits.ExitInputs:
    base: dict[str, object] = dict(
        direction=Direction.BULLISH, entry_debit=Decimal("2.00"), width=Decimal("5.00"),
        quantity=1, dte=20, underlying_price=Decimal("500"),
        underlying_source=PriceSource.COMPLETED_DAILY_CLOSE, invalidation=None,
        current_value=Decimal("2.00"), as_of=date(2026, 1, 5), sessions_elapsed=0)
    base.update(overrides)
    return exits.ExitInputs(**base)  # type: ignore[arg-type]


def variant(key: str) -> sv.Variant:
    return next(v for v in sv.VARIANTS if v.key == key)


class TheListIsClosed(unittest.TestCase):
    def test_six_alternatives_with_only_b4_not_run(self) -> None:
        self.assertEqual([v.key for v in sv.VARIANTS],
                         ["B1-2", "B1-5", "B2", "B3", "B4", "B5"])
        self.assertEqual({v.key for v in sv.VARIANTS if v.not_run}, {"B4"})

    def test_b1_5_reads_the_seven_session_window(self) -> None:
        # A five-session stop fires in the sixth session (plan 4.1).
        v = variant("B1-5")
        self.assertEqual((v.paths_folder, v.window), ("paths_s7", 7))

    def test_each_variant_changes_at_most_one_thing(self) -> None:
        for v in sv.VARIANTS:
            with self.subTest(v.key):
                self.assertLessEqual(len(v.patches), 1)


class PatchesChangeOneRuleAndAreRestored(unittest.TestCase):
    def test_restored_even_when_the_run_fails(self) -> None:
        with self.assertRaises(RuntimeError), sv.patched(variant("B1-2").patches):
            self.assertEqual(exits.SESSION_STOP, 2)
            raise RuntimeError
        self.assertEqual(exits.SESSION_STOP, 3)
        with sv.patched(variant("B5").patches):
            self.assertEqual(components.MIN_DTE, 21)
        self.assertEqual(components.MIN_DTE, 14)

    def test_session_stop_two_fires_a_session_earlier(self) -> None:
        two = state(sessions_elapsed=2)
        self.assertFalse(exits.evaluate_exit(two).should_close)
        with sv.patched(variant("B1-2").patches):
            self.assertEqual(exits.evaluate_exit(two).trigger, exits.ExitTrigger.SESSION_STOP)

    def test_thirty_percent_target(self) -> None:
        # Max gain 3.00: 60% target 3.80, 30% target 2.90.
        mid = state(current_value=Decimal("3.00"))
        self.assertFalse(exits.evaluate_exit(mid).should_close)
        with sv.patched(variant("B2").patches):
            self.assertEqual(exits.evaluate_exit(mid).trigger,
                             exits.ExitTrigger.PROFIT_CAPTURE)

    def test_no_stop_loss_leaves_the_other_rules(self) -> None:
        low = state(current_value=Decimal("0.10"))
        self.assertEqual(exits.evaluate_exit(low).trigger, exits.ExitTrigger.STOP_LOSS)
        with sv.patched(variant("B3").patches):
            self.assertFalse(exits.evaluate_exit(low).should_close)
            late = state(current_value=Decimal("0.10"), sessions_elapsed=3)
            self.assertEqual(exits.evaluate_exit(late).trigger,
                             exits.ExitTrigger.SESSION_STOP)
            near = state(current_value=Decimal("0.10"), dte=7)
            self.assertEqual(exits.evaluate_exit(near).trigger,
                             exits.ExitTrigger.EXPIRY_GUARD)


class Differences(unittest.TestCase):
    index = {"2026-01-05": 0, "2026-01-06": 1, "2026-01-07": 2, "2026-01-08": 3}

    def test_paired_by_session_with_one_sided_gaps_counted(self) -> None:
        current = [trade("2026-01-05", -10.0), trade("2026-01-06", 5.0),
                   trade("2026-01-07", None)]
        variant_ = [trade("2026-01-05", 0.0), trade("2026-01-06", 2.0),
                    trade("2026-01-07", 1.0), trade("2026-01-08", 4.0)]
        values, gaps = sv.differences(variant_, current, self.index, 4, "central")
        self.assertEqual(values, [10.0, -3.0, None, None])
        self.assertEqual(gaps, 2)

    def test_other_cases_and_vetoed_sessions_are_ignored(self) -> None:
        current = [trade("2026-01-05", -10.0), trade("2026-01-06", 1.0, case="optimistic"),
                   trade("2026-01-07", 1.0, group=vr.BREADTH_VETOED)]
        variant_ = [trade("2026-01-05", -4.0), trade("2026-01-06", 9.0, case="optimistic"),
                    trade("2026-01-07", 9.0, group=vr.BREADTH_VETOED)]
        values, gaps = sv.differences(variant_, current, self.index, 4, "central")
        self.assertEqual(values, [6.0, None, None, None])
        self.assertEqual(gaps, 0)


class ReadingRule(unittest.TestCase):
    def contrast(self, low: float, low_sensitivity: float | None = None
                 ) -> dict[str, dict[int, Mean]]:
        other = low if low_sensitivity is None else low_sensitivity
        return {c: {10: Mean(50, 0, 10.0, low, 20.0), 5: Mean(50, 0, 10.0, other, 20.0),
                    20: Mean(50, 0, 10.0, other, 20.0)} for c in vx.COST_CASES}

    def test_candidate_only_when_all_three_hold(self) -> None:
        better = dict.fromkeys(vx.COST_CASES, True)
        self.assertTrue(sv.verdict(self.contrast(1.0), better)["candidate"])
        self.assertFalse(sv.verdict(self.contrast(-1.0), better)["candidate"])
        held = sv.verdict(self.contrast(1.0, low_sensitivity=-0.5), better)
        self.assertTrue(held["interval_above_zero_block_10"])
        self.assertFalse(held["holds_at_5_and_20"])
        self.assertFalse(held["candidate"])
        worse = {**better, "optimistic": False}
        self.assertFalse(sv.verdict(self.contrast(1.0), worse)["candidate"])

    def test_a_missing_interval_never_counts_as_clearing(self) -> None:
        empty = {c: {b: Mean(0, 0, None, None, None) for b in sv.BLOCKS}
                 for c in vx.COST_CASES}
        self.assertFalse(sv.verdict(empty, dict.fromkeys(vx.COST_CASES, True))["candidate"])



class WindowEnds(unittest.TestCase):
    def test_an_unresolved_trade_is_held_to_its_own_window(self) -> None:
        from options_alpha_lab import veto_entries as ve
        days = [date(2026, 1, d) for d in (5, 6, 7, 8, 9, 12, 13, 14, 15)]
        entry = ve.Entry(session="2026-01-06", group=vr.PERMITTED, status=ve.ENTERED,
                         chain_calls=0, dropped=0)
        self.assertEqual(sv.window_ends([entry], days, 5)["2026-01-06"], date(2026, 1, 12))
        self.assertEqual(sv.window_ends([entry], days, 7)["2026-01-06"], date(2026, 1, 14))
        self.assertEqual(sv.window_ends([entry], days[:4], 7)["2026-01-06"], date(2026, 1, 8))


if __name__ == "__main__":
    unittest.main()
