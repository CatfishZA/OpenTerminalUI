from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from backend.simulation.domain.enums import OrderSide, OrderType, TimeInForce
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.market import as_decimal, require_aware


@dataclass(frozen=True, slots=True)
class StrategyIntent:
    instrument: InstrumentId
    side: OrderSide
    quantity: Decimal
    created_at: datetime
    order_type: OrderType = OrderType.MARKET
    tif: TimeInForce = TimeInForce.DAY
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_aware(self.created_at, "created_at")
        object.__setattr__(self, "quantity", as_decimal(self.quantity, "quantity"))
        if self.quantity <= 0:
            raise ValueError("intent quantity must be positive")


class MarketReadModel(Protocol):
    def history(self, instrument: InstrumentId, *, limit: int) -> tuple[Any, ...]: ...


class OrderApi(Protocol):
    def submit(self, intent: StrategyIntent) -> None: ...

    def cancel(self, order_id: str) -> None: ...


@dataclass(frozen=True, slots=True)
class StrategyContext:
    now: datetime
    account: Any
    positions: Any
    cash: Any
    market: MarketReadModel
    orders: OrderApi

    def __post_init__(self) -> None:
        require_aware(self.now, "now")
