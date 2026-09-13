from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.market import as_decimal, require_aware


@dataclass(frozen=True, slots=True)
class MarketTick:
    instrument: InstrumentId
    ts: datetime
    price: Decimal
    size: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        require_aware(self.ts, "ts")
        price = as_decimal(self.price, "price")
        if price <= 0:
            raise ValueError("tick price must be positive")
        object.__setattr__(self, "price", price)
        for name in ("size", "bid", "ask"):
            value = getattr(self, name)
            if value is None:
                continue
            decimal_value = as_decimal(value, name)
            if name == "size" and decimal_value < 0:
                raise ValueError("tick size cannot be negative")
            if name != "size" and decimal_value <= 0:
                raise ValueError(f"tick {name} must be positive")
            object.__setattr__(self, name, decimal_value)

