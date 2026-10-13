"""The feasibility count is only useful if it really is an upper bound.

`veto_study` applies two of the entry rule's three conditions and says the
result bounds what the whole rule can produce. If that were false, a count that
looked too small could hide a study worth doing, or the reverse. So the bound is
held against the shipped classifier on every session in the fixture, with
volatility supplied at each of its three regimes.
"""

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from options_alpha_lab import veto_study
from options_alpha_lab.architecture.contracts import (
    AccountSnapshot,
    DecisionSnapshot,
    Direction,
    Signal,
    SignalFamily,
)
from options_alpha_lab.components import DeterministicSetupClassifier
from options_alpha_lab.evidence import MIN_BARS_REQUIRED, build_signals

#: Calm (a confirmation), neither, and stressed (a veto).
VOLATILITIES = (Decimal("0.10"), Decimal("0.27"), Decimal("0.40"))


def _snapshot(signals: list[Signal], as_of: datetime, price: Decimal) -> DecisionSnapshot:
    return DecisionSnapshot(
        snapshot_id="veto-study-test",
        as_of=as_of,
        symbol="SPY",
        underlying_price=price,
        account=AccountSnapshot(
            account_id="test", as_of=as_of, equity=Decimal("100000"),
            options_buying_power=Decimal("100000"), is_paper=True,
        ),
        signals=tuple(signals),
    )


class UpperBoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spy, cls.rsp = veto_study.load_bars()
        cls.rows = list(veto_study.rows(cls.spy, cls.rsp))

    def test_there_is_enough_history_to_be_worth_counting(self) -> None:
        self.assertGreater(len(self.rows), 400)

    def test_volatility_never_adds_a_bullish_setup_the_count_missed(self) -> None:
        classifier = DeterministicSetupClassifier()
        for row in self.rows:
            first = row.completed - timedelta(days=veto_study.LOOKBACK_DAYS)
            window = [b for b in self.spy[: row.index + 1] if b.session > first]
            breadth = [b for b in self.rsp if first < b.session <= row.completed]
            as_of = datetime.combine(row.completed, datetime.min.time(), tzinfo=UTC)
            for volatility in VOLATILITIES:
                with self.subTest(session=str(row.completed), volatility=str(volatility)):
                    signals = build_signals(window, volatility, as_of, breadth)
                    setup = classifier.classify(_snapshot(signals, as_of, window[-1].close))
                    if setup is not None and setup.direction is Direction.BULLISH:
                        self.assertEqual(row.group, veto_study.BELOW_LINE)
                    if row.group == veto_study.AT_OR_ABOVE_LINE:
                        self.assertIsNone(setup)

    def test_no_row_sees_a_later_bar(self) -> None:
        cut = len(self.spy) - 40
        before = list(veto_study.rows(self.spy[:cut], self.rsp[:cut]))
        again = [row for row in self.rows if row.index < cut]
        self.assertEqual([r.signals for r in before], [r.signals for r in again])

    def test_the_window_is_the_workers_400_days_not_the_whole_series(self) -> None:
        # An EMA over the whole series differs from one over the bounded window,
        # so a row built from a longer history must still equal the bounded one.
        last = self.rows[-1]
        first = last.completed - timedelta(days=veto_study.LOOKBACK_DAYS)
        bounded_spy = [b for b in self.spy if b.session > first]
        bounded_rsp = [b for b in self.rsp if b.session > first]
        self.assertLess(len(bounded_spy), len(self.spy))
        self.assertEqual(list(veto_study.rows(bounded_spy, bounded_rsp))[-1].signals, last.signals)

    def test_too_little_history_yields_no_row(self) -> None:
        short = self.spy[: MIN_BARS_REQUIRED - 1]
        self.assertEqual(list(veto_study.rows(short, self.rsp)), [])


class GroupTests(unittest.TestCase):
    def _row(self, *signals: Signal) -> veto_study.Row:
        return veto_study.Row(datetime(2026, 1, 2, tzinfo=UTC).date(), 0, signals)

    def _signal(self, family: SignalFamily, direction: Direction, strength: str) -> Signal:
        return Signal(
            signal_id=f"sig-{family.value}", family=family, direction=direction,
            strength=Decimal(strength), as_of=datetime(2026, 1, 2, tzinfo=UTC),
            source="test", summary="test",
        )

    def test_structure_below_the_qualifying_strength_is_in_neither_group(self) -> None:
        row = self._row(self._signal(SignalFamily.STRUCTURE, Direction.BULLISH, "0.59"))
        self.assertIsNone(row.group)

    def test_bearish_structure_is_out_of_scope(self) -> None:
        row = self._row(self._signal(SignalFamily.STRUCTURE, Direction.BEARISH, "0.80"))
        self.assertIsNone(row.group)
        self.assertTrue(row.bearish_structure)

    def test_the_line_itself_counts_as_at_or_above(self) -> None:
        structure = self._signal(SignalFamily.STRUCTURE, Direction.BULLISH, "0.60")
        at = self._signal(SignalFamily.PARTICIPATION, Direction.BEARISH, "0.70")
        under = replace(at, strength=Decimal("0.69"))
        self.assertEqual(self._row(structure, at).group, veto_study.AT_OR_ABOVE_LINE)
        self.assertEqual(self._row(structure, under).group, veto_study.BELOW_LINE)

    def test_aligned_breadth_and_no_breadth_are_both_below_the_line(self) -> None:
        structure = self._signal(SignalFamily.STRUCTURE, Direction.BULLISH, "0.60")
        aligned = self._signal(SignalFamily.PARTICIPATION, Direction.BULLISH, "0.95")
        self.assertEqual(self._row(structure).group, veto_study.BELOW_LINE)
        self.assertEqual(self._row(structure, aligned).group, veto_study.BELOW_LINE)

    def test_a_veto_from_another_family_is_reported_not_merged_into_breadth(self) -> None:
        structure = self._signal(SignalFamily.STRUCTURE, Direction.BULLISH, "0.60")
        momentum = self._signal(SignalFamily.MOMENTUM, Direction.BEARISH, "0.75")
        row = self._row(structure, momentum)
        self.assertEqual(row.group, veto_study.BELOW_LINE)
        self.assertTrue(row.other_veto)


class ClusterTests(unittest.TestCase):
    def test_consecutive_sessions_are_one_cluster(self) -> None:
        self.assertEqual(veto_study.clusters([4, 5, 6]), [[4, 5, 6]])

    def test_a_gap_shorter_than_the_separation_does_not_split(self) -> None:
        self.assertEqual(veto_study.clusters([1, 3]), [[1, 3]])

    def test_a_gap_of_the_separation_splits(self) -> None:
        gap = veto_study.CLUSTER_GAP_SESSIONS
        self.assertEqual(veto_study.clusters([1, 1 + gap]), [[1], [1 + gap]])

    def test_longest_run_counts_only_adjacent_sessions(self) -> None:
        self.assertEqual(veto_study.longest_run([1, 2, 4, 5, 6, 9]), 3)
        self.assertEqual(veto_study.longest_run([]), 0)


class ReferenceTests(unittest.TestCase):
    """The replay is held to what the worker stored, exactly."""

    @classmethod
    def setUpClass(cls) -> None:
        spy, rsp = veto_study.load_bars()
        cls.rows = list(veto_study.rows(spy, rsp))
        cls.spy = spy

    def _stored(self, row: veto_study.Row, day: str) -> dict[str, object]:
        return {
            "snapshots": {day: 1},
            "signals": [
                {"day": day, "signal_id": s.signal_id, "direction": s.direction.value,
                 "strength": f"{s.strength:.4f}"}
                for s in row.signals
            ],
        }

    def _a_row_with_signals(self) -> veto_study.Row:
        return next(r for r in self.rows[:-1] if r.signals)

    def test_a_stored_session_matches_the_row_completed_before_it(self) -> None:
        row = self._a_row_with_signals()
        next_session = str(self.spy[row.index + 1].session)
        self.assertEqual(veto_study.disagreements(self.rows, self._stored(row, next_session)), [])

    def test_a_different_strength_is_a_disagreement(self) -> None:
        row = self._a_row_with_signals()
        stored = self._stored(row, str(self.spy[row.index + 1].session))
        stored["signals"][0]["strength"] = "0.0100"  # type: ignore[index]
        self.assertEqual(len(veto_study.disagreements(self.rows, stored)), 1)

    def test_a_signal_the_worker_did_not_store_is_a_disagreement(self) -> None:
        row = self._a_row_with_signals()
        stored = self._stored(row, str(self.spy[row.index + 1].session))
        stored["signals"] = []
        self.assertEqual(len(veto_study.disagreements(self.rows, stored)), 1)

    def test_the_volatility_signal_is_not_expected_of_the_replay(self) -> None:
        row = self._a_row_with_signals()
        day = str(self.spy[row.index + 1].session)
        stored = self._stored(row, day)
        stored["signals"].append(  # type: ignore[attr-defined]
            {"day": day, "signal_id": veto_study.NOT_REPLAYED, "direction": "bullish",
             "strength": "0.7500"}
        )
        self.assertEqual(veto_study.disagreements(self.rows, stored), [])

    def test_a_session_the_bars_do_not_reach_is_a_disagreement_not_a_skip(self) -> None:
        stored = {"snapshots": {"2001-01-02": 1}, "signals": []}
        self.assertEqual(len(veto_study.disagreements(self.rows, stored)), 1)


class ScreenTests(unittest.TestCase):
    def test_the_report_fails_the_screen_when_a_group_is_too_small(self) -> None:
        spy, rsp = veto_study.load_bars()
        recent = spy[-1].session - timedelta(days=30)
        report = veto_study.run(spy, rsp, since=recent)
        self.assertFalse(report["screen"]["passes"])

    def test_groups_partition_the_bullish_structure_sessions(self) -> None:
        spy, rsp = veto_study.load_bars()
        report = veto_study.run(spy, rsp)
        counted = sum(group["sessions"] for group in report["groups"].values())
        self.assertEqual(counted, report["bullish_structure"])


if __name__ == "__main__":
    unittest.main()
