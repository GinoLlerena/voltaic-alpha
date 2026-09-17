import type { Schemas } from "../api/client";
import { Fact, Matrix, Panel } from "./Panel";

type Lifecycle = Schemas["LifecycleOut"];

/**
 * What the broker acknowledged, and what it did not.
 *
 * An acknowledgement is SUBMITTED, never FILLED: the two are different claims
 * and the product refuses to blur them. Fills are shown as their own rows
 * because a filled quantity without the fills behind it is an assertion.
 */
export function Lifecycle({ lifecycle }: { lifecycle: Lifecycle | null }) {
  const orders = lifecycle?.orders ?? [];
  const positions = lifecycle?.positions ?? [];
  const exits = lifecycle?.exits ?? [];

  return (
    <>
      <Panel
        testId="lifecycle-orders"
        title="What reached the broker"
        source="broker_orders · fills"
        present={orders.length > 0}
        absence="Nothing reached the broker: no order was ever prepared for this decision."
      >
        <Matrix label="Orders sent to the broker">
        <table className="matrix">
          <thead>
            <tr>
              <th scope="col">Role</th>
              <th scope="col">Status</th>
              <th scope="col">Filled</th>
              <th scope="col">Average</th>
              <th scope="col">Submitted</th>
              <th scope="col">Reconciled</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <tr key={order.client_order_id} data-terminal={String(order.terminal)}>
                <td>{order.role}</td>
                <td className="verdict">{order.status}</td>
                <td className="num">
                  {order.filled_quantity ?? "—"} of {order.strategy_quantity ?? "—"}
                  {order.fills.length > 0 ? (
                    <span className="src">{order.fills.length} fill(s)</span>
                  ) : null}
                </td>
                <td className="num">{order.filled_avg_price ?? "—"}</td>
                <td className="num">{order.submitted_at ?? "—"}</td>
                <td className="num">{order.reconciled_at ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </Matrix>
      </Panel>

      <Panel
        testId="lifecycle-position"
        title="Position"
        source="positions"
        present={positions.length > 0}
        absence="No position exists for this decision."
      >
        {positions.map((position) => (
          <dl className="ticket" key={`${position.long_symbol}-${position.short_symbol}`}>
            <Fact label="State" value={<strong>{position.lifecycle_status}</strong>} />
            <Fact label="Structure" value={`${position.strategy} · ${position.direction}`} />
            <Fact label="Legs" value={`${position.long_symbol} / ${position.short_symbol}`} />
            <Fact label="Entry debit" value={position.avg_entry_debit ?? "—"} />
            <Fact label="Open risk" value={position.open_risk ?? "—"} />
            <Fact
              label="Invalidation level"
              value={position.invalidation_level ?? "—"}
              source={position.invalidation_source ?? undefined}
            />
            <Fact label="Closed" value={position.closed_at ?? "still open"} />
          </dl>
        ))}
      </Panel>

      <Panel
        testId="lifecycle-exits"
        title="Exit decisions"
        source="exit_decisions"
        present={exits.length > 0}
        absence="No exit decision has been recorded for this decision."
      >
        <ul className="chk">
          {exits.map((exit, index) => (
            <li key={exit.trigger + String(index)} data-close={String(exit.should_close)}>
              <span className="m">{exit.trigger}</span>
              <span className="prose">{exit.reason}</span>
              <span className="src">
                {exit.should_close ? "close" : "hold"}
                {exit.value_unmeasurable ? " · value unmeasurable" : ""}
                {exit.invalidation_unverifiable ? " · invalidation unverifiable" : ""}
              </span>
            </li>
          ))}
        </ul>
      </Panel>
    </>
  );
}
