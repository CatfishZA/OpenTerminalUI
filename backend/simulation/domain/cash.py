from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.simulation.domain.market import as_decimal


@dataclass(frozen=True, slots=True)
class CashBalance:
    currency: str
    settled: Decimal = Decimal("0")
    unsettled_receivable: Decimal = Decimal("0")
    unsettled_payable: Decimal = Decimal("0")
    reserved: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", self.currency.strip().upper())
        if len(self.currency) != 3:
            raise ValueError("cash currency must be a three-letter code")
        for name in ("settled", "unsettled_receivable", "unsettled_payable", "reserved"):
            object.__setattr__(self, name, as_decimal(getattr(self, name), name))
        if self.reserved < 0:
            raise ValueError("reserved cash cannot be negative")

    @property
    def available(self) -> Decimal:
        return self.settled - self.unsettled_payable - self.reserved

    @property
    def total(self) -> Decimal:
        return self.settled + self.unsettled_receivable - self.unsettled_payable
