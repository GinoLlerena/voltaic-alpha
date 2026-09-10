"""Options Alpha - judge-facing dashboard.

Five read-only views over recorded evidence. There are no control actions: the
dashboard cannot start a run, approve an intent, or reach a broker, so there is
nothing here to protect with a permission check. That is the intended design,
not a simplification - the surface a judge browses is not the surface that
trades.

Design note. Colour is semantic rather than decorative, and the rule is stated
in the legend so it can be read at a glance: **amber marks anything the model
touched; cool blue marks values deterministic code owns.** Once a reader has the
rule, every view answers "how much of this did the model decide?" without any
prose. The authority rail across the top carries the same argument spatially:
the model occupies exactly one fenced box in a seven-stage pipeline, and it is
visible on every screen rather than described once and forgotten.
"""

from __future__ import annotations

import html
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import streamlit as st
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from options_alpha_lab.architecture.contracts import ExecutionState
from options_alpha_lab.persistence.models import (
    AuditEvent,
    Decision,
    Incident,
    MarketSnapshot,
    ModelCall,
    Position,
    PreparedOrderRequest,
    SpreadCandidateRecord,
)
from options_alpha_lab.presentation.artifacts import (
    correlate_ablation,
    correlate_receipt,
)
from options_alpha_lab.presentation.decision import load as decision_view
from options_alpha_lab.presentation.explain import why_decision
from options_alpha_lab.presentation.export import digest as proof_digest
from options_alpha_lab.presentation.export import render as proof_bytes
from options_alpha_lab.presentation.proof import proof_tiles
from options_alpha_lab.presentation.status import system_status
from options_alpha_lab.presentation.tour import SCENES
from options_alpha_lab.presentation.tour import scene as tour_scene

ROOT = Path(__file__).resolve().parent
DB = ROOT / "demo" / "h0_demo.db"
RECEIPT = ROOT / "artifacts" / "h0_paper_lifecycle.json"
ABLATION = ROOT / "artifacts" / "ablation_h0.json"

#: When DASHBOARD_DATABASE_URL is set the dashboard reads the live worker
#: database; otherwise it falls back to the committed evidence file. Read-only
#: either way: this page has no code path that writes, and no broker access.
LIVE_DATABASE_URL = os.environ.get("DASHBOARD_DATABASE_URL", "").strip()

STAGES = [
    ("01", "Evidence", "evidence"),
    ("02", "Setup", "evidence"),
    ("03", "Memo", "memo"),
    ("04", "Risk", "lineage"),
    ("05", "Intent", "lineage"),
    ("06", "Request", "lineage"),
    ("07", "Broker", "outcome"),
]

st.set_page_config(page_title="Options Alpha", page_icon="◬", layout="wide")
# st.markdown strips <style>; st.html is the supported path for raw CSS.
THEME = '\n<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">\n<style>\n:root{\n  /* Two temperatures, and the rule is semantic: warm means the model touched\n     it, cool means deterministic code owns it. Stated once in the legend, then\n     every view is scannable without reading. */\n  --ink:#0D1117; --panel:#151B23; --panel2:#1B222C; --edge:#263040; --edge2:#31405433;\n  --cool:#5AB3F0;      /* deterministic authority */\n  --warm:#E8A33D;      /* model, advisory only */\n  --affirm:#46D08A;    /* verified, flat, passed */\n  --alarm:#FF6161;     /* blocked, refused */\n  --text:#E7EDF5; --muted:#8896A8; --dim:#5C697A;\n  --mono:\'IBM Plex Mono\',ui-monospace,monospace;\n  --cond:\'IBM Plex Sans Condensed\',\'IBM Plex Sans\',system-ui,sans-serif;\n  --body:\'IBM Plex Sans\',system-ui,sans-serif;\n}\nhtml,body,[data-testid="stAppViewContainer"],[data-testid="stHeader"]{background:var(--ink)!important}\n[data-testid="stHeader"]{border-bottom:1px solid var(--edge)}\n.stApp{font-family:var(--body);color:var(--text)}\n.stApp p,.stApp li{font-family:var(--body)}\n/* Colour is inherited from .stApp rather than set on every span and div: a\n   broad element rule outranks a single-class semantic rule and would quietly\n   win over .pass, .fail and the tone classes. */\n[data-testid="stMainBlockContainer"]{padding-top:1.2rem;max-width:1500px}\n#MainMenu,footer{visibility:hidden}\n\n/* ---- masthead ---- */\n.oa-head{display:flex;align-items:baseline;gap:.85rem;flex-wrap:wrap;\n  border-bottom:1px solid var(--edge);padding-bottom:.7rem;margin-bottom:.9rem}\n.oa-head h1{font-family:var(--cond);font-weight:700;font-size:2.1rem;letter-spacing:-.015em;\n  margin:0;line-height:1;color:var(--text)}\n.oa-head .sub{font-family:var(--mono);font-size:.72rem;letter-spacing:.18em;\n  text-transform:uppercase;color:var(--dim)}\n.oa-head .spacer{flex:1}\n\n/* ---- annunciator panel: discrete lit tiles, cockpit vernacular ---- */\n.tour{border:1px solid var(--accent);background:rgba(232,163,61,.06);padding:.7rem .85rem;margin:.2rem 0 .7rem}\n.tour .hd{font-family:var(--mono);font-size:.6rem;letter-spacing:.14em;color:var(--accent)}\n.tour h3{font-family:var(--cond);font-weight:700;font-size:1.05rem;margin:.2rem 0 .3rem;color:var(--fg)}\n.tour p{font-size:.82rem;line-height:1.5;color:var(--fg);margin:0;max-width:70ch}\n.why{border-left:2px solid var(--accent);padding:.1rem 0 .1rem .8rem;margin:.2rem 0 .4rem}\n.why .s{font-family:var(--mono);font-size:.6rem;letter-spacing:.13em;color:var(--accent)}\n.why .s.na{color:var(--dim)}\n.why .t{font-size:.82rem;line-height:1.5;color:var(--fg);margin:.12rem 0 .5rem}\n.why .t.na{color:var(--dim)}\n.why .src{font-family:var(--mono);font-size:.58rem;color:var(--dim)}\n.oa-promise{margin:.2rem 0 .9rem}\n.oa-promise h2{font-family:var(--cond);font-weight:700;font-size:1.42rem;line-height:1.18;letter-spacing:-.01em;margin:0 0 .3rem;color:var(--fg)}\n.oa-promise p{font-size:.82rem;line-height:1.45;color:var(--dim);margin:0;max-width:62ch}\n.proof{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:.55rem;margin:.75rem 0 .5rem}\n.proof .p{border:1px solid var(--line);background:var(--panel);padding:.7rem .8rem}\n.proof .p.na{opacity:.62}\n.proof .n{font-family:var(--mono);font-size:1.72rem;font-weight:600;line-height:1;font-variant-numeric:tabular-nums;color:var(--fg)}\n.proof .l{font-size:.76rem;color:var(--fg);margin-top:.34rem;line-height:1.3}\n.proof .mode{font-family:var(--mono);font-size:.58rem;letter-spacing:.13em;color:var(--accent);margin-top:.4rem}\n.proof .src{font-family:var(--mono);font-size:.58rem;color:var(--dim);margin-top:.22rem;line-height:1.35}\n.ann{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1px;\n  background:var(--edge);border:1px solid var(--edge);margin:0 0 1.1rem}\n.ann .t{background:var(--panel);padding:.6rem .8rem}\n.ann .k{font-family:var(--mono);font-size:.61rem;letter-spacing:.15em;text-transform:uppercase;\n  color:var(--dim);margin-bottom:.28rem}\n.ann .v{font-family:var(--cond);font-weight:700;font-size:1.15rem;line-height:1.1;\n  display:flex;align-items:center;gap:.42rem}\n.ann .v::before{content:"";width:7px;height:7px;border-radius:50%;flex:none;\n  background:currentColor;box-shadow:0 0 8px currentColor}\n.ok{color:var(--affirm)} .warn{color:var(--warm)} .bad{color:var(--alarm)}\n.neutral{color:var(--cool)} .off{color:var(--dim)}\n.off .v::before,.ann .off::before{box-shadow:none;opacity:.45}\n\n/* ---- the signature: authority rail ---- */\n.rail{border:1px solid var(--edge);background:var(--panel);padding:.85rem .9rem 1rem;\n  margin-bottom:1.1rem;overflow-x:auto}\n.rail .cap{font-family:var(--mono);font-size:.61rem;letter-spacing:.15em;text-transform:uppercase;\n  color:var(--dim);margin-bottom:.65rem;display:flex;gap:1.2rem;flex-wrap:wrap}\n.rail .cap i{font-style:normal;display:inline-flex;align-items:center;gap:.34rem}\n.rail .cap i::before{content:"";width:8px;height:8px;border-radius:2px;background:currentColor}\n.flow{display:flex;align-items:stretch;gap:0;min-width:820px}\n.node{flex:1;border:1px solid var(--edge);background:var(--panel2);padding:.5rem .55rem;\n  text-align:center;position:relative}\n.node .n{font-family:var(--mono);font-size:.58rem;color:var(--dim);letter-spacing:.1em}\n.node .l{font-family:var(--cond);font-weight:600;font-size:.92rem;margin-top:.12rem;color:var(--muted)}\n.node.on{background:#101923;border-color:var(--cool);box-shadow:inset 0 -2px 0 var(--cool)}\n.node.on .l{color:var(--cool)}\n.node.model{border-color:var(--warm);background:#1F1808}\n.node.model .l{color:var(--warm)}\n.node.model.on{box-shadow:inset 0 -2px 0 var(--warm)}\n.node.model .n{color:var(--warm);opacity:.8}\n.arrow{display:flex;align-items:center;padding:0 .34rem;color:var(--edge);font-size:.85rem}\n.fence{font-family:var(--mono);font-size:.58rem;color:var(--warm);text-align:center;\n  margin-top:.5rem;letter-spacing:.08em}\n\n/* ---- panels & headings ---- */\n.oa-h{font-family:var(--cond);font-weight:600;font-size:1.02rem;letter-spacing:.01em;\n  color:var(--text);margin:1.35rem 0 .6rem;padding-bottom:.32rem;\n  border-bottom:1px solid var(--edge);display:flex;align-items:baseline;gap:.55rem}\n.oa-h small{font-family:var(--mono);font-size:.62rem;letter-spacing:.13em;text-transform:uppercase;\n  color:var(--dim);font-weight:400}\n.card{border:1px solid var(--edge);background:var(--panel);padding:.85rem .95rem}\n.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:.75rem}\n\n/* ---- data rows ---- */\n.kv{display:grid;grid-template-columns:170px 1fr;gap:.4rem .9rem;font-size:.86rem}\n.kv dt{font-family:var(--mono);font-size:.68rem;letter-spacing:.1em;text-transform:uppercase;\n  color:var(--dim);padding-top:.15rem}\n.kv dd{margin:0;font-family:var(--mono);font-size:.82rem;color:var(--text);word-break:break-all}\n\n/* ---- ordered guard list: these run in sequence, so number them ---- */\n.seq{counter-reset:g;display:flex;flex-direction:column;gap:1px;background:var(--edge);\n  border:1px solid var(--edge)}\n.seq li{counter-increment:g;list-style:none;background:var(--panel);padding:.5rem .8rem;\n  display:grid;grid-template-columns:26px 1fr auto;gap:.75rem;align-items:baseline}\n.seq li::before{content:counter(g);font-family:var(--mono);font-size:.7rem;color:var(--dim)}\n.seq .g{font-size:.87rem;color:var(--text)}\n.seq .b{font-family:var(--mono);font-size:.72rem;color:var(--muted);text-align:right}\n\n/* ---- checks ---- */\n.chk{display:flex;flex-direction:column;gap:1px;background:var(--edge);border:1px solid var(--edge)}\n.chk div{background:var(--panel);padding:.44rem .8rem;display:flex;justify-content:space-between;\n  gap:1rem;font-size:.84rem;align-items:baseline}\n.chk .m{font-family:var(--mono);font-size:.75rem}\n.pass{color:var(--affirm)} .fail{color:var(--alarm)}\n\n/* ---- hash chain: the differentiator, drawn as an actual chain ---- */\n.chain{display:flex;flex-direction:column;gap:0}\n.link{display:grid;grid-template-columns:180px 1fr;gap:.9rem;align-items:center;\n  border:1px solid var(--edge);border-bottom:none;background:var(--panel);padding:.55rem .8rem}\n.chain .link:last-child{border-bottom:1px solid var(--edge)}\n.link .lab{font-family:var(--mono);font-size:.66rem;letter-spacing:.11em;text-transform:uppercase;\n  color:var(--dim)}\n.link .dig{font-family:var(--mono);font-size:.78rem;color:var(--cool);word-break:break-all}\n.link.warm .dig{color:var(--warm)}\n.knot{font-family:var(--mono);font-size:.62rem;color:var(--dim);padding:.16rem 0 .16rem 1rem}\n\n/* ---- signal strength ---- */\n.sig{display:flex;flex-direction:column;gap:1px;background:var(--edge);border:1px solid var(--edge)}\n.sig .r{background:var(--panel);padding:.55rem .8rem;display:grid;\n  grid-template-columns:1fr 92px 54px;gap:.8rem;align-items:center}\n.sig .nm{font-size:.85rem}\n.sig .nm em{font-style:normal;font-family:var(--mono);font-size:.66rem;color:var(--dim);\n  display:block;letter-spacing:.09em;text-transform:uppercase}\n.bar{height:5px;background:var(--edge);position:relative}\n.bar i{position:absolute;inset:0 auto 0 0;display:block}\n.num{font-family:var(--mono);font-size:.78rem;text-align:right}\n\n/* ---- badges & prose ---- */\n.badge{font-family:var(--mono);font-size:.66rem;letter-spacing:.1em;text-transform:uppercase;\n  padding:.16rem .45rem;border:1px solid currentColor;display:inline-block}\n.memo{border-left:2px solid var(--warm);background:#1B160B;padding:.75rem .95rem;\n  font-size:.92rem;line-height:1.55}\n.note{color:var(--muted);font-size:.85rem;line-height:1.55}\n.rule{border:none;border-top:1px solid var(--edge);margin:1.1rem 0}\n\n/* ---- streamlit overrides ---- */\n[data-testid="stSidebar"]{background:var(--panel)!important;border-right:1px solid var(--edge)}\n[data-testid="stSidebar"] p,[data-testid="stSidebar"] label,[data-testid="stSidebar"] li{font-family:var(--body)}\n/* Icon fonts render ligatures: overriding their family shows the literal\n   ligature name instead of the glyph, e.g. keyboard_double_arrow_left on\n   the sidebar collapse control. Never let a broad rule reach them. */\n[data-testid="stIconMaterial"],span[class*="material-symbols"],\n.material-symbols-rounded,.material-symbols-outlined{\n  font-family:\"Material Symbols Rounded\",\"Material Symbols Outlined\",\"Material Icons\"!important;\n  font-weight:normal;font-style:normal;letter-spacing:normal;\n  text-transform:none;white-space:nowrap;direction:ltr;\n  -webkit-font-feature-settings:\"liga\";font-feature-settings:\"liga\"}\n.stTabs [data-baseweb="tab-list"]{gap:0;border-bottom:1px solid var(--edge);background:transparent}\n.stTabs [data-baseweb="tab"]{font-family:var(--mono)!important;font-size:.72rem!important;\n  letter-spacing:.11em;text-transform:uppercase;color:var(--dim)!important;\n  padding:.55rem .95rem!important;border-radius:0}\n.stTabs [aria-selected="true"]{color:var(--cool)!important;background:var(--panel)}\n.stTabs [data-baseweb="tab-highlight"]{background:var(--cool)!important}\n.stTabs [data-baseweb="tab-border"]{display:none}\n[data-testid="stRadio"] label p{font-size:.83rem!important}\ndiv[data-testid="stSelectbox"] div[data-baseweb="select"]>div{background:var(--panel2);\n  border-color:var(--edge);font-family:var(--mono);font-size:.82rem}\n[data-testid="stAlert"]{border-radius:0;font-size:.87rem}\ncode{font-family:var(--mono)!important;background:var(--panel2)!important;color:var(--cool)!important;\n  font-size:.8rem!important;padding:.1rem .3rem!important}\n:focus-visible{outline:2px solid var(--cool);outline-offset:2px}\n@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}\n</style>\n'  # noqa: E501 - one stylesheet literal, not code

# st.markdown strips <style> tags; st.html is the supported path for raw CSS.
st.html(THEME)


def esc(value: Any) -> str:
    return html.escape(str(value))


def money(value: Any) -> str:
    """Trim database scale. 300.000000 is a storage artefact, not a price."""
    if value is None:
        return "—"
    try:
        return f"{Decimal(str(value)).normalize():,.2f}"
    except Exception:  # noqa: BLE001 - display must not fail on an odd value
        return str(value)


def block(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


@st.cache_resource
def _resolve_source():  # type: ignore[no-untyped-def]
    """Prefer the live worker database, but never show a judge an empty page.

    The live database is empty until the worker has decided something, and a
    worker started outside market hours has not. Falling back to the committed
    evidence keeps the demo honest and working; the sidebar always says which
    source is in use, so "live" is never implied when it is not true.
    """
    committed = create_engine(f"sqlite+pysqlite:///{DB}", future=True)
    if not LIVE_DATABASE_URL:
        return committed, "committed evidence"
    try:
        live = create_engine(LIVE_DATABASE_URL, future=True, pool_pre_ping=True)
        with Session(live) as session:
            count = session.scalar(select(func.count()).select_from(Decision)) or 0
        if count:
            return live, f"live worker database ({count} decisions)"
        return committed, "committed evidence (live worker has decided nothing yet)"
    except Exception as exc:  # noqa: BLE001 - a broken live source must not break the page
        return committed, f"committed evidence (live source unavailable: {type(exc).__name__})"


def engine():  # type: ignore[no-untyped-def]
    return _resolve_source()[0]


def source_label() -> str:
    return _resolve_source()[1]


def rows(stmt: Any) -> list[Any]:
    with Session(engine()) as session:
        return list(session.scalars(stmt).all())


def scalar(stmt: Any) -> Any:
    with Session(engine()) as session:
        return session.scalar(stmt)


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a missing artifact must not break the page
        return {}


# ---------------------------------------------------------------- components
def annunciator(tiles: list[tuple[str, str, str]]) -> None:
    """Cockpit-style state panel: discrete lit tiles, readable without reading."""
    cells = "".join(
        f'<div class="t {tone}"><div class="k">{esc(k)}</div>'
        f'<div class="v">{esc(v)}</div></div>'
        for k, v, tone in tiles
    )
    block(f'<div class="ann">{cells}</div>')


def authority_rail(active: str) -> None:
    """The signature element. The model occupies one fenced box out of seven."""
    parts = []
    for index, (num, label, group) in enumerate(STAGES):
        classes = ["node"]
        if label == "Memo":
            classes.append("model")
        if group == active:
            classes.append("on")
        parts.append(
            f'<div class="{" ".join(classes)}"><div class="n">{num}</div>'
            f'<div class="l">{esc(label)}</div></div>'
        )
        if index < len(STAGES) - 1:
            parts.append('<div class="arrow">&rsaquo;</div>')
    block(
        '<div class="rail">'
        '<div class="cap">'
        '<i style="color:var(--cool)">deterministic code decides</i>'
        '<i style="color:var(--warm)">model advises only</i>'
        "</div>"
        f'<div class="flow">{"".join(parts)}</div>'
        '<div class="fence">the model writes stage 03 and reads nothing else; '
        "direction, invalidation, sizing, eligibility and every broker write "
        "live outside the fence</div>"
        "</div>"
    )


def heading(text: str, note: str = "") -> None:
    block(f'<div class="oa-h">{esc(text)}<small>{esc(note)}</small></div>')


def kv(pairs: list[tuple[str, str]]) -> None:
    body = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in pairs)
    block(f'<dl class="kv">{body}</dl>')


def badge(text: str, tone: str) -> str:
    return f'<span class="badge {tone}">{esc(text)}</span>'


def chain(links: list[tuple[str, str, bool]]) -> None:
    """Evidence to fill, drawn as an actual chain rather than a list of strings."""
    out = []
    for index, (label, digest, is_model) in enumerate(links):
        out.append(
            f'<div class="link{" warm" if is_model else ""}">'
            f'<div class="lab">{esc(label)}</div>'
            f'<div class="dig">{esc(digest)}</div></div>'
        )
        if index < len(links) - 1:
            out.append('<div class="knot">&#9482;</div>')
    block(f'<div class="chain">{"".join(out)}</div>')


def signals_panel(signals: list[Any], evidence_ids: set[str],
                  setup_direction: str = "") -> None:
    out = []
    for signal in sorted(signals, key=lambda s: -float(s.strength)):
        strength = float(signal.strength)
        used = signal.signal_id in evidence_ids
        counter = not used and signal.direction != setup_direction
        # Cited evidence is cool; genuine counter-evidence is amber, because it
        # argues against the setup; anything else is simply unused.
        colour = "var(--cool)" if used else ("var(--warm)" if counter else "var(--dim)")
        role = "cited" if used else ("counter-evidence" if counter else "observed, unused")
        out.append(
            '<div class="r">'
            f'<div class="nm">{esc(signal.summary[:110])}'
            f"<em>{esc(signal.family)} &middot; {esc(signal.direction)}"
            f" &middot; {esc(role)}</em></div>"
            f'<div class="bar"><i style="width:{strength * 100:.0f}%;'
            f'background:{colour}"></i></div>'
            f'<div class="num" style="color:{colour}">{strength:.2f}</div>'
            "</div>"
        )
    block(f'<div class="sig">{"".join(out)}</div>')


# ----------------------------------------------------------------- decisions
#: A polling agent produces roughly 66 decisions per session at a five-minute
#: cadence, so an unbounded list is a few hundred rows within days. The query is
#: bounded and the list is collapsed rather than paginated, because pagination
#: would still leave a judge scrolling past sixty identical refusals to find the
#: two decisions that matter.
DECISION_LIMIT = 400
RUN_THRESHOLD = 2


def load_decisions(limit: int = DECISION_LIMIT) -> tuple[list[Any], int]:
    total = int(scalar(select(func.count()).select_from(Decision)) or 0)
    recent = rows(select(Decision).order_by(Decision.recorded_at.desc()).limit(limit))
    return list(reversed(recent)), total


def outcome_key(decision: Any) -> tuple[str, str]:
    """What makes two decisions the same story: the action and why."""
    return decision.action, ", ".join(decision.reason_codes or [])


def collapse_runs(items: list[Any]) -> list[dict[str, Any]]:
    """Run-length encode consecutive identical outcomes.

    Sixty consecutive `NO_TRADE / no_qualified_setup` decisions are one fact, not
    sixty. Collapsing them keeps the two decisions that differ visible instead of
    burying them, and each run still exposes its most recent member so the full
    trace remains one click away.
    """
    runs: list[dict[str, Any]] = []
    for decision in items:
        key = outcome_key(decision)
        if runs and runs[-1]["key"] == key:
            runs[-1]["members"].append(decision)
        else:
            runs.append({"key": key, "members": [decision]})
    return runs


decisions, total_decisions = load_decisions()
if not decisions:
    block('<div class="oa-head"><h1>Options Alpha</h1></div>')
    st.error("No evidence database found. Run `python scripts/build_demo_db.py`.")
    st.stop()

receipt = load_json(RECEIPT)
ablation = load_json(ABLATION)
positions = rows(select(Position))
open_positions = [p for p in positions if p.lifecycle_status in {"OPEN", "CLOSING"}]
incidents = rows(select(Incident).where(Incident.resolved_at.is_(None)))

block(
    '<div class="oa-head"><h1>Options Alpha</h1>'
    '<div class="sub">auditable execution firewall</div>'
    '<div class="spacer"></div>'
    f'<div class="sub">{esc(source_label())}</div></div>'
)

# CIIP-003. The product promise comes before the disclosures, and every number
# beneath it is derived from a correlated record or a versioned artifact. A tile
# a person typed would be the hardcoded safety strip again, moved somewhere
# louder.
block(
    '<div class="oa-promise">'
    "<h2>AI options research, with execution authority kept in code.</h2>"
    "<p>A language model writes the memo. Deterministic code owns direction, "
    "invalidation, sizing, contract choice and every broker write &mdash; and "
    "each decision below carries the evidence chain that proves it.</p></div>"
)

with Session(engine()) as _proof_session:
    _tiles = proof_tiles(_proof_session, root=ROOT)
block(
    '<div class="proof">'
    + "".join(
        f'<div class="p{"" if tile.available else " na"}">'
        f'<div class="n">{esc(tile.value)}</div>'
        f'<div class="l">{esc(tile.label)}</div>'
        f'<div class="mode">{esc(tile.mode)}</div>'
        f'<div class="src">{esc(tile.source)}'
        + (f"<br>{esc(tile.detail)}" if tile.detail else "")
        + "</div></div>"
        for tile in _tiles
    )
    + "</div>"
)

# CIIP-CV-001. These were string constants, so the strip said the same
# reassuring thing over a live database, a fixture, or nothing at all. Values now
# come from `runs` and `worker_leases`; anything unsourceable renders UNKNOWN.
with Session(engine()) as _status_session:
    _status = system_status(_status_session)
annunciator([(item.label, item.value, item.tone) for item in _status])
block(
    '<div class="note" style="margin-top:-.4rem;margin-bottom:.9rem">'
    + " · ".join(
        f"{esc(i.label)}: {esc(i.source)}"
        + (f" ({esc(i.reason)})" if i.reason else "")
        for i in _status
    )
    + "</div>"
)

# ------------------------------------------------------------------- selector
st.sidebar.markdown(
    '<div style="font-family:var(--mono);font-size:.62rem;'
    'letter-spacing:.15em;text-transform:uppercase;color:var(--dim);'
    'margin-bottom:.4rem">Recorded decisions</div>',
    unsafe_allow_html=True,
)

view = st.sidebar.radio(
    "Show", ["Notable", "Positions", "Refusals", "Everything"],
    horizontal=False, label_visibility="collapsed", index=0,
)

if view == "Positions":
    candidates = [d for d in decisions if d.action == "OPTIONS_POSITION"]
elif view == "Refusals":
    candidates = [d for d in decisions if d.action != "OPTIONS_POSITION"]
else:
    candidates = list(decisions)

runs = collapse_runs(candidates)
if view == "Notable":
    # Every position, plus one representative of each run of identical refusals.
    entries = [
        {"decision": run["members"][-1], "count": len(run["members"]), "run": run}
        for run in runs
    ]
else:
    entries = [
        {"decision": member, "count": 1, "run": run}
        for run in runs
        for member in reversed(run["members"])
    ]

labels: dict[str, str] = {}
for entry in entries:
    decision_row = entry["decision"]
    name = decision_row.snapshot_id.replace("spy-", "SPY ").replace("-", " ")
    if decision_row.action == "OPTIONS_POSITION":
        summary = f"position · {decision_row.direction}"
    else:
        summary = ", ".join(decision_row.reason_codes or ["refused"])
    repeat = f"  ×{entry['count']}" if entry["count"] > 1 else ""
    labels[decision_row.id] = f"{name}\n{summary}{repeat}"

# CIIP-004. The tour step lives in the URL, so a scene is a shareable link rather
# than a sequence of instructions. A hand-edited step is clamped, not raised on.
params = st.query_params
try:
    tour_step = int(params.get("tour", 0))
except ValueError:
    tour_step = 0

forced_id: str | None = None
active_scene = tour_scene(tour_step) if tour_step else None
if active_scene is not None:
    forced_id = next(
        (d.id for d in decisions if d.snapshot_id == active_scene.snapshot_id), None
    )

options = list(labels)
index = options.index(forced_id) if forced_id in options else 0
chosen_id = st.sidebar.radio(
    "Decision", options, format_func=lambda k: labels[k], index=index,
    label_visibility="collapsed",
)
decision = next(d for d in decisions if d.id == chosen_id)

# CIIP-006. One resolve, isolated by construction, instead of a dozen ad hoc
# cross-table queries spread through five tab bodies. That scattering is how
# CIIP-CV-003 happened: a single query forgot its filter, and nothing could
# detect it while the evidence set held one lifecycle.
with Session(engine()) as _lineage_session:
    lineage = decision_view(_lineage_session, decision)

shown = len(labels)
st.sidebar.markdown(
    f'<div style="font-family:var(--mono);font-size:.62rem;color:var(--dim);'
    f'margin-top:.5rem;line-height:1.5">{shown} of {total_decisions} recorded'
    + (
        '<br>identical consecutive outcomes are grouped'
        if view == "Notable" and shown < len(candidates)
        else ""
    )
    + (
        f'<br>showing the most recent {DECISION_LIMIT}'
        if total_decisions > DECISION_LIMIT
        else ""
    )
    + "</div>",
    unsafe_allow_html=True,
)

st.sidebar.markdown('<hr class="rule">', unsafe_allow_html=True)
st.sidebar.markdown(
    f"**Source:** {source_label()}\n\n"
    "**What this is**\n\n"
    "A read-only view of decisions this system already made. It has no controls: "
    "it cannot start a run, approve an intent, or reach a broker.\n\n"
    "**Disclosures**\n\n"
    "- Alpaca **Paper** only. No live endpoint exists in this build.\n"
    "- Option quotes come from the **indicative** feed. The account has no OPRA "
    "agreement, so quotes are not trading-quality.\n"
    "- **No alpha is claimed.** A `NO_TRADE` refusal and a deterministic baseline "
    "beating the model are both valid results.\n"
    "- Nothing here is investment advice."
)

# CIIP-004. The guided path. Always paused, every step directly reachable, and
# no motion to reduce — the plan permits animated pacing rather than requiring
# it, and a timed auto-advance in Streamlit means blocking reruns.
if active_scene is not None:
    block(
        '<div class="tour">'
        f'<div class="hd">GUIDED PATH · STEP {active_scene.number} OF {len(SCENES)}'
        f" · {esc(source_label().upper())}</div>"
        f"<h3>{esc(active_scene.title)}</h3>"
        f"<p>{esc(active_scene.narration)}</p></div>"
    )
    nav = st.columns([1, 1, 1, 5])
    if active_scene.number > 1 and nav[0].button("← Back"):
        st.query_params["tour"] = str(active_scene.number - 1)
        st.rerun()
    if active_scene.number < len(SCENES) and nav[1].button("Next →"):
        st.query_params["tour"] = str(active_scene.number + 1)
        st.rerun()
    if nav[2].button("Exit tour"):
        st.query_params.clear()
        st.rerun()
else:
    if st.button("Start guided tour"):
        st.query_params["tour"] = "1"
        st.rerun()

# CIIP-007. A reviewer can leave with the proof chain as a file they can diff
# and check without this application or its database. Redaction is by allowlist,
# so a new column cannot leak into an export by default.
_manifest = proof_bytes(lineage)
st.download_button(
    "Download proof manifest",
    data=_manifest,
    file_name=f"proof-{decision.snapshot_id}.json",
    mime="application/json",
    help=f"Deterministic and redacted · {proof_digest(lineage)[:19]}…",
)

# CIIP-005. The five tabs hold everything needed to reconstruct a decision, but
# they make the reader do the reconstruction. This does it once, in authority
# order, and renders a missing stage rather than skipping it — the refusal case
# is three explicit absences, which is the point.
with st.expander("Why this decision?", expanded=True):
    with Session(engine()) as _why_session:
        _lines = why_decision(_why_session, decision)
    block(
        '<div class="why">'
        + "".join(
            f'<div class="s{"" if line.present else " na"}">{esc(line.stage.upper())}'
            + ("" if line.present else " · NO RECORD")
            + "</div>"
            f'<div class="t{"" if line.present else " na"}">{esc(line.text)}</div>'
            f'<div class="src">{esc(line.source)}</div>'
            for line in _lines
        )
        + "</div>"
    )

tabs = st.tabs([
    "Evidence & setup", "Model memo", "Approval lineage", "Outcome", "Guards & state",
])

snapshot = rows(
    select(MarketSnapshot).where(MarketSnapshot.id == decision.market_snapshot_id)
)[0]
packs = lineage.packs
theses = lineage.theses
spreads = rows(
    select(SpreadCandidateRecord).where(SpreadCandidateRecord.decision_id == decision.id)
)
risks = lineage.risks
intents = lineage.intents

# ----------------------------------------------------------- 1 evidence/setup
with tabs[0]:
    authority_rail("evidence")
    feed_note = (
        "recorded fixture, not a live quote"
        if snapshot.feed in {"fixture", ""}
        else f"{snapshot.provider} · {snapshot.feed} feed"
    )
    heading("What the system observed", feed_note)
    kv([
        ("Underlying", f"{snapshot.symbol} @ {money(snapshot.underlying_price)}"),
        ("Observed at", str(snapshot.source_time)),
        ("Input hash", snapshot.payload_hash),
    ])

    signals = lineage.signals
    cited = set(packs[0].evidence_ids) if packs else set()
    heading("Signals", "cited signals are lit; the rest were observed and not used")
    signals_panel(signals, cited, packs[0].direction if packs else "")

    heading("Deterministic qualification", "no model involved at this stage")
    if packs:
        pack = packs[0]
        block(
            f'<div class="card">{badge(pack.direction, "neutral")} '
            f'<span class="note">{esc(pack.setup_family)} · classifier '
            f"<code>{esc(pack.classifier_name)}</code></span>"
            '<div style="margin-top:.7rem"><div class="lab" style="font-family:var(--mono);'
            'font-size:.66rem;letter-spacing:.11em;text-transform:uppercase;color:var(--dim);'
            'margin-bottom:.3rem">Invalidation, set by code and not negotiable</div>'
            + "".join(
                f'<div class="note">— {esc(c)}</div>' for c in pack.invalidation_conditions
            )
            + "</div></div>"
        )
    else:
        block(
            f'<div class="card">{badge("no setup qualified", "bad")}'
            '<div class="note" style="margin-top:.6rem">The deterministic classifier '
            "declined before any model was consulted. Contradictory evidence is not "
            "something the model is asked to resolve, because it has no authority "
            "to resolve it.</div></div>"
        )

# ------------------------------------------------------------------- 2 memo
with tabs[1]:
    authority_rail("memo")
    if not theses:
        heading("Model memo", "not produced")
        block(
            '<div class="card"><div class="note">No memo exists for this decision. '
            "The setup did not qualify, so the model was never called. This is the "
            "cheapest possible refusal: it costs one classifier run and no tokens."
            "</div></div>"
        )
    else:
        thesis = theses[0]
        calls = rows(select(ModelCall).where(ModelCall.id == thesis.model_call_id))
        heading("Model memo", f"synthesizer {thesis.synthesizer_name}")
        block(
            f'<div class="memo">{esc(thesis.reasoning_summary)}</div>'
        )
        kv([
            ("Direction", f"{thesis.direction} (may only agree or abstain)"),
            ("Confidence", f"{thesis.confidence} — advisory, sizes nothing"),
            ("Cited evidence", ", ".join(thesis.evidence_ids) or "none"),
            ("Counter-evidence", ", ".join(thesis.counter_evidence_ids) or "none"),
        ])
        if calls:
            call = calls[0]
            heading("Provider call", "no prompt text or hidden reasoning is stored")
            kv([
                ("Model", f"{call.provider} / {call.model}"),
                ("Status", call.status),
                ("Latency", f"{call.latency_ms} ms"),
                ("Tokens", f"{call.input_tokens} in / {call.output_tokens} out"),
                ("Input hash", call.input_hash),
            ])

    heading("What the model cannot do", "enforced by absence, not by validation")
    block(
        '<ul class="seq">'
        '<li><span class="g">Pick a direction</span>'
        '<span class="b">may agree or abstain; a reversal is coerced to abstention</span></li>'
        '<li><span class="g">Change an invalidation level</span>'
        '<span class="b">never sent to the model; absent from its schema</span></li>'
        '<li><span class="g">Size the position</span>'
        '<span class="b">not in the prompt; computed after the memo</span></li>'
        '<li><span class="g">Choose the contracts</span>'
        '<span class="b">deterministic, from the observed chain</span></li>'
        '<li><span class="g">Reach a broker</span>'
        '<span class="b">no order tool exists on the model path</span></li>'
        "</ul>"
    )

# ---------------------------------------------------------------- 3 lineage
with tabs[2]:
    authority_rail("lineage")
    heading("Risk decision", "recomputed from observed quotes, never trusted from the candidate")
    if risks:
        risk = risks[0]
        tone = "ok" if risk.approved else "bad"
        block(
            f'<div class="card">{badge("approved" if risk.approved else "rejected", tone)}'
            f'<span class="note" style="margin-left:.6rem">max loss '
            f"<b>{money(risk.calculated_max_loss)}</b> against a budget of "
            f"<b>{money(risk.risk_budget)}</b> · policy <code>"
            f"{esc(risk.policy_version)}</code></span></div>"
        )
        if risk.checks:
            out = []
            for check in risk.checks:
                passed = bool(check.get("passed"))
                extra = " · ".join(
                    f"{k}={v}" for k, v in check.items() if k not in {"check", "passed"}
                )
                out.append(
                    '<div><span>' + esc(str(check.get("check", "")).replace("_", " "))
                    + (f' <span class="m" style="color:var(--dim)">{esc(extra)}</span>'
                       if extra else "")
                    + "</span>"
                    + f'<span class="m {"pass" if passed else "fail"}">'
                    + ("PASS" if passed else "FAIL") + "</span></div>"
                )
            block(f'<div class="chk">{"".join(out)}</div>')
    else:
        block('<div class="card"><div class="note">No risk decision: the workflow '
              "terminated before a spread was proposed.</div></div>")

    heading("Hash lineage", "each link binds the next to the evidence it came from")
    links: list[tuple[str, str, bool]] = [
        ("Observation", snapshot.payload_hash, False),
        ("Decision", decision.decision_hash, False),
    ]
    prepared_all: list[Any] = []
    for intent in intents:
        links.append((f"Intent · {intent.approval_reference}", intent.intent_hash, False))
        prepared = rows(
            select(PreparedOrderRequest).where(
                PreparedOrderRequest.order_intent_id == intent.id
            )
        )
        prepared_all.extend(prepared)
        for request in prepared:
            links.append(("Prepared request", request.request_hash, False))
    chain(links)

    if intents:
        heading("Client order id", "derived, never generated")
        for intent in intents:
            block(
                f'<div class="card"><code>{esc(intent.client_order_id)}</code>'
                '<div class="note" style="margin-top:.5rem">The first 28 hex characters '
                "of the intent hash. Because it is derived, the same approved intent can "
                "only ever produce the same id, so a duplicate submit collides at the "
                "broker instead of opening a second strategy.</div></div>"
            )

    if prepared_all:
        heading("Exact request sent to the broker", "the bytes that were approved")
        for request in prepared_all:
            st.json(request.serialized_request, expanded=False)
            if request.intent_hash_match:
                st.success("Request hash matches the approved intent.")
            else:
                st.error("Request does not match the approved intent. A write would be refused.")

# ---------------------------------------------------------------- 4 outcome
with tabs[3]:
    authority_rail("outcome")
    if decision.action != "OPTIONS_POSITION":
        heading("Outcome", "refusal")
        block(
            f'<div class="card">{badge(decision.action, "bad")}'
            f'<span class="note" style="margin-left:.6rem">'
            f'{esc(", ".join(decision.reason_codes) or "refused")}</span>'
            '<div class="note" style="margin-top:.7rem">A refusal is a first-class '
            "result. It is reproducible from the recorded evidence and required no "
            "model call.</div></div>"
        )
    else:
        heading("Selected structure", "deterministic eligibility and tie-breaking")
        if spreads:
            spread = spreads[0]
            kv([
                ("Strategy", spread.strategy.replace("_", " ")),
                ("Long leg", spread.long_contract_symbol),
                ("Short leg", spread.short_contract_symbol),
                ("Quantity", str(spread.quantity)),
                ("Estimated debit", money(spread.estimated_debit)),
                ("Maximum loss", money(spread.calculated_max_loss)),
            ])

    # CIIP-CV-003. This used to select every BrokerOrder in the database, which
    # looked coherent only while exactly one lifecycle existed. Traverse the
    # lineage instead: Decision -> OrderIntent -> BrokerOrder -> Fill.
    orders = lineage.orders
    if orders:
        heading("Reconciled broker state", "acceptance is not a fill")
        for order in orders:
            fills = lineage.fills_for(order.id)
            leg_text = " · ".join(f"{f.leg_symbol} @ {money(f.price)}" for f in fills)
            block(
                f'<div class="card" style="margin-bottom:.5rem">'
                f'{badge(order.role, "neutral")} '
                f'{badge(order.status, "ok" if order.status == "filled" else "warn")}'
                f'<code style="margin-left:.5rem">{esc(order.client_order_id)}</code>'
                f'<div class="note" style="margin-top:.5rem">filled '
                f"{order.filled_quantity}/{order.strategy_quantity} at an average of "
                f"<b>{money(order.filled_avg_price)}</b> against a "
                f"{esc(order.status)} order"
                + (f'<br><span class="m">{esc(leg_text)}</span>' if leg_text else "")
                + "</div></div>"
            )

    # Risk accounting, not performance reporting. A judge will ask "did it make
    # money"; the honest and more interesting answer is how the position was
    # sized and what the round trip actually cost. An equity curve or a win rate
    # at n=1 would be theatre.
    if risks and spreads:
        risk, spread = risks[0], spreads[0]
        budget = Decimal(str(risk.risk_budget))
        used = Decimal(str(risk.calculated_max_loss))
        pct = float(used / budget * 100) if budget else 0.0
        equity = (snapshot.payload or {}).get("account", {}).get("equity", "—")
        heading("Risk accounting", "sized before entry, not discovered after")
        block(
            '<div class="card">'
            '<div class="kv" style="grid-template-columns:190px 1fr">'
            f"<dt>Account equity</dt><dd>{money(equity)}</dd>"
            f"<dt>Risk budget</dt><dd>{money(budget)} &nbsp;<span style='color:var(--dim)'>"
            "0.5% of equity, provisional</span></dd>"
            f"<dt>Maximum loss</dt><dd>{money(used)} &nbsp;<span style='color:var(--dim)'>"
            "known at entry: a debit spread cannot lose more than it cost</span></dd>"
            "</div>"
            f'<div style="margin-top:.75rem"><div class="bar" style="height:9px">'
            f'<i style="width:{min(pct, 100):.0f}%;background:var(--cool)"></i></div>'
            f'<div class="m" style="font-family:var(--mono);font-size:.7rem;color:var(--dim);'
            f'margin-top:.35rem">{pct:.0f}% of the risk budget committed &middot; '
            "the remainder is not available to a second strategy, because H0 permits "
            "one open position</div></div></div>"
        )

    # CIIP-CV-002. The selected decision may come from a live database while the
    # receipt and ablation always come from committed files. Placed together
    # without a qualifier, the receipt reads as this decision's outcome — which
    # it usually is not. Correlate explicitly; adjacency is not evidence.
    receipt_link = correlate_receipt(lineage, receipt)
    ablation_link = correlate_ablation(lineage, ablation)

    final = receipt.get("final_state") or {}
    if final:
        if receipt_link.belongs:
            heading("Realised result", "a diagnostic, not a score")
        else:
            heading("Realised result — a different decision", receipt_link.relation)
            block(
                '<div class="card" style="border-color:var(--accent);margin-bottom:.6rem">'
                f'<div class="note">{esc(receipt_link.reason)}'
                + (
                    f" (checked on <code>{esc(receipt_link.matched_on)}</code>)"
                    if receipt_link.matched_on
                    else ""
                )
                + "</div></div>"
            )
        metrics = [
            ("Open positions", str(final.get("open_positions", "—")), "ok"),
            ("Equity", str(final.get("equity_after", "—")), "neutral"),
            ("Realised", str(final.get("realized", "—")), "warn"),
        ]
        annunciator(metrics)
        if ablation.get("metrics"):
            # Corpus-level, so it is rendered as its own card rather than as a
            # metric of the selected decision.
            block(
                '<div class="card" style="margin-top:.6rem">'
                f'{badge("ABLATION", "neutral")} '
                f'<b>{esc(str(ablation["metrics"].get("decisions_changed_by_model", "—")))}</b>'
                " decisions changed by the model"
                f'<div class="note" style="margin-top:.4rem">{esc(ablation_link.reason)}'
                "</div></div>"
            )
        opened = (receipt.get("open") or {}).get("filled_avg_price")
        closed = (receipt.get("close") or {}).get("filled_avg_price")
        if opened and closed:
            block(
                '<div class="card"><div class="kv" style="grid-template-columns:190px 1fr">'
                f"<dt>Entered at</dt><dd>{esc(opened)} debit</dd>"
                f"<dt>Exited at</dt><dd>{esc(closed)} credit</dd>"
                f"<dt>Round trip</dt><dd>{esc(final.get('realized', '—'))} "
                "&nbsp;<span style='color:var(--dim)'>the cost of crossing the spread "
                "twice on one contract</span></dd></div></div>"
            )
        block(
            '<div class="note" style="margin-top:.6rem">'
            "P&amp;L is reported here with its sample size, which is one round trip. "
            "That is far too small to say anything about the strategy, and the "
            "published judging criteria do not include P&amp;L. What the number does "
            "show is the friction any real edge would have to clear first. "
            "An ablation that cannot return &ldquo;no difference&rdquo; is not "
            "measuring anything, so that result is published rather than buried."
            "</div>"
        )

    heading("Audit trail", "every transition, in order")
    events = rows(
        select(AuditEvent)
        .where(AuditEvent.correlation_id == decision.snapshot_id)
        .order_by(AuditEvent.sequence)
    )
    block(
        '<ul class="seq">'
        + "".join(
            f'<li><span class="g">{esc(e.stage)} — {esc(e.outcome)}</span>'
            f'<span class="b">{esc(e.component)}'
            + (f' · {esc(", ".join(e.reason_codes))}' if e.reason_codes else "")
            + "</span></li>"
            for e in events
        )
        + "</ul>"
    )

# ------------------------------------------------------------- 5 guards/state
with tabs[4]:
    authority_rail("")
    heading("What blocks a write", "checked immediately before every order, in this order")
    block(
        '<ul class="seq">'
        '<li><span class="g">Configuration permits writes</span>'
        '<span class="b">blocks any mode but paper_execute</span></li>'
        '<li><span class="g">Resolved endpoint is Paper</span>'
        '<span class="b">blocks a client pointing anywhere else</span></li>'
        '<li><span class="g">Execution state allows the write</span>'
        '<span class="b">blocks NO_NEW_RISK and FREEZE_ALL_WRITES</span></li>'
        '<li><span class="g">An operator has approved</span>'
        '<span class="b">blocks an autonomous open when approval is required</span></li>'
        '<li><span class="g">No strategy already open</span>'
        '<span class="b">blocks a second concurrent position</span></li>'
        '<li><span class="g">Intent has not expired</span>'
        '<span class="b">blocks a stale approval past its 90 s TTL</span></li>'
        '<li><span class="g">Request still matches the intent hash</span>'
        '<span class="b">blocks bytes that drifted after approval</span></li>'
        "</ul>"
        '<div class="note" style="margin-top:.6rem">They run before every order rather '
        "than at startup, because the interesting failures develop between the two. "
        "Risk-reducing closes are exempt from guards 3, 4 and 5: those exist to stop "
        "new risk, and applying them to an exit would trap exposure at the moment it "
        "most needs reducing.</div>"
    )

    heading("Halt states", "POLICY SIMULATOR · NO STATE CHANGE")
    state = st.selectbox(
        "Durable execution state", [s.value for s in ExecutionState], index=0,
        label_visibility="collapsed",
    )
    if state == ExecutionState.NORMAL.value:
        st.success("New risk permitted. Closes and cancels also permitted.")
    elif state == ExecutionState.NO_NEW_RISK.value:
        st.warning(
            "New or increased risk blocked. Cancels and risk-reducing closes stay "
            "permitted, because blocking a close during a loss would trap exposure."
        )
    else:
        st.error(
            "All writes blocked, including closes. Reserved for adapter, credential or "
            "endpoint integrity incidents, and it raises an incident precisely because "
            "it can temporarily prevent risk reduction."
        )

    if incidents:
        heading("Open incidents", "durable, not a console line")
        for incident in incidents:
            block(
                f'<div class="card" style="margin-bottom:.4rem">'
                f'{badge(incident.severity, "bad")} <code>{esc(incident.kind)}</code>'
                f'<div class="note" style="margin-top:.4rem">{esc(incident.detail)}</div></div>'
            )
    else:
        heading("Open incidents", "none")
        block('<div class="card"><div class="note">No unresolved integrity incident. '
              "Anything that halts new risk writes a durable row here rather than "
              "printing to a log that dies with the process.</div></div>")
