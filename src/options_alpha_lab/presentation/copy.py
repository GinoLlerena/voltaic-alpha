"""Public copy that states a system rule, owned by the server.

`RUI-1`. The redesign's rule is that copy describing authority -- what blocks a
write, what the model cannot do, what a halt state permits, what is disclosed --
is server-owned rather than typed into each client. This is that copy, moved out
of `app.py` word for word, so the dashboard and the API cannot drift apart on
what the system claims about itself.

Interface microcopy (a heading's subtitle, an empty-state note) stays with the
client that renders it. The line drawn is whether a sentence makes a claim about
the system's behaviour that a reviewer could check.

`RUI-VAL-010`. The proof manifest carries its own, different disclosures
(`export.DISCLOSURES`: "... the sample is two trades"), where this page says a
NO_TRADE refusal and a losing baseline are valid results and elsewhere calls
the sample one round trip. They are not unified here: the manifest's bytes are
pinned by the digests reviewers keep, so changing them needs a manifest version
bump, and a sample size should be derived from records rather than typed in
either place.
"""

from __future__ import annotations

from dataclasses import dataclass

WHAT_THIS_IS = (
    "A read-only view of decisions this system already made. It has no controls: "
    "it cannot start a run, approve an intent, or reach a broker."
)

#: Markdown, as the page renders it.
DISCLOSURES = (
    "Alpaca **Paper** only. No live endpoint exists in this build.",
    "Option quotes come from the **indicative** feed. The account has no OPRA "
    "agreement, so quotes are not trading-quality.",
    "**No alpha is claimed.** A `NO_TRADE` refusal and a deterministic baseline "
    "beating the model are both valid results.",
    "Nothing here is investment advice.",
)


@dataclass(frozen=True)
class Rule:
    name: str
    effect: str


#: Checked immediately before every order, in this order.
WRITE_GUARDS = (
    Rule("Configuration permits writes", "blocks any mode but paper_execute"),
    Rule("Resolved endpoint is Paper", "blocks a client pointing anywhere else"),
    Rule("Execution state allows the write", "blocks NO_NEW_RISK and FREEZE_ALL_WRITES"),
    Rule("An operator has approved", "blocks an autonomous open when approval is required"),
    Rule("No strategy already open", "blocks a second concurrent position"),
    Rule("Intent has not expired", "blocks a stale approval past its 90 s TTL"),
    Rule("Request still matches the intent hash", "blocks bytes that drifted after approval"),
)

WRITE_GUARDS_NOTE = (
    "They run before every order rather than at startup, because the interesting "
    "failures develop between the two. Risk-reducing closes are exempt from guards "
    "3, 4 and 5: those exist to stop new risk, and applying them to an exit would "
    "trap exposure at the moment it most needs reducing."
)

#: Enforced by absence, not by validation.
MODEL_LIMITS = (
    Rule("Pick a direction", "may agree or abstain; a reversal is coerced to abstention"),
    Rule("Change an invalidation level", "never sent to the model; absent from its schema"),
    Rule("Size the position", "not in the prompt; computed after the memo"),
    Rule("Choose the contracts", "deterministic, from the observed chain"),
    Rule("Reach a broker", "no order tool exists on the model path"),
)


@dataclass(frozen=True)
class HaltState:
    state: str
    tone: str
    explanation: str


HALT_STATES = (
    HaltState("NORMAL", "ok", "New risk permitted. Closes and cancels also permitted."),
    HaltState(
        "NO_NEW_RISK", "warn",
        "New or increased risk blocked. Cancels and risk-reducing closes stay "
        "permitted, because blocking a close during a loss would trap exposure.",
    ),
    HaltState(
        "FREEZE_ALL_WRITES", "bad",
        "All writes blocked, including closes. Reserved for adapter, credential or "
        "endpoint integrity incidents, and it raises an incident precisely because "
        "it can temporarily prevent risk reduction.",
    ),
)
