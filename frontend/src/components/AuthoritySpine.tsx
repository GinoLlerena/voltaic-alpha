/**
 * The seven stages, with the one the model touches marked.
 *
 * The dashboard's signature argument, carried over: the model occupies exactly
 * one fenced box in the pipeline, and it is visible on every screen rather than
 * described once. `reached` comes from the decision's own records.
 */
const STAGES = [
  { key: "01", label: "Evidence", model: false },
  { key: "02", label: "Setup", model: false },
  { key: "03", label: "Memo", model: true },
  { key: "04", label: "Risk", model: false },
  { key: "05", label: "Intent", model: false },
  { key: "06", label: "Request", model: false },
  { key: "07", label: "Broker", model: false },
] as const;

export function AuthoritySpine({
  modelWasCalled,
  reachedTheBroker,
}: {
  modelWasCalled: boolean;
  reachedTheBroker: boolean;
}) {
  const lit = (key: string) => {
    if (key === "03") return modelWasCalled;
    if (key >= "05") return reachedTheBroker;
    return true;
  };
  return (
    <ol className="spine" data-testid="authority-spine">
      {STAGES.map((stage) => (
        <li
          key={stage.key}
          className={[stage.model ? "model" : "code", lit(stage.key) ? "on" : "off"].join(" ")}
          data-stage={stage.key}
          data-lit={String(lit(stage.key))}
        >
          <span className="n">{stage.key}</span>
          <span className="l">{stage.label}</span>
        </li>
      ))}
      <li className="fence" aria-hidden="true">
        the model may only write the memo
      </li>
    </ol>
  );
}
