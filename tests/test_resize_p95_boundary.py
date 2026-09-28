"""The latency criterion is "more than 20% worse", compared exactly.

On 28 September a float comparison flagged a dashboard p95 of 4.5 -> 5.4 ms,
exactly +20.0%, as a breach: (5.4 - 4.5) / 4.5 is 0.20000000000000007 in binary.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "resize_trial.py"
spec = importlib.util.spec_from_file_location("resize_trial_p95", SCRIPT)
assert spec is not None and spec.loader is not None
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)


class P95BoundaryTests(unittest.TestCase):
    def test_the_28_september_values_are_exactly_the_limit_not_over_it(self) -> None:
        self.assertGreater((5.4 - 4.5) / 4.5, 0.20)  # the float trap itself
        self.assertFalse(rt.p95_regressed(4.5, 5.4))

    def test_one_step_over_the_limit_trips(self) -> None:
        self.assertTrue(rt.p95_regressed(4.5, 5.5))

    def test_exact_limits_at_other_scales_do_not_trip(self) -> None:
        for base, trial in ((35.0, 42.0), (28.7, 34.44), (0.5, 0.6), (100.0, 120.0)):
            with self.subTest(base=base):
                self.assertFalse(rt.p95_regressed(base, trial))

    def test_improvement_and_small_regressions_pass(self) -> None:
        for base, trial in ((34.9, 37.0), (28.7, 29.3), (29.0, 20.0)):
            with self.subTest(base=base):
                self.assertFalse(rt.p95_regressed(base, trial))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
