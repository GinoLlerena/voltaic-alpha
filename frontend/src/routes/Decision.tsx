import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { useResource } from "../api/useResource";
import { AuthoritySpine } from "../components/AuthoritySpine";
import {
  DecisionTicket,
  Horizons,
  Identifiers,
  SetupReading,
  WhyDecision,
} from "../components/DecisionTicket";
import { Evidence } from "../components/Evidence";
import { Invalidation } from "../components/Invalidation";
import { Lifecycle } from "../components/Lifecycle";
import { ModelMemo, Qualification } from "../components/Memo";
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
 *
 * `PUI-007`: a concise summary, then three named sections - Setup & risk,
 * Execution, Evidence - each reachable from a section list, instead of a dozen
 * panels in one column. Every panel is still on the page, and its warnings
 * still show; only the order changed.
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
        <Link to="/decisions">Back to the decisions</Link>
      </p>
    ) : (
      <p role="alert" className="failed" data-testid="decision-unavailable">
        This decision could not be loaded ({summary.reason}). That is a failed request, not a
        missing record.{" "}
        <button type="button" onClick={summary.retry}>
          Retry
        </button>{" "}
        <Link to="/decisions">Back to the decisions</Link>
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

  const source = { id: summary.envelope.source_id, label: summary.envelope.source_label };
  const data = summary.envelope.data;
  return (
    <>
      <SourceBanner
        envelope={summary.envelope}
        stale={summary.stale}
        {...(summary.state === "stale" ? { reason: summary.reason } : {})}
      />
      <p>
        <Link to="/decisions">← Decisions</Link>
      </p>
      <DecisionTicket summary={data} market={market} />
      <Loaded
        what="decision summary"
        resources={{ market, memo, structure, risk }}
        expectedSource={source}
      >
        {(d) => <TraderSummary market={d.market} memo={d.memo} structure={d.structure} risk={d.risk} />}
      </Loaded>

      <nav className="sections" aria-label="Decision sections">
        <a href="#setup">Setup &amp; risk</a>
        <a href="#execution">Execution</a>
        <a href="#evidence">Evidence</a>
      </nav>

      <Part id="setup" title="Setup & risk">
        <SetupReading summary={data} market={market} />
        <Loaded what="qualification" resources={{ market }} expectedSource={source}>
          {(d) => <Qualification market={d.market} />}
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
      </Part>

      <Part id="execution" title="Execution">
        <p className="note">
          Intent, broker acceptance, fills, reconciliation and exits are separate records; one
          present does not imply the next.
        </p>
        <Loaded what="lifecycle" resources={{ lifecycle }} expectedSource={source}>
          {(d) => <Lifecycle lifecycle={d.lifecycle} />}
        </Loaded>
      </Part>

      <Part id="evidence" title="Evidence">
        <AuthoritySpine
          modelWasCalled={data.model_was_called}
          reachedTheBroker={data.reached_the_broker}
        />
        <WhyDecision summary={data} />
        <Loaded what="model memo" resources={{ memo }} expectedSource={source}>
          {(d) => <ModelMemo memo={d.memo} />}
        </Loaded>
        <Horizons horizons={horizons} />
        <Loaded what="proof lineage" resources={{ lifecycle, proof }} expectedSource={source}>
          {(d) => <ProofLineage digest={digest} lifecycle={d.lifecycle} proof={d.proof} />}
        </Loaded>
        <Identifiers summary={data} />
      </Part>
    </>
  );
}

/** A named, linkable section of the decision page. */
function Part({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="part" aria-labelledby={`${id}-heading`} data-testid={`part-${id}`}>
      <h2 id={`${id}-heading`}>{title}</h2>
      {children}
    </section>
  );
}
