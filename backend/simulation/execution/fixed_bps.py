from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.simulation.domain.enums import OrderSide
from backend.simulation.domain.market import as_decimal


@dataclass(frozen=True, slots=True)
class FixedBpsExecutionModel:
    slippage_bps: Decimal = Decimal("0")
    max_participation: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        object.__setattr__(self, "slippage_bps", as_decimal(self.slippage_bps, "slippage_bps"))
        object.__setattr__(self, "max_participation", as_decimal(self.max_participation, "max_participation"))
        if self.slippage_bps < 0 or not Decimal("0") < self.max_participation <= Decimal("1"):
            raise ValueError("invalid fixed-BPS execution configuration")

    def execution_price(self, base_price: Decimal, side: OrderSide) -> Decimal:
        multiplier = Decimal("1") + (self.slippage_bps / Decimal("10000")) * (
            Decimal("1") if side is OrderSide.BUY else Decimal("-1")
        )
        return as_decimal(base_price, "base_price") * multiplier

    def maximum_quantity(self, volume: Decimal) -> Decimal:
        return as_decimal(volume, "volume") * self.max_participation
