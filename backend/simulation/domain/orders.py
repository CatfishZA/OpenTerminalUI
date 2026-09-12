from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.simulation.domain.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.market import as_decimal, require_aware


@dataclass(frozen=True, slots=True)
class Order:
    id: str
    run_id: str
    account_id: str
    instrument: InstrumentId
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    remaining_quantity: Decimal
    tif: TimeInForce
    submitted_at: datetime
    accepted_at: datetime | None = None
    eligible_at: datetime | None = None
    completed_at: datetime | None = None
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    status: OrderStatus = OrderStatus.CREATED
    strategy_order_id: str | None = None
    parent_order_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        quantity = as_decimal(self.quantity, "quantity")
        remaining = as_decimal(self.remaining_quantity, "remaining_quantity")
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "remaining_quantity", remaining)
        require_aware(self.submitted_at, "submitted_at")
        if self.accepted_at is not None:
            require_aware(self.accepted_at, "accepted_at")
            if self.accepted_at < self.submitted_at:
                raise ValueError("accepted_at cannot precede submitted_at")
        if self.eligible_at is not None:
            require_aware(self.eligible_at, "eligible_at")
            if self.eligible_at < self.submitted_at:
                raise ValueError("eligible_at cannot precede submitted_at")
        if self.completed_at is not None:
            require_aware(self.completed_at, "completed_at")
        if quantity <= 0 or remaining < 0 or remaining > quantity:
            raise ValueError("order quantity/remaining quantity is invalid")
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit orders require limit_price")
        if self.order_type is OrderType.STOP and self.stop_price is None:
            raise ValueError("stop orders require stop_price")
        if self.limit_price is not None:
            price = as_decimal(self.limit_price, "limit_price")
            if price <= 0:
                raise ValueError("limit_price must be positive")
            object.__setattr__(self, "limit_price", price)
        if self.stop_price is not None:
            price = as_decimal(self.stop_price, "stop_price")
            if price <= 0:
                raise ValueError("stop_price must be positive")
            object.__setattr__(self, "stop_price", price)
