from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from backend.simulation.domain.market import as_decimal


@dataclass(frozen=True, slots=True)
class ImpactCurveExecutionModel:
    coefficient_bps: Decimal
    exponent: Decimal = Decimal("0.5")
    max_participation: Decimal = Decimal("0.1")

    def __post_init__(self) -> None:
        for name in ("coefficient_bps", "exponent", "max_participation"):
            object.__setattr__(self, name, as_decimal(getattr(self, name), name))
        if self.coefficient_bps < 0 or self.exponent <= 0 or not Decimal("0") < self.max_participation <= Decimal("1"):
            raise ValueError("invalid impact curve configuration")

    def impact_bps(self, quantity: Decimal, bar_volume: Decimal) -> Decimal:
        volume = as_decimal(bar_volume, "bar_volume")
        if volume <= 0:
            return self.coefficient_bps
        participation = min(as_decimal(quantity, "quantity") / volume, self.max_participation)
        with localcontext() as context:
            context.prec = 38
            return self.coefficient_bps * (participation ** self.exponent)
