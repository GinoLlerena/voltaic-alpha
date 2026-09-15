"""Tests for `CIIP-I-006` and `CIIP-I-007`: identity on every line, cadence damped.

The dangerous half is the suppression. Anything that drops log lines can drop
the one line that mattered, so the tests are written from that direction: a
changed action must always be emitted, a fault must never be suppressible, and
silence must never be ambiguous between "nothing changed" and "the process
died".

The naive alternative — emit every Nth line — fails the first of those, and
would look identical in a test that only counted output volume.
"""

from __future__ import annotations

import io
import json
import unittest

from options_alpha_lab.telemetry import (
    HEARTBEAT_EVERY,
    CadenceFilter,
    Context,
    emit,
)


def _emitted(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


class EmitTests(unittest.TestCase):
    def test_identity_is_attached_to_every_line(self) -> None:
        out = io.StringIO()
        ctx = Context(run_id="run-1", lease_owner="owner-1")
        emit("tick", context=ctx, correlation_id="spy-1", action="NO_TRADE", stream=out)
        (line,) = _emitted(out)
        self.assertEqual(line["run_id"], "run-1")
        self.assertEqual(line["lease_owner"], "owner-1")
        self.assertEqual(line["correlation_id"], "spy-1")

    def test_a_line_can_be_joined_to_its_records(self) -> None:
        """The whole point: a log line must name what it describes."""
        out = io.StringIO()
        emit("tick", context=Context(run_id="r"), correlation_id="snap-9", stream=out)
        (line,) = _emitted(out)
        self.assertIn("run_id", line)
        self.assertIn("correlation_id", line)

    def test_absent_identity_is_omitted_rather_than_null(self) -> None:
        out = io.StringIO()
        emit("worker_started", context=Context(), stream=out)
        (line,) = _emitted(out)
        self.assertNotIn("run_id", line)
        self.assertNotIn("lease_owner", line)

    def test_every_line_declares_its_kind(self) -> None:
        out = io.StringIO()
        emit("tick", stream=out)
        emit("tick_failed", kind="fault", error="boom", stream=out)
        kinds = [line["kind"] for line in _emitted(out)]
        self.assertEqual(kinds, ["state", "fault"])

    def test_event_and_kind_lead_the_line(self) -> None:
        out = io.StringIO()
        emit("tick", context=Context(run_id="r"), action="X", stream=out)
        keys = list(_emitted(out)[0])
        self.assertEqual(keys[:2], ["event", "kind"])

    def test_output_is_valid_json_per_line(self) -> None:
        out = io.StringIO()
        for n in range(3):
            emit("tick", detail=f'quotes "and" braces {{{n}}}', stream=out)
        self.assertEqual(len(_emitted(out)), 3)


class CadenceFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.filter = CadenceFilter(heartbeat_every=5)

    def test_the_first_line_is_always_emitted(self) -> None:
        self.assertTrue(self.filter.should_emit("position_clock", "POSITION_HELD"))

    def test_an_unchanged_action_is_suppressed(self) -> None:
        self.filter.should_emit("position_clock", "POSITION_HELD")
        self.assertFalse(self.filter.should_emit("position_clock", "POSITION_HELD"))

    def test_a_changed_action_is_always_emitted(self) -> None:
        """The line a rate-based sampler would throw away."""
        self.filter.should_emit("position_clock", "POSITION_HELD")
        for _ in range(3):
            self.filter.should_emit("position_clock", "POSITION_HELD")
        self.assertTrue(
            self.filter.should_emit("position_clock", "STOP_LOSS"),
            "a change in what the clock reports must never be suppressed",
        )

    def test_silence_is_broken_by_a_heartbeat(self) -> None:
        """Otherwise a quiet system is indistinguishable from a dead one."""
        emitted = sum(
            1
            for _ in range(11)
            if self.filter.should_emit("position_clock", "POSITION_HELD")
        )
        self.assertEqual(emitted, 3, "expected first line plus two heartbeats")

    def test_clocks_suppress_independently(self) -> None:
        """One clock going quiet must not hide another."""
        self.filter.should_emit("position_clock", "HELD")
        self.assertTrue(
            self.filter.should_emit("order_clock", "HELD"),
            "the order clock inherited the position clock's state",
        )

    def test_the_suppressed_count_is_reported(self) -> None:
        self.filter.should_emit("position_clock", "HELD")
        self.filter.should_emit("position_clock", "HELD")
        self.filter.should_emit("position_clock", "HELD")
        self.assertEqual(self.filter.suppressed("position_clock"), 2)

    def test_the_count_resets_when_a_line_is_emitted(self) -> None:
        self.filter.should_emit("position_clock", "HELD")
        self.filter.should_emit("position_clock", "HELD")
        self.filter.should_emit("position_clock", "CLOSING")
        self.assertEqual(self.filter.suppressed("position_clock"), 0)

    def test_alternating_actions_are_never_suppressed(self) -> None:
        emitted = sum(
            1
            for n in range(10)
            if self.filter.should_emit("position_clock", f"ACTION_{n % 2}")
        )
        self.assertEqual(emitted, 10)

    def test_the_default_heartbeat_is_bounded(self) -> None:
        """A very large default would make silence meaningless in practice."""
        self.assertLessEqual(HEARTBEAT_EVERY, 60)
        self.assertGreater(HEARTBEAT_EVERY, 1)


class NoSuppressionOfWhatMattersTests(unittest.TestCase):
    """State and fault lines have no path through the filter at all."""

    def test_emit_has_no_suppression_parameter(self) -> None:
        import inspect

        self.assertNotIn("filter", inspect.signature(emit).parameters)
        self.assertNotIn("sample", inspect.signature(emit).parameters)

    def test_repeated_faults_all_emit(self) -> None:
        out = io.StringIO()
        for _ in range(5):
            emit("tick_failed", kind="fault", error="same error", stream=out)
        self.assertEqual(len(_emitted(out)), 5)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
