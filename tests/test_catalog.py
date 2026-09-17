"""`CIIP-009`: the strategy catalog's lifecycle, and the authority it does not grant.

Two properties carry this file. A state change must be a decision rather than an
assignment, so illegal moves are refused and accepted ones return the decision
that justified them. And reaching a trading state must grant nothing: the
execution path has never heard of the catalog, which is asserted against the real
import graph rather than described in a comment.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import unittest
from pathlib import Path

from options_alpha_lab.catalog import (
    TRADING_STATES,
    TRANSITIONS,
    CandidateState,
    TransitionError,
    allowed,
    promote,
)

ROOT = Path(__file__).resolve().parents[1]


def code(path: Path) -> str:
    """Source with docstrings and comments removed, so prose about a thing is
    not read as the thing."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            if isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def move(current: CandidateState, target: CandidateState, **over: str):  # type: ignore[no-untyped-def]
    kwargs = {
        "candidate_id": "c1",
        "current": current,
        "target": target,
        "rationale": "walk-forward folds held up out of sample",
        "decided_by": "owner",
        "policy_version": "h0-provisional-1",
    }
    kwargs.update(over)
    return promote(**kwargs)  # type: ignore[arg-type]


class TheLifecycleIsEnforcedTests(unittest.TestCase):
    def test_the_documented_path_walks_end_to_end(self) -> None:
        path = [
            CandidateState.PROPOSED, CandidateState.TESTING, CandidateState.CHALLENGED,
            CandidateState.ELIGIBLE, CandidateState.PAPER_SHADOW,
            CandidateState.PAPER_ACTIVE, CandidateState.PAUSED, CandidateState.RETIRED,
        ]
        for current, target in zip(path, path[1:], strict=False):
            with self.subTest(step=f"{current.value}->{target.value}"):
                self.assertEqual(move(current, target).to_state, target)

    def test_a_candidate_cannot_skip_to_trading(self) -> None:
        """The whole point of the ladder: proposed is not eligible."""
        for target in (CandidateState.PAPER_ACTIVE, CandidateState.PAPER_SHADOW,
                       CandidateState.ELIGIBLE):
            with self.subTest(target=target.value), self.assertRaises(TransitionError):
                move(CandidateState.PROPOSED, target)

    def test_rejection_is_reachable_until_paper_trading_begins(self) -> None:
        """A candidate that cannot be rejected late is one nobody can argue
        against once it has momentum."""
        for state in (CandidateState.PROPOSED, CandidateState.TESTING,
                      CandidateState.CHALLENGED, CandidateState.ELIGIBLE,
                      CandidateState.PAPER_SHADOW):
            with self.subTest(state=state.value):
                self.assertIn(CandidateState.REJECTED, allowed(state))

    def test_terminal_states_are_terminal(self) -> None:
        for state in (CandidateState.RETIRED, CandidateState.REJECTED):
            with self.subTest(state=state.value):
                self.assertEqual(allowed(state), frozenset())
                with self.assertRaises(TransitionError):
                    move(state, CandidateState.TESTING)

    def test_a_paper_active_candidate_cannot_quietly_reverse_to_testing(self) -> None:
        with self.assertRaises(TransitionError):
            move(CandidateState.PAPER_ACTIVE, CandidateState.TESTING)

    def test_every_state_has_a_rule(self) -> None:
        self.assertEqual(set(TRANSITIONS), set(CandidateState))

    def test_staying_put_is_not_a_transition(self) -> None:
        with self.assertRaises(TransitionError):
            move(CandidateState.TESTING, CandidateState.TESTING)


class APromotionRecordsWhoAndWhyTests(unittest.TestCase):
    def test_a_promotion_without_a_reason_is_refused(self) -> None:
        with self.assertRaises(TransitionError):
            move(CandidateState.PROPOSED, CandidateState.TESTING, rationale="   ")

    def test_a_promotion_without_a_decider_is_refused(self) -> None:
        with self.assertRaises(TransitionError):
            move(CandidateState.PROPOSED, CandidateState.TESTING, decided_by="")

    def test_an_accepted_move_carries_its_justification(self) -> None:
        transition = move(CandidateState.ELIGIBLE, CandidateState.PAPER_SHADOW)
        self.assertEqual(transition.from_state, CandidateState.ELIGIBLE)
        self.assertEqual(transition.decided_by, "owner")
        self.assertTrue(transition.rationale)
        self.assertEqual(transition.policy_version, "h0-provisional-1")


class StateGrantsNoAuthorityTests(unittest.TestCase):
    """`CIIP-3`'s acceptance: a candidate cannot reach the gateway by changing
    its state alone."""

    def test_the_execution_path_does_not_import_the_catalog(self) -> None:
        probe = (
            "import sys, json\n"
            "import options_alpha_lab.execution.gateway  # noqa: F401\n"
            "print(json.dumps(sorted(sys.modules)))\n"
        )
        result = subprocess.run(  # noqa: S603 - fixed argv, no user input
            [sys.executable, "-c", probe], capture_output=True, text=True, cwd=ROOT, check=True
        )
        loaded = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertNotIn("options_alpha_lab.catalog", loaded)

    def test_no_execution_module_mentions_a_candidate_state(self) -> None:
        execution = sorted((ROOT / "src" / "options_alpha_lab" / "execution").glob("*.py"))
        self.assertTrue(execution)
        for path in execution:
            source = path.read_text(encoding="utf-8")
            for token in ("PAPER_ACTIVE", "PAPER_SHADOW", "StrategyCandidate", "catalog"):
                self.assertNotIn(token, source, f"{path.name} consults the catalog")

    def test_the_catalog_cannot_build_an_order(self) -> None:
        """It holds no path to an intent, a request or a broker.

        Read as code with docstrings and comments removed, for the reason
        check_no_write_path.py gives: this module's own docstring explains that
        it never reaches the gateway, and a guard that cannot tell that from
        reaching one punishes the explanation.
        """
        source = code(ROOT / "src" / "options_alpha_lab" / "catalog.py")
        for token in ("ApprovedOrderIntent", "submit", "gateway", "broker", "OrderIntent"):
            self.assertNotIn(token, source)

    def test_trading_states_are_named_but_powerless(self) -> None:
        """They mark where a candidate may inform trading, not where it may trade."""
        self.assertEqual(
            TRADING_STATES, {CandidateState.PAPER_SHADOW, CandidateState.PAPER_ACTIVE}
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
