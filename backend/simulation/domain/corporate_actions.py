from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

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
    data_version_id: str | None
    warnings: tuple[str, ...] = ()
    source: str | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
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


@dataclass(frozen=True, slots=True)
class DividendEntitlement:
    id: str
    run_id: str
    corporate_action_source_id: str
    instrument: InstrumentId
    entitlement_date: date
    pay_date: date
    eligible_quantity: Decimal
    cash_amount_per_share: Decimal
    currency: str
    total_amount: Decimal
    status: str = "PENDING"
    created_at: datetime | None = None
    paid_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("eligible_quantity", "cash_amount_per_share", "total_amount"):
            object.__setattr__(self, name, as_decimal(getattr(self, name), name))
        if self.status not in {"PENDING", "PAID"}:
            raise ValueError("invalid dividend entitlement status")
