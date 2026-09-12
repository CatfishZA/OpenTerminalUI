from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.simulation.domain.enums import CorporateActionType
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.market import as_decimal


@dataclass(frozen=True, slots=True)
class CorporateAction:
    id: str
    instrument: InstrumentId
    action_type: CorporateActionType
    ex_date: date
    record_date: date | None
    pay_date: date | None
    factor: Decimal | None
    cash_amount: Decimal | None
    currency: str | None
    data_version_id: str

    def __post_init__(self) -> None:
        if not self.data_version_id:
            raise ValueError("corporate action requires data_version_id")
        if self.factor is not None:
            object.__setattr__(self, "factor", as_decimal(self.factor, "factor"))
        if self.cash_amount is not None:
            object.__setattr__(self, "cash_amount", as_decimal(self.cash_amount, "cash_amount"))
        if self.action_type is CorporateActionType.SPLIT and (self.factor is None or self.factor <= 0):
            raise ValueError("split action requires a positive factor")
        if self.action_type is CorporateActionType.CASH_DIVIDEND and (
            self.cash_amount is None or self.cash_amount < 0 or not self.currency
        ):
            raise ValueError("cash dividend requires a non-negative amount and currency")
