from __future__ import annotations

from dataclasses import replace
from datetime import date

from backend.simulation.domain.account import AccountState
from backend.simulation.domain.cash import CashBalance


class SettlementEngine:
    def __init__(self, settlement_days: int):
        if settlement_days < 0:
            raise ValueError("settlement_days cannot be negative")
        self.settlement_days = settlement_days

    def process(self, account: AccountState, session: date) -> list[str]:
        settled_fill_ids: list[str] = []
        pending = []
        for obligation in account.settlements:
            if obligation.settlement_date > session:
                pending.append(obligation)
                continue
            cash = account.cash.get(obligation.currency, CashBalance(obligation.currency))
            account.cash[obligation.currency] = replace(
                cash,
                settled=cash.settled + obligation.amount,
                unsettled_receivable=cash.unsettled_receivable - obligation.amount,
            )
            settled_fill_ids.append(obligation.fill_id)
        account.settlements = pending
        account.buying_power = account.base_cash.available
        return settled_fill_ids
