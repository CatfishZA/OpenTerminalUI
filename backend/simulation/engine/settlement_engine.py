from __future__ import annotations

from datetime import date

from backend.simulation.domain.account import AccountState


class SettlementEngine:
    def __init__(self, settlement_days: int):
        if settlement_days < 0:
            raise ValueError("settlement_days cannot be negative")
        self.settlement_days = settlement_days

    def process(self, account: AccountState, session: date) -> None:
        raise NotImplementedError("Settlement processing is a Phase 1B task")
