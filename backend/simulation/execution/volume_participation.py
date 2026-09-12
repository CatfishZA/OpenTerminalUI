from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.simulation.domain.market import as_decimal


@dataclass(frozen=True, slots=True)
class VolumeParticipationExecutionModel:
    max_participation: Decimal
    base_slippage_bps: Decimal = Decimal("0")
    volume_weighted_bps: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        for name in ("max_participation", "base_slippage_bps", "volume_weighted_bps"):
            object.__setattr__(self, name, as_decimal(getattr(self, name), name))
        if not Decimal("0") < self.max_participation <= Decimal("1"):
            raise ValueError("max_participation must be in (0, 1]")
        if self.base_slippage_bps < 0 or self.volume_weighted_bps < 0:
            raise ValueError("slippage values cannot be negative")

    def maximum_quantity(self, bar_volume: Decimal) -> Decimal:
        return as_decimal(bar_volume, "bar_volume") * self.max_participation

    def slippage_for(self, quantity: Decimal, bar_volume: Decimal) -> Decimal:
        volume = as_decimal(bar_volume, "bar_volume")
        if volume <= 0:
            return self.base_slippage_bps
        participation = min(as_decimal(quantity, "quantity") / volume, self.max_participation)
        return self.base_slippage_bps + self.volume_weighted_bps * participation
