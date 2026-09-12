from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.simulation.domain.market import as_decimal
from backend.simulation.domain.orders import Order


@dataclass(frozen=True, slots=True)
class BpsCommissionModel:
    bps: Decimal = Decimal("0")
    minimum: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        object.__setattr__(self, "bps", as_decimal(self.bps, "bps"))
        object.__setattr__(self, "minimum", as_decimal(self.minimum, "minimum"))
        if self.bps < 0 or self.minimum < 0:
            raise ValueError("commission values cannot be negative")

    def calculate(self, order: Order, fill_quantity: Decimal, fill_price: Decimal) -> Decimal:  # noqa: ARG002
        commission = as_decimal(fill_quantity, "fill_quantity") * as_decimal(fill_price, "fill_price") * self.bps / Decimal("10000")
        return max(commission, self.minimum)


@dataclass(frozen=True, slots=True)
class PerShareCommissionModel:
    per_share: Decimal
    minimum: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        object.__setattr__(self, "per_share", as_decimal(self.per_share, "per_share"))
        object.__setattr__(self, "minimum", as_decimal(self.minimum, "minimum"))
        if self.per_share < 0 or self.minimum < 0:
            raise ValueError("commission values cannot be negative")

    def calculate(self, order: Order, fill_quantity: Decimal, fill_price: Decimal) -> Decimal:  # noqa: ARG002
        return max(as_decimal(fill_quantity, "fill_quantity") * self.per_share, self.minimum)
