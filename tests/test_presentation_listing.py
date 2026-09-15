"""The decision list, and the two defects extracting it exposed (`RUI-VAL-009`).

Written against constructed decisions, so every case is explicit rather than
whatever the committed evidence happens to contain -- the committed evidence is
exactly where the grouping defect went unnoticed.
"""

import unittest
from dataclasses import dataclass, field

from options_alpha_lab.presentation.listing import VIEWS, build


@dataclass(eq=False)
class D:
    snapshot_id: str
    action: str = "NO_TRADE"
    direction: str = "neutral"
    reason_codes: list[str] = field(default_factory=lambda: ["no_qualified_setup"])
    decision_hash: str = ""
    id: str = ""

    def __post_init__(self) -> None:
        self.decision_hash = self.decision_hash or f"sha256:{self.snapshot_id}"
        self.id = self.id or self.snapshot_id


def position(name: str, direction: str = "bullish") -> D:
    return D(name, action="OPTIONS_POSITION", direction=direction, reason_codes=[])


def names(listing) -> list[str]:  # type: ignore[no-untyped-def]
    return [e.decision.snapshot_id for e in listing.entries]


class PositionsAreNeverGroupedTests(unittest.TestCase):
    def test_consecutive_positions_each_get_an_entry(self) -> None:
        """The committed-evidence shape: two qualified cases back to back."""
        decisions = [position("a"), position("b", "bearish"), D("r"), position("c"), position("d")]
        listing = build(decisions, "Notable")
        self.assertEqual(sorted(names(listing)), ["a", "b", "c", "d", "r"])
        self.assertFalse(listing.grouped)

    def test_opposite_directions_are_never_one_entry(self) -> None:
        listing = build([position("up"), position("down", "bearish")], "Notable")
        self.assertEqual({e.decision.direction for e in listing.entries}, {"bullish", "bearish"})


class RefusalsAreGroupedTests(unittest.TestCase):
    def test_identical_consecutive_refusals_become_one_counted_entry(self) -> None:
        decisions = [D(f"r{i}") for i in range(5)]
        (entry,) = build(decisions, "Notable").entries
        self.assertEqual(entry.count, 5)
        self.assertEqual(entry.decision.snapshot_id, "r4", "the representative is the newest")

    def test_different_reasons_are_different_stories(self) -> None:
        decisions = [D("a"), D("b", reason_codes=["max_loss_exceeds_risk_budget"])]
        self.assertEqual(len(build(decisions, "Notable").entries), 2)

    def test_a_position_breaks_a_run(self) -> None:
        decisions = [D("r1"), D("r2"), position("p"), D("r3")]
        self.assertEqual([e.count for e in build(decisions, "Notable").entries], [1, 1, 2])

    def test_only_notable_groups(self) -> None:
        decisions = [D(f"r{i}") for i in range(3)]
        for view in ("Refusals", "Everything"):
            self.assertEqual(len(build(decisions, view).entries), 3, view)


class OrderTests(unittest.TestCase):
    def test_every_view_is_newest_first(self) -> None:
        decisions = [position("p1"), D("r1"), position("p2"), D("r2")]
        for view in VIEWS:
            listed = names(build(decisions, view))
            expected = [d.snapshot_id for d in reversed(decisions) if d.snapshot_id in listed]
            self.assertEqual(listed, expected, view)


class PinTests(unittest.TestCase):
    """A tour scene's decision must be selectable in whatever view is showing."""

    def test_a_pinned_member_replaces_its_runs_representative(self) -> None:
        decisions = [D(f"r{i}") for i in range(4)]
        (entry,) = build(decisions, "Notable", pin=decisions[1]).entries
        self.assertIs(entry.decision, decisions[1])
        self.assertEqual(entry.count, 4, "pinning must not hide how many it stands for")

    def test_a_pin_the_filter_excludes_is_still_listed(self) -> None:
        decisions = [position("p"), D("r")]
        listing = build(decisions, "Refusals", pin=decisions[0])
        self.assertIn("p", names(listing))
        self.assertFalse(listing.pin_missing)

    def test_a_pin_absent_from_the_source_is_reported(self) -> None:
        listing = build([D("r")], "Notable", pin=position("elsewhere"))
        self.assertTrue(listing.pin_missing)
        self.assertEqual(names(listing), ["r"], "nothing is substituted for the missing pin")

    def test_no_pin_is_not_missing(self) -> None:
        self.assertFalse(build([D("r")], "Notable").pin_missing)


class LabelTests(unittest.TestCase):
    def test_labels_keep_the_pages_format(self) -> None:
        refusal = build([D("spy-refusal-2026-08-27"), D("spy-refusal-2026-08-28")], "Notable")
        self.assertEqual(refusal.entries[0].label, "SPY refusal 2026 08 28\nno_qualified_setup  ×2")
        pos = build([position("spy-live-x")], "Notable")
        self.assertEqual(pos.entries[0].label, "SPY live x\nposition · bullish")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
