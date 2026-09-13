from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.simulation.domain.market import as_decimal, require_aware


@dataclass(frozen=True, slots=True)
class PaperSessionSpec:
    portfolio_id: str
    initial_cash: Decimal
    base_currency: str
    execution_profile: dict[str, Any]
    commission_profile: dict[str, Any]
    settlement_profile: dict[str, Any]
    started_at: datetime
    strategy_key: str = "manual:paper"
    strategy_context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        cash = as_decimal(self.initial_cash, "initial_cash")
        currency = self.base_currency.strip().upper()
        require_aware(self.started_at, "started_at")
        if not self.portfolio_id:
            raise ValueError("portfolio_id is required")
        if cash <= 0:
            raise ValueError("initial_cash must be positive")
        if len(currency) != 3:
            raise ValueError("base_currency must be a three-letter code")
        if not self.strategy_key.strip():
            raise ValueError("strategy_key is required")
        object.__setattr__(self, "initial_cash", cash)
        object.__setattr__(self, "base_currency", currency)

