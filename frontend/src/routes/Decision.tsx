import { Link } from "@tanstack/react-router";
import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { useResource } from "../api/useResource";
import { DecisionTicket } from "../components/DecisionTicket";
import { Evidence } from "../components/Evidence";
import { Invalidation } from "../components/Invalidation";
import { Lifecycle } from "../components/Lifecycle";
import { Memo } from "../components/Memo";
import { ProofLineage } from "../components/ProofLineage";
import { Loaded } from "../components/ResourceState";
import { Risk } from "../components/Risk";
import { SourceBanner } from "../components/SourceBanner";
import { TraderSummary } from "../components/TraderSummary";
import { Structure } from "../components/Structure";

type Summary = Schemas["DecisionSummary"];
type Market = Schemas["MarketOut"];
type MemoData = Schemas["MemoOut"];
type StructureData = Schemas["StructureOut"];
type RiskData = Schemas["RiskOut"];
type LifecycleData = Schemas["LifecycleOut"];
type ProofData = Schemas["ProofOut"];
type Horizons = Schemas["DecisionHorizonOut"][];

/**
 * One decision, addressable by its hash so the link is the evidence.
 *
 * `PUI-003`: eight requests, eight states. Each panel renders from its own
 * request: loading, unavailable, stale or verified. A failed panel never
 * becomes its "nothing recorded" text, and panels answered from a different
 * source than the summary say so.
 */
export function Decision({ digest }: { digest: string }) {
  const summary = useResource<Summary>(api.summary(digest));
  const market = useResource<Market>(api.market(digest));
  const memo = useResource<MemoData>(api.memo(digest));
  const structure = useResource<StructureData>(api.structure(digest));
  const risk = useResource<RiskData>(api.risk(digest));
  const lifecycle = useResource<LifecycleData>(api.lifecycle(digest));
  const proof = useResource<ProofData>(api.proof(digest));
  const horizons = useResource<Horizons>(api.outcomes(digest));

  if (summary.state === "failed") {
    // Only the server's 404 says the decision does not exist. A network or
    // server failure says nothing about the record, and must not be read as absence.
    return summary.notFound ? (
      <p role="alert" className="failed" data-testid="decision-missing">
        This source holds no decision with that hash.{" "}
        <Link to="/">Back to the overview</Link>
      </p>
    ) : (
      <p role="alert" className="failed" data-testid="decision-unavailable">
        This decision could not be loaded ({summary.reason}). That is a failed request, not a
        missing record.{" "}
        <button type="button" onClick={summary.retry}>
          Retry
        </button>{" "}
        <Link to="/">Back to the overview</Link>
      </p>
    );
  }
  if (summary.state === "loading") {
    return (
      <p role="status" data-testid="decision-loading">
        Loading the decision…
      </p>
    );
  }

  const source = summary.envelope.source_label;
  return (
    <>
      <SourceBanner
        envelope={summary.envelope}
        stale={summary.stale}
        {...(summary.state === "stale" ? { reason: summary.reason } : {})}
      />
      <p>
        <Link to="/">← All decisions</Link>
      </p>
      <DecisionTicket
        summary={summary.envelope.data}
        market={market}
        horizons={horizons}
      />
      {/* RUI-4's five questions, in the order a trader asks them: why this
          direction, why now, why this structure, what it can lose, and what
          would prove it wrong. Everything below is a record or an absence. */}
      <Loaded
        what="trader summary"
        resources={{ market, memo, structure, risk }}
        expectedSource={source}
      >
        {(d) => <TraderSummary market={d.market} memo={d.memo} structure={d.structure} risk={d.risk} />}
      </Loaded>
      <Loaded what="setup and memo" resources={{ memo, market }} expectedSource={source}>
        {(d) => <Memo memo={d.memo} market={d.market} />}
      </Loaded>
      <Loaded what="market evidence" resources={{ market }} expectedSource={source}>
        {(d) => <Evidence market={d.market} />}
      </Loaded>
      <Loaded what="structure" resources={{ structure }} expectedSource={source}>
        {(d) => <Structure structure={d.structure} />}
      </Loaded>
      <Loaded what="risk record" resources={{ risk }} expectedSource={source}>
        {(d) => <Risk risk={d.risk} />}
      </Loaded>
      <Loaded what="invalidation conditions" resources={{ market, memo }} expectedSource={source}>
        {(d) => <Invalidation market={d.market} memo={d.memo} />}
      </Loaded>
      <Loaded what="lifecycle" resources={{ lifecycle }} expectedSource={source}>
        {(d) => <Lifecycle lifecycle={d.lifecycle} />}
      </Loaded>
      <Loaded what="proof lineage" resources={{ lifecycle, proof }} expectedSource={source}>
        {(d) => <ProofLineage digest={digest} lifecycle={d.lifecycle} proof={d.proof} />}
      </Loaded>
    </>
  );
}
