from __future__ import annotations

from decimal import Decimal

from backend.simulation.domain.account import AccountState
from backend.simulation.domain.identifiers import InstrumentId


class ValuationEngine:
    def value(self, account: AccountState, marks: dict[InstrumentId, Decimal]) -> Decimal:
        raise NotImplementedError("Portfolio valuation is a Phase 1B task")
