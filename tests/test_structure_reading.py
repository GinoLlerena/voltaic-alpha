"""`CIIP-VAL-012`: the structure gate reports where it stopped.

`build_signals` returns `[]` the moment a gate declines, so a refusal reached the
records carrying nothing — 201 live decisions with zero signal rows and no way to
tell a near miss from an absent trend.

`structure_reading` recomputes the same gates and keeps the arithmetic. The
duplication is the risk, so the first test is the one that holds both functions
to the same answer: the reading says `passed` exactly when `build_signals`
produces a structure signal, over series built to land on either side of every
threshold.
"""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from options_alpha_lab.architecture.contracts import SignalFamily
from options_alpha_lab.evidence import (
    MIN_BARS_REQUIRED,
    MIN_EMA_SEPARATION,
    RETEST_LOOKBACK_SESSIONS,
    RETEST_TOLERANCE,
    Bar,
    build_signals,
    structure_reading,
)

NOW = datetime(2026, 9, 17, 20, 0, tzinfo=UTC)


def series(closes: list[str], *, lows: list[str] | None = None,
           highs: list[str] | None = None) -> list[Bar]:
    start = date(2026, 1, 5)
    bars = []
    for i, close in enumerate(closes):
        value = Decimal(close)
        low = Decimal(lows[i]) if lows else value
        high = Decimal(highs[i]) if highs else value
        bars.append(Bar(session=start + timedelta(days=i), open=value, high=high,
                        low=low, close=value, volume=Decimal("1000000")))
    return bars


def rising(n: int = MIN_BARS_REQUIRED + 5, step: str = "1.5") -> list[str]:
    """A clean uptrend: EMA20 pulls well clear of EMA50."""
    return [str(Decimal("500") + Decimal(step) * i) for i in range(n)]


def flat(n: int = MIN_BARS_REQUIRED + 5) -> list[str]:
    """No trend at all: the EMAs converge, separation stays under the threshold."""
    return ["500"] * n


class ReadingAgreesWithTheGateTests(unittest.TestCase):
    """The duplication's guard. If these drift, the diagnostic lies."""

    def assert_agrees(self, bars: list[Bar], label: str) -> None:
        signals = build_signals(bars, None, NOW)
        produced = any(s.family is SignalFamily.STRUCTURE for s in signals)
        reading = structure_reading(bars, NOW)
        self.assertEqual(
            reading.gate == "passed", produced,
            f"{label}: reading said {reading.gate!r} but build_signals "
            f"{'produced' if produced else 'produced no'} structure signal",
        )

    def test_a_clean_uptrend_with_a_retest(self) -> None:
        closes = rising()
        lows = list(closes)
        # Drag the recent lows back onto the fast EMA so the retest is touched.
        for i in range(1, RETEST_LOOKBACK_SESSIONS + 1):
            lows[-i] = str(Decimal(closes[-i]) * Decimal("0.90"))
        self.assert_agrees(series(closes, lows=lows), "uptrend with retest")

    def test_a_trend_that_never_retested(self) -> None:
        self.assert_agrees(series(rising()), "uptrend, no retest")

    def test_no_trend_at_all(self) -> None:
        self.assert_agrees(series(flat()), "flat")

    def test_too_few_bars(self) -> None:
        self.assert_agrees(series(rising(MIN_BARS_REQUIRED - 1)), "short history")

    def test_a_downtrend(self) -> None:
        closes = [str(Decimal("800") - Decimal("1.5") * i) for i in range(MIN_BARS_REQUIRED + 5)]
        highs = list(closes)
        for i in range(1, RETEST_LOOKBACK_SESSIONS + 1):
            highs[-i] = str(Decimal(closes[-i]) * Decimal("1.10"))
        self.assert_agrees(series(closes, highs=highs), "downtrend with retest")


def ramp(step: Decimal, n: int = MIN_BARS_REQUIRED + 5) -> list[Bar]:
    return series([str(Decimal("500") + step * i) for i in range(n)])


def ramp_for_separation(target: Decimal) -> list[Bar]:
    """A series whose EMA separation lands within 1% of `target`.

    Found by bisection rather than guessed: separation rises monotonically with
    the drift per bar, and the boundary is the only place the two implementations
    can disagree without one of them being obviously wrong.
    """
    low, high = Decimal("0.0001"), Decimal("50")
    for _ in range(200):
        mid = (low + high) / 2
        reading = structure_reading(ramp(mid), NOW)
        separation = reading.separation or Decimal(0)
        if abs(separation - target) <= target / 100:
            return ramp(mid)
        if separation < target:
            low = mid
        else:
            high = mid
    raise AssertionError(f"no ramp found for separation {target}")


class TheBoundaryIsWhereTheyCanDisagreeTests(unittest.TestCase):
    """Agreement on obvious cases proves little.

    A first version of this file tested a trend twenty times the threshold and a
    flat series at zero; tripling the threshold in one implementation left both
    tests passing. These sit either side of the line, which is the only place a
    drifted constant shows.
    """

    def touched(self, bars: list[Bar]) -> list[Bar]:
        """Drag the recent lows onto the fast EMA so the retest gate passes."""
        reading = structure_reading(bars, NOW)
        fast = reading.fast_ema or Decimal(0)
        out = list(bars)
        for i in range(1, RETEST_LOOKBACK_SESSIONS + 1):
            bar = out[-i]
            out[-i] = Bar(session=bar.session, open=bar.open, high=bar.high,
                          low=fast * (Decimal(1) + RETEST_TOLERANCE / 2),
                          close=bar.close, volume=bar.volume)
        return out

    def test_just_above_the_threshold_qualifies_in_both(self) -> None:
        bars = self.touched(ramp_for_separation(MIN_EMA_SEPARATION * Decimal("1.05")))
        reading = structure_reading(bars, NOW)
        produced = any(s.family is SignalFamily.STRUCTURE for s in build_signals(bars, None, NOW))
        self.assertGreater(reading.separation or Decimal(0), MIN_EMA_SEPARATION)
        self.assertTrue(produced, "build_signals must accept a series just over the line")
        self.assertEqual(reading.gate, "passed")

    def test_just_below_the_threshold_declines_in_both(self) -> None:
        bars = self.touched(ramp_for_separation(MIN_EMA_SEPARATION * Decimal("0.95")))
        reading = structure_reading(bars, NOW)
        produced = any(s.family is SignalFamily.STRUCTURE for s in build_signals(bars, None, NOW))
        self.assertLess(reading.separation or Decimal(0), MIN_EMA_SEPARATION)
        self.assertFalse(produced)
        self.assertEqual(reading.gate, "separation_or_side")

    def test_the_shortfall_is_signed_across_the_line(self) -> None:
        over = structure_reading(ramp_for_separation(MIN_EMA_SEPARATION * Decimal("1.05")), NOW)
        under = structure_reading(ramp_for_separation(MIN_EMA_SEPARATION * Decimal("0.95")), NOW)
        self.assertGreater(over.separation_shortfall or Decimal(-1), 0)
        self.assertLess(under.separation_shortfall or Decimal(1), 0)


class EveryGateIsReachableTests(unittest.TestCase):
    """A diagnostic that can only ever report one outcome diagnoses nothing."""

    def test_insufficient_bars(self) -> None:
        reading = structure_reading(series(rising(10)), NOW)
        self.assertEqual(reading.gate, "insufficient_bars")
        self.assertEqual(reading.bars_considered, 10)
        self.assertEqual(reading.bars_required, MIN_BARS_REQUIRED)
        self.assertIsNone(reading.separation, "nothing was computed, so nothing is reported")

    def test_no_trend_reports_the_separation_it_measured(self) -> None:
        reading = structure_reading(series(flat()), NOW)
        self.assertEqual(reading.gate, "separation_or_side")
        self.assertIsNotNone(reading.separation)
        self.assertIsNotNone(reading.fast_ema)
        self.assertLess(reading.separation_shortfall or Decimal(1), 0,
                        "a shortfall is negative, so the sign says which way it missed")

    def test_a_trend_without_a_retest_says_so(self) -> None:
        reading = structure_reading(series(rising()), NOW)
        self.assertEqual(reading.gate, "no_retest")
        self.assertFalse(reading.retest_touched)
        self.assertGreaterEqual(reading.separation_shortfall or Decimal(-1), 0,
                                "the trend cleared the threshold; only the retest failed")

    def test_a_qualifying_series_passes(self) -> None:
        closes = rising()
        lows = list(closes)
        for i in range(1, RETEST_LOOKBACK_SESSIONS + 1):
            lows[-i] = str(Decimal(closes[-i]) * Decimal("0.90"))
        reading = structure_reading(series(closes, lows=lows), NOW)
        self.assertEqual(reading.gate, "passed")
        self.assertTrue(reading.retest_touched)


class ItDiagnosesWithoutDecidingTests(unittest.TestCase):
    def test_reading_the_gate_twice_gives_the_same_answer(self) -> None:
        bars = series(rising())
        self.assertEqual(structure_reading(bars, NOW), structure_reading(bars, NOW))

    def test_it_does_not_disturb_the_signals(self) -> None:
        """A diagnostic that changed an outcome would be a second classifier."""
        bars = series(rising())
        before = build_signals(bars, None, NOW)
        structure_reading(bars, NOW)
        self.assertEqual(build_signals(bars, None, NOW), before)

    def test_the_tolerance_and_threshold_come_from_the_gate(self) -> None:
        """Constants restated in the diagnostic would drift from the policy."""
        import inspect

        source = inspect.getsource(structure_reading)
        self.assertIn("MIN_EMA_SEPARATION", source)
        self.assertIn("RETEST_TOLERANCE", source)
        self.assertIn("RETEST_LOOKBACK_SESSIONS", source)
        self.assertNotIn("0.002", source)
        self.assertNotIn("0.010", source)


class ItIsRecordedWithTheDecisionTests(unittest.TestCase):
    """`CIIP-VAL-012`: a decision cannot exist without the measurement that
    explains it -- and a caller with no bars records nothing rather than a zero."""

    def _recorder(self):  # type: ignore[no-untyped-def]
        import tempfile
        from pathlib import Path

        from options_alpha_lab.config import load_settings
        from options_alpha_lab.persistence.repository import (
            DecisionRecorder,
            build_engine,
            create_schema,
        )

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        settings = load_settings({
            "BOT_MODE": "observe",
            "ALPACA_PAPER_TRADE": "true",
            "ALPACA_TRADING_ENABLED": "false",
            "DATABASE_URL": f"sqlite+pysqlite:///{Path(tmp.name) / 'r.db'}",
        })
        engine = build_engine(settings)
        create_schema(engine)
        return DecisionRecorder(engine, settings), engine, settings

    def _decide(self, recorder, settings, **extra):  # type: ignore[no-untyped-def]
        from options_alpha_lab.components import DeterministicRiskGovernor
        from options_alpha_lab.replay import build_workflow
        from options_alpha_lab.snapshot_io import load_snapshot

        snapshot = load_snapshot("fixtures/h0/spy_refusal.snapshot.json")
        governor = DeterministicRiskGovernor(settings.policy_version)
        outcome = build_workflow(governor, None).evaluate(snapshot)
        return recorder.record_decision(
            run_id=recorder.start_run(), snapshot=snapshot, outcome=outcome, **extra
        )

    def _rows(self, engine):  # type: ignore[no-untyped-def]
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from options_alpha_lab.persistence.models import StructureReadingRecord

        with Session(engine) as session:
            return list(session.scalars(select(StructureReadingRecord)).all())

    def test_a_reading_is_written_with_the_decision(self) -> None:
        recorder, engine, settings = self._recorder()
        reading = structure_reading(series(flat()), NOW)
        recorded = self._decide(recorder, settings, structure=reading)
        (row,) = self._rows(engine)
        self.assertEqual(row.decision_id, recorded.decision_id)
        self.assertEqual(row.gate, "separation_or_side")
        self.assertEqual(Decimal(str(row.separation)), reading.separation)
        self.assertLess(Decimal(str(row.separation_shortfall)), 0)

    def test_a_caller_without_bars_records_no_reading(self) -> None:
        """A replayed fixture carries signals, not the series behind them. A zero
        row would claim a measurement nobody made."""
        recorder, engine, settings = self._recorder()
        self._decide(recorder, settings)
        self.assertEqual(self._rows(engine), [])

    def test_the_decision_hash_does_not_depend_on_the_reading(self) -> None:
        """The reading is recorded beside the decision, never inside it: a
        diagnostic that changed a hash would rewrite history to describe itself."""
        first, _, settings_a = self._recorder()
        second, _, settings_b = self._recorder()
        with_reading = self._decide(
            first, settings_a, structure=structure_reading(series(flat()), NOW)
        )
        without = self._decide(second, settings_b)
        self.assertEqual(with_reading.decision_hash, without.decision_hash)
        self.assertEqual(with_reading.input_hash, without.input_hash)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
