"""Durable order and position lifecycle.

Addresses `EXIT-001` and `EXIT-002`. The rule this module exists to enforce:

    **Broker acknowledgement is `SUBMITTED`, never `FILLED`.**

Nothing here may create an `OPEN` position from a submission response. Only
reconciled fills establish a filled quantity and an actual entry debit, and only
a reconciled flat broker position releases close responsibility.

Every broker mutation is bracketed: state is written *before* the request is
sent, so a crash between send and response leaves a durable record that
something may be in flight, and written again *after* the response. A process
that dies mid-submit must be recoverable by reading the database, not by hoping.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from ..architecture.contracts import Direction, ExecutionState
from ..persistence.models import (
    BrokerOrder,
    Fill,
    Incident,
    Position,
    PreparedOrderRequest,
)
from ..persistence.models import (
    OrderIntent as OrderIntentRow,
)
from .intent import OrderIntent
from .request import PreparedRequest


class OrderState(str, Enum):  # noqa: UP042 - matches the str-Enum style used project-wide
    """Our view of an order. Distinct from the broker's `status` string."""

    PREPARED = "PREPARED"          # persisted, not yet sent
    SUBMITTED = "SUBMITTED"        # sent; outcome unknown
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    AMBIGUOUS = "AMBIGUOUS"        # sent, response lost; must be reconciled

    @property
    def is_terminal(self) -> bool:
        return self in {
            OrderState.FILLED,
            OrderState.CANCELED,
            OrderState.REJECTED,
            OrderState.EXPIRED,
        }


class PositionState(str, Enum):  # noqa: UP042 - matches the str-Enum style used project-wide
    PENDING = "PENDING"        # entry submitted, no confirmed fill
    OPEN = "OPEN"              # reconciled fills establish exposure
    CLOSING = "CLOSING"        # close submitted, not yet confirmed flat
    CLOSED = "CLOSED"          # broker confirms flat
    ABANDONED = "ABANDONED"    # entry terminated without a fill; no exposure
    INCIDENT = "INCIDENT"      # local and broker disagree


#: Broker status strings mapped to our states. Unknown strings are not guessed.
BROKER_STATUS_MAP: dict[str, OrderState] = {
    "new": OrderState.SUBMITTED,
    "accepted": OrderState.SUBMITTED,
    "pending_new": OrderState.SUBMITTED,
    "accepted_for_bidding": OrderState.SUBMITTED,
    "held": OrderState.SUBMITTED,
    "partially_filled": OrderState.PARTIALLY_FILLED,
    "filled": OrderState.FILLED,
    "canceled": OrderState.CANCELED,
    "cancelled": OrderState.CANCELED,
    "pending_cancel": OrderState.SUBMITTED,
    "rejected": OrderState.REJECTED,
    "expired": OrderState.EXPIRED,
    "done_for_day": OrderState.EXPIRED,
    "suspended": OrderState.SUBMITTED,
    "stopped": OrderState.SUBMITTED,
}


def map_broker_status(raw: str | None) -> OrderState:
    """Map a broker status. An unrecognised status is ambiguous, never assumed."""
    if not raw:
        return OrderState.AMBIGUOUS
    key = str(raw).lower().rsplit(".", 1)[-1].strip()
    return BROKER_STATUS_MAP.get(key, OrderState.AMBIGUOUS)


@dataclass(frozen=True)
class TypedInvalidation:
    """A structural invalidation rule, stored rather than parsed from prose."""

    level: Decimal
    direction: Direction
    source: str

    def breached(self, price: Decimal) -> bool:
        if self.direction is Direction.BULLISH:
            return price <= self.level
        return price >= self.level


@dataclass(frozen=True)
class IncidentRecord:
    """A detached view of an incident.

    Returning ORM instances outside their session raises DetachedInstanceError on
    first attribute access, which turns a diagnostic call into a crash.
    """

    incident_id: str
    kind: str
    severity: str
    detail: str
    execution_state: str
    position_id: str | None
    opened_at: datetime


@dataclass(frozen=True)
class ManagedPosition:
    """A position reconstructed from durable records, not from process memory."""

    position_id: str
    decision_id: str
    entry_order_id: str
    state: PositionState
    direction: Direction
    strategy: str
    long_symbol: str
    short_symbol: str
    expiration: datetime
    width: Decimal
    requested_quantity: int
    filled_quantity: int
    avg_entry_debit: Decimal | None
    invalidation: TypedInvalidation | None
    entry_filled_at: datetime | None
    close_order_id: str | None

    @property
    def has_confirmed_exposure(self) -> bool:
        return self.state in {PositionState.OPEN, PositionState.CLOSING} and (
            self.filled_quantity > 0
        )


def _new_id() -> str:
    return uuid.uuid4().hex


class LifecycleStore:
    """Durable lifecycle writes. The only component allowed to change these rows."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._session_factory = sessionmaker(bind=engine, future=True)

    @contextmanager
    def _session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # -- before a mutation -------------------------------------------------
    def prepare_entry(
        self,
        *,
        decision_id: str,
        intent: OrderIntent,
        request: PreparedRequest,
        direction: Direction,
        long_symbol: str,
        short_symbol: str,
        expiration: datetime,
        width: Decimal,
        max_loss: Decimal,
        invalidation: TypedInvalidation | None,
        deadline_at: datetime | None = None,
        now: datetime | None = None,
    ) -> tuple[str, str]:
        """Persist intent, request, order, and a PENDING position **before** sending.

        Returns ``(order_id, position_id)``. The position is `PENDING`: it records
        that something may be in flight, and asserts no exposure.
        """
        stamp = now or datetime.now(UTC)
        intent_id, order_id, position_id = _new_id(), _new_id(), _new_id()

        with self._session() as session:
            session.add(
                OrderIntentRow(
                    id=intent_id,
                    decision_id=decision_id,
                    intent_hash=intent.intent_hash,
                    client_order_id=intent.client_order_id,
                    legs=[
                        {
                            "symbol": leg.symbol,
                            "ratio_qty": leg.ratio_qty,
                            "side": leg.side,
                            "position_intent": leg.position_intent,
                        }
                        for leg in intent.legs
                    ],
                    desired_limit_price=intent.limit_price,
                    approval_reference=intent.approval_reference,
                    expires_at=intent.expires_at,
                )
            )
            session.flush()
            session.add(
                PreparedOrderRequest(
                    id=_new_id(),
                    order_intent_id=intent_id,
                    adapter_version=request.adapter_version,
                    request_schema_version=request.request_schema_version,
                    serialized_request=request.body,
                    request_hash=request.request_hash,
                    intent_hash_match=request.matches(intent),
                    dry_run_result="prepared",
                    prepared_at=request.prepared_at,
                    expires_at=request.expires_at,
                )
            )
            session.add(
                BrokerOrder(
                    id=order_id,
                    order_intent_id=intent_id,
                    broker_order_id=None,
                    client_order_id=intent.client_order_id,
                    role="entry",
                    status="not_sent",
                    local_state=OrderState.PREPARED.value,
                    terminal=False,
                    strategy_quantity=intent.strategy_quantity,
                    filled_quantity=0,
                    prepared_at=stamp,
                    deadline_at=deadline_at,
                )
            )
            session.flush()
            session.add(
                Position(
                    id=position_id,
                    decision_id=decision_id,
                    entry_order_id=order_id,
                    strategy=intent.strategy.value,
                    direction=direction.value,
                    lifecycle_status=PositionState.PENDING.value,
                    long_symbol=long_symbol,
                    short_symbol=short_symbol,
                    expiration=expiration,
                    width=width,
                    requested_quantity=intent.strategy_quantity,
                    filled_quantity=0,
                    avg_entry_debit=None,
                    open_risk=max_loss,
                    invalidation_level=invalidation.level if invalidation else None,
                    invalidation_direction=(
                        invalidation.direction.value if invalidation else None
                    ),
                    invalidation_source=invalidation.source if invalidation else None,
                )
            )
        return order_id, position_id

    def prepare_close(
        self,
        *,
        position_id: str,
        decision_id: str,
        intent: OrderIntent,
        request: PreparedRequest,
        reason: str,
        deadline_at: datetime | None = None,
        now: datetime | None = None,
    ) -> str:
        """Persist the close intent and order **before** sending. Returns order id."""
        stamp = now or datetime.now(UTC)
        intent_id, order_id = _new_id(), _new_id()
        with self._session() as session:
            session.add(
                OrderIntentRow(
                    id=intent_id,
                    decision_id=decision_id,
                    intent_hash=intent.intent_hash,
                    client_order_id=intent.client_order_id,
                    legs=[
                        {
                            "symbol": leg.symbol,
                            "ratio_qty": leg.ratio_qty,
                            "side": leg.side,
                            "position_intent": leg.position_intent,
                        }
                        for leg in intent.legs
                    ],
                    desired_limit_price=intent.limit_price,
                    approval_reference=intent.approval_reference,
                    expires_at=intent.expires_at,
                )
            )
            session.flush()
            session.add(
                PreparedOrderRequest(
                    id=_new_id(),
                    order_intent_id=intent_id,
                    adapter_version=request.adapter_version,
                    request_schema_version=request.request_schema_version,
                    serialized_request=request.body,
                    request_hash=request.request_hash,
                    intent_hash_match=request.matches(intent),
                    dry_run_result="prepared",
                    prepared_at=request.prepared_at,
                    expires_at=request.expires_at,
                )
            )
            session.add(
                BrokerOrder(
                    id=order_id,
                    order_intent_id=intent_id,
                    broker_order_id=None,
                    client_order_id=intent.client_order_id,
                    role="close",
                    status="not_sent",
                    local_state=OrderState.PREPARED.value,
                    terminal=False,
                    strategy_quantity=intent.strategy_quantity,
                    filled_quantity=0,
                    prepared_at=stamp,
                    deadline_at=deadline_at,
                )
            )
            session.flush()
            position = session.get(Position, position_id)
            if position is not None:
                position.close_order_id = order_id
                position.lifecycle_status = PositionState.CLOSING.value
                position.close_reason = reason
        return order_id

    # -- after a mutation --------------------------------------------------
    def record_submission(
        self,
        order_id: str,
        *,
        broker_order_id: str | None,
        broker_status: str | None,
        ambiguous: bool = False,
        error: str | None = None,
        now: datetime | None = None,
    ) -> OrderState:
        """Record the broker's response. Acceptance is SUBMITTED, never FILLED."""
        stamp = now or datetime.now(UTC)
        state = OrderState.AMBIGUOUS if ambiguous else map_broker_status(broker_status)
        # A submission response never establishes a fill, whatever it claims.
        if state in {OrderState.FILLED, OrderState.PARTIALLY_FILLED}:
            state = OrderState.SUBMITTED
        with self._session() as session:
            order = session.get(BrokerOrder, order_id)
            if order is None:
                raise LookupError(f"broker order {order_id} not found")
            order.broker_order_id = broker_order_id
            order.status = str(broker_status or ("ambiguous" if ambiguous else "unknown"))
            order.local_state = state.value
            order.submitted_at = stamp
            order.last_error = error
        return state

    def apply_order_reconciliation(
        self,
        order_id: str,
        *,
        broker_status: str | None,
        filled_quantity: int,
        filled_avg_price: Decimal | None,
        legs: Sequence[dict[str, Any]] = (),
        now: datetime | None = None,
    ) -> OrderState:
        """Apply an authoritative order read. This is the only path that creates fills."""
        stamp = now or datetime.now(UTC)
        state = map_broker_status(broker_status)
        if state is OrderState.SUBMITTED and filled_quantity > 0:
            state = OrderState.PARTIALLY_FILLED

        with self._session() as session:
            order = session.get(BrokerOrder, order_id)
            if order is None:
                raise LookupError(f"broker order {order_id} not found")
            order.status = str(broker_status or "unknown")
            order.local_state = state.value
            order.filled_quantity = filled_quantity
            order.filled_avg_price = filled_avg_price
            order.terminal = state.is_terminal
            order.reconciled_at = stamp

            # Normalized keys: the database returns Decimal("6.900000") where the
            # provider sends "6.90". Comparing their str() forms silently
            # duplicates every fill on each reconciliation pass.
            def key_of(symbol: Any, quantity: Any, price: Any) -> tuple[str, int, Decimal]:
                return (str(symbol), int(quantity), Decimal(str(price)).normalize())

            existing = {
                key_of(f.leg_symbol, f.quantity, f.price)
                for f in session.scalars(
                    select(Fill).where(Fill.broker_order_id == order_id)
                ).all()
            }
            for leg in legs:
                key = key_of(leg["symbol"], leg["quantity"], leg["price"])
                if key in existing:
                    continue  # idempotent: reconciliation may run repeatedly
                existing.add(key)
                session.add(
                    Fill(
                        id=_new_id(),
                        broker_order_id=order_id,
                        leg_symbol=str(leg["symbol"]),
                        quantity=int(leg["quantity"]),
                        price=Decimal(str(leg["price"])),
                        filled_at=leg.get("filled_at") or stamp,
                    )
                )
        return state

    def apply_entry_outcome(
        self, position_id: str, *, state: OrderState, filled_quantity: int,
        avg_debit: Decimal | None, now: datetime | None = None,
    ) -> PositionState:
        """Move a PENDING position based on the reconciled entry order."""
        stamp = now or datetime.now(UTC)
        with self._session() as session:
            position = session.get(Position, position_id)
            if position is None:
                raise LookupError(f"position {position_id} not found")

            if filled_quantity > 0:
                # Only here does exposure become real, and only with an actual debit.
                position.filled_quantity = filled_quantity
                position.avg_entry_debit = avg_debit
                position.entry_filled_at = position.entry_filled_at or stamp
                position.opened_at = position.opened_at or stamp
                position.lifecycle_status = PositionState.OPEN.value
            elif state.is_terminal:
                # Canceled, rejected, expired, or filled-zero: no exposure was created.
                position.lifecycle_status = PositionState.ABANDONED.value
                position.closed_at = stamp
                position.close_reason = f"entry_{state.value.lower()}_without_fill"
            else:
                position.lifecycle_status = PositionState.PENDING.value
            result = PositionState(position.lifecycle_status)
        return result

    def apply_close_outcome(
        self, position_id: str, *, broker_flat: bool, remaining_quantity: int,
        now: datetime | None = None,
    ) -> PositionState:
        """Release responsibility only when the broker confirms flat (`EXIT-001`)."""
        stamp = now or datetime.now(UTC)
        with self._session() as session:
            position = session.get(Position, position_id)
            if position is None:
                raise LookupError(f"position {position_id} not found")
            if broker_flat and remaining_quantity == 0:
                position.lifecycle_status = PositionState.CLOSED.value
                position.closed_at = stamp
                position.filled_quantity = 0
            else:
                # A submitted close is not a closed position.
                position.filled_quantity = remaining_quantity
                position.lifecycle_status = PositionState.CLOSING.value
            result = PositionState(position.lifecycle_status)
        return result

    # -- reads -------------------------------------------------------------
    def active_positions(self) -> list[ManagedPosition]:
        """Everything still owed management, reconstructed from the database."""
        with self._session() as session:
            rows = session.scalars(
                select(Position).where(
                    Position.lifecycle_status.in_(
                        [
                            PositionState.PENDING.value,
                            PositionState.OPEN.value,
                            PositionState.CLOSING.value,
                            PositionState.INCIDENT.value,
                        ]
                    )
                )
            ).all()
            return [self._to_managed(row) for row in rows]

    def get_position(self, position_id: str) -> ManagedPosition | None:
        with self._session() as session:
            row = session.get(Position, position_id)
            return self._to_managed(row) if row is not None else None

    def client_order_id_for(self, order_id: str) -> str | None:
        """The deterministic id an order was submitted under, for broker lookup."""
        with self._session() as session:
            order = session.get(BrokerOrder, order_id)
            return order.client_order_id if order is not None else None

    def order_state(self, order_id: str) -> tuple[OrderState, int, Decimal | None]:
        with self._session() as session:
            order = session.get(BrokerOrder, order_id)
            if order is None:
                raise LookupError(f"broker order {order_id} not found")
            return (
                OrderState(order.local_state),
                order.filled_quantity,
                Decimal(str(order.filled_avg_price))
                if order.filled_avg_price is not None
                else None,
            )

    @staticmethod
    def _to_managed(row: Position) -> ManagedPosition:
        invalidation = None
        if row.invalidation_level is not None and row.invalidation_direction:
            invalidation = TypedInvalidation(
                level=Decimal(str(row.invalidation_level)),
                direction=Direction(row.invalidation_direction),
                source=row.invalidation_source or "unspecified",
            )
        return ManagedPosition(
            position_id=row.id,
            decision_id=row.decision_id,
            entry_order_id=row.entry_order_id,
            state=PositionState(row.lifecycle_status),
            direction=Direction(row.direction),
            strategy=row.strategy,
            long_symbol=row.long_symbol,
            short_symbol=row.short_symbol,
            expiration=row.expiration,
            width=Decimal(str(row.width)),
            requested_quantity=row.requested_quantity,
            filled_quantity=row.filled_quantity,
            avg_entry_debit=(
                Decimal(str(row.avg_entry_debit)) if row.avg_entry_debit is not None else None
            ),
            invalidation=invalidation,
            entry_filled_at=row.entry_filled_at,
            close_order_id=row.close_order_id,
        )

    # -- incidents ---------------------------------------------------------
    def open_incident(
        self, *, kind: str, detail: str, severity: str = "high",
        execution_state: ExecutionState = ExecutionState.NO_NEW_RISK,
        position_id: str | None = None, run_id: str | None = None,
        now: datetime | None = None,
    ) -> str:
        """Record a durable incident. A console line is not an incident."""
        incident_id = _new_id()
        with self._session() as session:
            session.add(
                Incident(
                    id=incident_id,
                    run_id=run_id,
                    position_id=position_id,
                    kind=kind,
                    severity=severity,
                    detail=detail,
                    execution_state=execution_state.value,
                    opened_at=now or datetime.now(UTC),
                )
            )
            if position_id is not None:
                position = session.get(Position, position_id)
                if position is not None and position.lifecycle_status not in {
                    PositionState.CLOSED.value,
                    PositionState.ABANDONED.value,
                }:
                    position.lifecycle_status = PositionState.INCIDENT.value
        return incident_id

    def open_incidents(self) -> list[IncidentRecord]:
        with self._session() as session:
            return [
                IncidentRecord(
                    incident_id=row.id,
                    kind=row.kind,
                    severity=row.severity,
                    detail=row.detail,
                    execution_state=row.execution_state,
                    position_id=row.position_id,
                    opened_at=row.opened_at,
                )
                for row in session.scalars(
                    select(Incident).where(Incident.resolved_at.is_(None))
                ).all()
            ]
