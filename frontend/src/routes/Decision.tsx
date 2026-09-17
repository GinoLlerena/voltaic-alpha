import { Link } from "@tanstack/react-router";
import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { useResource } from "../api/useResource";
import { DecisionTicket } from "../components/DecisionTicket";
import { SourceBanner } from "../components/SourceBanner";

type Summary = Schemas["DecisionSummary"];
type Market = Schemas["MarketOut"];
type Horizons = Schemas["DecisionHorizonOut"][];

/** One decision, addressable by its hash so the link is the evidence. */
export function Decision({ digest }: { digest: string }) {
  const summary = useResource<Summary>(api.summary(digest));
  const market = useResource<Market>(api.market(digest));
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
        market={
          market.state === "ready" || market.state === "stale" ? market.envelope.data : null
        }
        horizons={
          horizons.state === "ready" || horizons.state === "stale"
            ? horizons.envelope.data
            : []
        }
      />
    </>
  );
}
