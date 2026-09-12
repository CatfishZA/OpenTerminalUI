from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from backend.simulation.domain.enums import OrderStatus
from backend.simulation.domain.orders import Order

TERMINAL_ORDER_STATUSES = frozenset(
    {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.EXPIRED, OrderStatus.REJECTED}
)
ALLOWED_TRANSITIONS = {
    OrderStatus.CREATED: {OrderStatus.ACCEPTED, OrderStatus.REJECTED, OrderStatus.CANCELLED},
    OrderStatus.ACCEPTED: {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.EXPIRED},
    OrderStatus.PARTIALLY_FILLED: {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.EXPIRED},
}


class OrderManager:
    """Deterministic order lifecycle and shared-cash reservation helper."""

    def transition(
        self, order: Order, status: OrderStatus, *, remaining_quantity: Decimal | None = None
    ) -> Order:
        if status not in ALLOWED_TRANSITIONS.get(order.status, set()):
            raise ValueError(f"invalid order transition: {order.status.value} -> {status.value}")
        remaining = order.remaining_quantity if remaining_quantity is None else remaining_quantity
        if status is OrderStatus.FILLED:
            remaining = Decimal("0")
        completed_at = order.completed_at
        if status in TERMINAL_ORDER_STATUSES:
            completed_at = order.completed_at
        return replace(order, status=status, remaining_quantity=remaining, completed_at=completed_at)

    def accept(self, order: Order, accepted_at: datetime, eligible_at: datetime) -> Order:
        return replace(
            self.transition(order, OrderStatus.ACCEPTED),
            accepted_at=accepted_at,
            eligible_at=eligible_at,
        )

    def complete(self, order: Order, status: OrderStatus, at: datetime) -> Order:
        return replace(self.transition(order, status), completed_at=at)
