import type { Schemas } from "../api/client";
import { api } from "../api/client";
import { Fact, Panel } from "./Panel";

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

/**
 * The manifest's own disclosures, read rather than restated.
 *
 * They are the server's sentences about what this evidence is and is not — that
 * the account is Paper, that quotes are indicative, that no alpha is claimed.
 * Paraphrasing them here would put a second, unversioned copy of the product's
 * most careful language in the browser.
 */
function disclosures(manifest: Record<string, unknown> | undefined): string[] {
  const value = manifest?.["disclosures"];
  if (!Array.isArray(value)) return [];
  return value.filter((line): line is string => typeof line === "string");
}

export function ProofLineage({
  digest,
  lifecycle,
  proof,
}: {
  digest: string;
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

      <Panel
        testId="proof-export"
        title="Take the evidence with you"
        source="the committed manifest"
        present={proof !== null}
        absence="No proof manifest exists for this decision, so there is nothing to export."
      >
        {proof ? (
          <>
            <dl className="ticket">
              <Fact
                label="Download"
                value={
                  <a href={api.proofExport(digest)} download data-testid="proof-download">
                    proof-{digest.slice(0, 16)}.json
                  </a>
                }
                source="served by the API, not assembled here"
              />
              <Fact
                label="Manifest digest"
                value={<span className="hash">{proof.manifest_digest}</span>}
                // The digest is over the bytes the API serves, so the file a
                // reader downloads hashes to exactly this. Saying how to check
                // is the difference between a verifiable claim and decoration.
                source="shasum -a 256 of the downloaded file"
              />
              <Fact
                label="Version"
                value={String(proof.manifest["manifest_version"] ?? "unversioned")}
              />
            </dl>
            {disclosures(proof.manifest).length > 0 ? (
              <ul className="plain disclosures">
                {disclosures(proof.manifest).map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            ) : null}
          </>
        ) : null}
      </Panel>
    </>
  );
}
