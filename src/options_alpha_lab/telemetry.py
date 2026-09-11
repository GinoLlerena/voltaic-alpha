"""Structured worker events that can be joined to the records they describe.

`CIIP-I-006` and `CIIP-I-007`. The worker already emitted JSON, which is why the
gap was easy to miss: the lines looked structured and were not usable as
evidence. Nothing carried a `run_id`, so a log line could not be joined to the
run, decision or snapshot it described, and `position_clock` emitted at the same
level as an incident — a metronome burying the signal.

Two ideas do the work.

**Identity travels with every line.** `emit` attaches `run_id`, `lease_owner`
and `correlation_id` to everything, so `journalctl` output and the database
describe the same events rather than two parallel stories.

**Cadence is suppressed by repetition, not by rate.** A naive "log every tenth
tick" throws away the tick where something changed, which is the only one that
mattered. `CadenceFilter` instead emits when the reported action *changes*, and
otherwise at a heartbeat interval so a quiet system still proves it is alive. A
position held at the same action for an hour produces a handful of lines; the
moment it moves toward an exit, that line is emitted immediately.

State changes and faults are never suppressed. There is no sampling path that
can drop an incident.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any, Literal, TextIO

#: `state` is a transition worth keeping forever; `cadence` is a routine clock
#: line; `fault` is an error. Only `cadence` is ever suppressed.
Kind = Literal["state", "cadence", "fault"]

#: Emit a repeated cadence line at least this often, so silence is never
#: ambiguous between "nothing changed" and "the process died".
HEARTBEAT_EVERY = 15


@dataclass
class Context:
    """Identity attached to every line this worker emits."""

    run_id: str | None = None
    lease_owner: str | None = None

    def fields(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.run_id:
            out["run_id"] = self.run_id
        if self.lease_owner:
            out["lease_owner"] = self.lease_owner
        return out


def emit(
    event: str,
    *,
    kind: Kind = "state",
    context: Context | None = None,
    correlation_id: str | None = None,
    stream: TextIO | None = None,
    **fields: Any,
) -> None:
    """Write one structured line. Key order is stable so output diffs cleanly."""
    payload: dict[str, Any] = {"event": event, "kind": kind}
    if context is not None:
        payload.update(context.fields())
    if correlation_id:
        payload["correlation_id"] = correlation_id
    payload.update(fields)
    target = stream if stream is not None else sys.stdout
    print(json.dumps(payload), file=target, flush=True)


@dataclass
class CadenceFilter:
    """Decides whether a routine clock line is worth emitting.

    Keyed by event name, so the order clock and the position clock suppress
    independently — one of them going quiet must not hide the other.
    """

    heartbeat_every: int = HEARTBEAT_EVERY
    _last: dict[str, str] = field(default_factory=dict)
    _since: dict[str, int] = field(default_factory=dict)

    def should_emit(self, event: str, action: str) -> bool:
        """True when the action changed, or the heartbeat interval elapsed."""
        previous = self._last.get(event)
        self._since[event] = self._since.get(event, 0) + 1
        if previous != action:
            self._last[event] = action
            self._since[event] = 0
            return True
        if self._since[event] >= self.heartbeat_every:
            self._since[event] = 0
            return True
        return False

    def suppressed(self, event: str) -> int:
        """How many lines have been held back since the last emitted one."""
        return self._since.get(event, 0)
