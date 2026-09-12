from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.market import as_decimal


@dataclass(frozen=True, slots=True)
class Position:
    instrument: InstrumentId
    quantity: Decimal = Decimal("0")
    average_cost: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    market_value: Decimal = Decimal("0")
    last_mark: Decimal | None = None

    def __post_init__(self) -> None:
        for name in ("quantity", "average_cost", "realized_pnl", "unrealized_pnl", "market_value"):
            object.__setattr__(self, name, as_decimal(getattr(self, name), name))
        if self.average_cost < 0:
            raise ValueError("average cost cannot be negative")
        if self.last_mark is not None:
            object.__setattr__(self, "last_mark", as_decimal(self.last_mark, "last_mark"))
