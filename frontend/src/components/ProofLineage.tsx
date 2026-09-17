import type { Schemas } from "../api/client";
import { Panel } from "./Panel";

type Lifecycle = Schemas["LifecycleOut"];
type Proof = Schemas["ProofOut"];
type Artifact = Schemas["ArtifactOut"];

/**
 * Whether the artifacts on this page are this decision's.
 *
 * `RUI-4`'s exit requires selected-decision isolation to hold throughout, and
 * the server already answers it per artifact: `relation` and `belongs` say
 * whether a committed file describes this decision, another one, or nothing
 * decision-scoped. Showing an artifact without that answer is how a page ends
 * up illustrating one decision with another's evidence.
 */
function Lineage({ label, artifact }: { label: string; artifact: Artifact }) {
  return (
    <li data-belongs={String(artifact.belongs)} data-relation={artifact.relation}>
      <span className="m">{label}</span>
      <span className="prose">{artifact.reason}</span>
      <span className="src">
        {artifact.relation}
        {artifact.matched_on ? ` · matched on ${artifact.matched_on}` : ""}
      </span>
    </li>
  );
}

export function ProofLineage({
  lifecycle,
  proof,
}: {
  lifecycle: Lifecycle | null;
  proof: Proof | null;
}) {
  const artifacts = lifecycle
    ? ([
        { label: "Paper receipt", artifact: lifecycle.receipt },
        { label: "Ablation", artifact: lifecycle.ablation },
      ] as const)
    : [];
  const trail = lifecycle?.trail ?? null;

  return (
    <>
      <Panel
        testId="proof-lineage"
        title="Does this evidence belong to this decision?"
        source="artifacts · decision hash"
        present={artifacts.length > 0}
        absence="No committed artifact is associated with this decision."
      >
        <ul className="chk">
          {artifacts.map((entry) => (
            <Lineage key={entry.label} label={entry.label} artifact={entry.artifact} />
          ))}
        </ul>
      </Panel>

      <Panel
        testId="proof-trail"
        title="Event trail"
        source="worker_events"
        present={trail !== null}
        absence="No event trail is recorded for this decision."
      >
        {trail ? (
          <p className="gate">
            <strong>{trail.complete ? "Complete" : "Incomplete"}</strong> — {trail.events.length} event(s)
            {trail.gaps.length > 0 ? `, gaps at ${trail.gaps.join(", ")}` : ", no gaps"}
            <span className="src">
              {proof ? `manifest ${proof.manifest_digest}` : "no manifest recorded"}
            </span>
          </p>
        ) : null}
      </Panel>
    </>
  );
}
