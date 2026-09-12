from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from backend.simulation.domain.account import AccountState
from backend.simulation.domain.orders import Order


@dataclass(frozen=True, slots=True)
class RiskDecision:
    accepted: bool
    allowed_quantity: Decimal
    reason: str | None = None


class RiskModel(Protocol):
    def evaluate(self, order: Order, account: AccountState) -> RiskDecision: ...
