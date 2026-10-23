"""Step 6 of the veto backtest: the portfolio rules, on hand-made trades.

Each test pins one rule: one position at a time, re-entry only after the exit
session, the budget read from the running equity, an unresolved exit charged
its whole debit and holding capacity to its window's end, and arms differing
only in which sessions they may use.
"""

import unittest
from datetime import date, timedelta
from decimal import Decimal

from options_alpha_lab import veto_entries as ve
from options_alpha_lab import veto_exits as vx
from options_alpha_lab import veto_portfolio as vp
from options_alpha_lab.veto_replay import BREADTH_VETOED, PERMITTED

SESSIONS = [date(2024, 3, 1) + timedelta(days=i) for i in range(20)]


def entry(i: int, group: str = PERMITTED, status: str = ve.ENTERED,
          debit: str = "3.00") -> ve.Entry:
    return ve.Entry(session=SESSIONS[i].isoformat(), group=group, status=status,
                    chain_calls=2, dropped=0, estimated_debit=debit, fill_reference=debit)


def trade(i: int, exit_day: int | None, result: float | None, group: str = PERMITTED,
          case: str = "central") -> vx.Trade:
    exited = None if exit_day is None else f"{SESSIONS[exit_day].isoformat()}T10:00:00-05:00"
    status = vx.CLOSED if result is not None else vx.NO_EXIT_FILL
    return vx.Trade(SESSIONS[i].isoformat(), group, case, "3.00", "6", status,
                    exited_at=exited, result_usd=result)


def go(entries: list[ve.Entry], trades: list[vx.Trade], arm: str = vp.BASELINE) -> vp.Path:
    index = {(t.session, t.case): t for t in trades}
    ends = vp.window_ends(entries, SESSIONS)
    return vp.run(arm, "central", entries, index, ends)


class Rules(unittest.TestCase):
    def test_one_position_and_re_entry_after_the_exit_session(self) -> None:
        # Entry on day 0 exits on day 2: days 1 and 2 are busy, day 3 may enter.
        e = [entry(0), entry(1), entry(2), entry(3)]
        t = [trade(0, 2, 100.0), trade(1, 2, 50.0), trade(2, 4, 50.0), trade(3, 5, -40.0)]
        p = go(e, t)
        self.assertEqual([ev[2] for ev in p.events],
                         [vp.TRADED, vp.CAPACITY, vp.CAPACITY, vp.TRADED])
        self.assertEqual(p.equity, Decimal("100060.0"))

    def test_budget_is_read_from_the_running_equity(self) -> None:
        # 0.75% of 100,000 is 750: a 7.40 debit fits. After a 60,000 loss the
        # budget is 300, and the same debit no longer does.
        e = [entry(0, debit="7.40"), entry(2, debit="7.40")]
        t = [trade(0, 1, -60000.0), trade(2, 3, 10.0)]
        p = go(e, t)
        self.assertEqual(p.events[1][2], vp.OVER_BUDGET)

    def test_unresolved_charges_the_debit_and_holds_to_the_window_end(self) -> None:
        e = [entry(0), entry(3), entry(5)]
        t = [trade(0, None, None), trade(3, 4, 20.0), trade(5, 6, 30.0)]
        p = go(e, t)
        # Window: day 0 plus four sessions, so day 4. Day 3 is busy, day 5 trades.
        self.assertEqual([ev[2] for ev in p.events], [vp.TRADED, vp.CAPACITY, vp.TRADED])
        self.assertEqual(p.events[0][3], -300.0)
        self.assertEqual(p.unresolved, [SESSIONS[0].isoformat()])

    def test_a_session_with_no_entry_is_recorded_and_passed(self) -> None:
        e = [entry(0, status=ve.UNFILLED), entry(1)]
        t = [trade(1, 2, 10.0)]
        self.assertEqual([ev[2] for ev in go(e, t).events], [ve.UNFILLED, vp.TRADED])

    def test_arms_differ_only_in_the_sessions_they_may_use(self) -> None:
        e = [entry(0, BREADTH_VETOED), entry(1)]
        t = [trade(0, 3, -100.0, BREADTH_VETOED), trade(1, 2, 80.0)]
        base, without = go(e, t), go(e, t, vp.WITHOUT_VETO)
        self.assertEqual(base.equity, Decimal("100080.0"))
        # Without the veto, day 0 is taken and blocks day 1.
        self.assertEqual([ev[2] for ev in without.events], [vp.TRADED, vp.CAPACITY])
        self.assertEqual(without.equity, Decimal("99900.0"))

    def test_largest_fall_is_peak_to_trough(self) -> None:
        e = [entry(0), entry(2), entry(4)]
        t = [trade(0, 1, 100.0), trade(2, 3, -250.0), trade(4, 5, 50.0)]
        self.assertEqual(go(e, t).worst_fall, Decimal("250.0"))


if __name__ == "__main__":
    unittest.main()
