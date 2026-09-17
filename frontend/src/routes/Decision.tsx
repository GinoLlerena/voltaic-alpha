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

/** One decision, addressable by its hash so the link is the evidence. */
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
    return (
      <p role="alert" className="failed" data-testid="decision-missing">
        This source holds no decision with that hash ({summary.reason}).{" "}
        <Link to="/">Back to the overview</Link>
      </p>
    );
  }
  if (summary.state === "loading") return <p>Loading…</p>;

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
        market={ready(market)}
        horizons={
          horizons.state === "ready" || horizons.state === "stale"
            ? horizons.envelope.data
            : []
        }
      />
      {/* RUI-4's five questions, in the order a trader asks them: why this
          direction, why now, why this structure, what it can lose, and what
          would prove it wrong. Everything below is a record or an absence. */}
      <TraderSummary
        market={ready(market)}
        memo={ready(memo)}
        structure={ready(structure)}
        risk={ready(risk)}
      />
      <Memo memo={ready(memo)} market={ready(market)} />
      <Evidence market={ready(market)} />
      <Structure structure={ready(structure)} />
      <Risk risk={ready(risk)} />
      <Invalidation market={ready(market)} memo={ready(memo)} />
      <Lifecycle lifecycle={ready(lifecycle)} />
      <ProofLineage digest={digest} lifecycle={ready(lifecycle)} proof={ready(proof)} />
    </>
  );
}

/**
 * A resource's data once it has some, or null.
 *
 * A panel that cannot tell "still loading" from "the server holds nothing"
 * would render an absence that is not true yet, so every panel below takes
 * null and says what it means in its own terms.
 */
function ready<T>(resource: ReturnType<typeof useResource<T>>): T | null {
  return resource.state === "ready" || resource.state === "stale" ? resource.envelope.data : null;
}
