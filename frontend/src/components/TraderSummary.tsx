import type { Schemas } from "../api/client";

type Market = Schemas["MarketOut"];
type Memo = Schemas["MemoOut"];
type Structure = Schemas["StructureOut"];
type Risk = Schemas["RiskOut"];

/**
 * The five questions, answered in one line each.
 *
 * `RUI-4`'s exit is that a trader answers why direction, why now, why
 * structure, max loss and invalidation in thirty seconds. The panels below
 * hold the evidence for each, but they are several screens long, and a reader
 * who has to scroll to learn the maximum loss has not answered it in thirty
 * seconds. Each row links to the panel it summarises, so the short answer and
 * the long one are the same answer.
 *
 * Nothing here is computed. Every value is selected from a record, and an
 * unanswerable question says so rather than being omitted — a missing row
 * would read as though the question did not apply.
 */
export function TraderSummary({
  market,
  memo,
  structure,
  risk,
}: {
  market: Market | null;
  memo: Memo | null;
  structure: Structure | null;
  risk: Risk | null;
}) {
  const qualification = market?.qualification ?? null;
  const selected = structure?.selected ?? null;
  const accounting = risk?.accounting ?? null;
  const conditions = qualification?.invalidation_conditions ?? [];
  const cited = (market?.signals ?? []).filter((signal) => signal.role === "cited");

  const answers = [
    {
      question: "Why this direction",
      target: "qualification",
      answer: qualification
        ? `${qualification.direction}, by ${qualification.classifier_name}`
        : null,
      note: memo?.produced === true ? "memo agrees, advisory only" : "no model was called",
    },
    {
      question: "Why now",
      target: "signals",
      answer:
        cited.length > 0
          ? `${cited.length} signal(s) cited${
              market?.observation?.underlying_price
                ? ` at ${market.observation.underlying_price}`
                : ""
            }`
          : null,
      note: market?.observation?.source_time ?? "no observation recorded",
    },
    {
      question: "Why this structure",
      target: "structure-selected",
      answer: selected
        ? `${selected.strategy} ×${selected.quantity}, debit ${selected.estimated_debit ?? "—"}`
        : null,
      note: selected ? `${selected.long_contract_symbol} / ${selected.short_contract_symbol}` : "",
    },
    {
      question: "What it could lose",
      target: "risk-accounting",
      answer: accounting?.maximum_loss
        ? `${accounting.maximum_loss} of ${accounting.risk_budget ?? "—"}`
        : null,
      note: accounting?.budget_used_percent ? `${accounting.budget_used_percent}% of budget` : "",
    },
    {
      question: "What would invalidate it",
      target: "invalidation",
      answer: conditions[0] ?? null,
      note: conditions.length > 1 ? `and ${conditions.length - 1} more` : "",
    },
  ];

  return (
    <section data-testid="trader-summary">
      <h3>The five questions</h3>
      <dl className="five">
        {answers.map((row) => (
          <div key={row.question} data-answered={String(row.answer !== null)}>
            <dt>
              <a href={`#${row.target}`}>{row.question}</a>
            </dt>
            <dd>
              {row.answer === null ? (
                <span className="t na">not answerable from this decision&apos;s records</span>
              ) : (
                <span className="a">{row.answer}</span>
              )}
              {row.note ? <span className="src">{row.note}</span> : null}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
