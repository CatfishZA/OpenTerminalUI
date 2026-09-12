from __future__ import annotations

from dataclasses import replace
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
    """Pure order-state transition helper; matching remains out of Phase 1A."""

    def transition(
        self, order: Order, status: OrderStatus, *, remaining_quantity: Decimal | None = None
    ) -> Order:
        if status not in ALLOWED_TRANSITIONS.get(order.status, set()):
            raise ValueError(f"invalid order transition: {order.status.value} -> {status.value}")
        remaining = order.remaining_quantity if remaining_quantity is None else remaining_quantity
        if status is OrderStatus.FILLED:
            remaining = Decimal("0")
        return replace(order, status=status, remaining_quantity=remaining)
