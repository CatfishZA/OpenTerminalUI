from __future__ import annotations

from decimal import Decimal

from backend.simulation.domain.account import AccountState
from dataclasses import replace

from backend.simulation.domain.identifiers import InstrumentId


class ValuationEngine:
    def value(self, account: AccountState, marks: dict[InstrumentId, Decimal]) -> Decimal:
        market_value = Decimal("0")
        unrealized = Decimal("0")
        for instrument in sorted(account.positions, key=lambda item: item.key):
            position = account.positions[instrument]
            mark = marks.get(instrument, position.last_mark)
            if mark is None:
                continue
            value = position.quantity * mark
            pnl = position.quantity * (mark - position.average_cost)
            account.positions[instrument] = replace(
                position, last_mark=mark, market_value=value, unrealized_pnl=pnl
            )
            market_value += value
            unrealized += pnl
        account.unrealized_pnl = unrealized
        account.equity = account.base_cash.total + market_value
        account.buying_power = account.base_cash.available
        return account.equity
