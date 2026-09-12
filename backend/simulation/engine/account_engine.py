from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from backend.simulation.domain.account import AccountState, SettlementObligation
from backend.simulation.domain.cash import CashBalance
from backend.simulation.domain.enums import LedgerEntryType, OrderSide
from backend.simulation.domain.events import LedgerEntry
from backend.simulation.domain.fills import Fill
from backend.simulation.domain.positions import Position


class AccountEngine:
    """Apply immutable fills to one shared long-only cash account."""

    def apply_fill(
        self, account: AccountState, fill: Fill, *, settlement_date: date
    ) -> list[LedgerEntry]:
        currency = fill.instrument.currency
        if currency != account.base_currency:
            raise ValueError("UNSUPPORTED_ASSET_CLASS: Phase 1B is single-currency")
        cash = account.cash.get(currency, CashBalance(currency))
        position = account.positions.get(fill.instrument, Position(fill.instrument))
        principal = fill.quantity * fill.price
        costs = fill.commission + fill.fees
        entries: list[LedgerEntry] = []

        def entry(kind: LedgerEntryType, amount: Decimal, suffix: str) -> LedgerEntry:
            return LedgerEntry(
                id=f"led_{fill.id}_{suffix}", run_id=fill.run_id, account_id=fill.account_id,
                ts=fill.executed_at, entry_type=kind, currency=currency, amount=amount,
                instrument=fill.instrument, order_id=fill.order_id, fill_id=fill.id,
            )

        if fill.side is OrderSide.BUY:
            debit = principal + costs
            if cash.available < debit:
                raise ValueError("INSUFFICIENT_CASH")
            new_quantity = position.quantity + fill.quantity
            average = (
                (position.quantity * position.average_cost + principal) / new_quantity
                if new_quantity else Decimal("0")
            )
            cash = replace(cash, settled=cash.settled - debit)
            position = replace(position, quantity=new_quantity, average_cost=average)
            entries.append(entry(LedgerEntryType.TRADE_PRINCIPAL, -principal, "principal"))
        else:
            if position.quantity < fill.quantity:
                raise ValueError("ORDER_REJECTED: shorting is disabled")
            realized = (fill.price - position.average_cost) * fill.quantity
            new_quantity = position.quantity - fill.quantity
            position = replace(
                position,
                quantity=new_quantity,
                average_cost=position.average_cost if new_quantity else Decimal("0"),
                realized_pnl=position.realized_pnl + realized,
            )
            if settlement_date <= fill.executed_at.date():
                cash = replace(cash, settled=cash.settled + principal)
            else:
                cash = replace(cash, unsettled_receivable=cash.unsettled_receivable + principal)
                account.settlements.append(SettlementObligation(settlement_date, currency, principal, fill.id))
            account.realized_pnl += realized
            entries.append(entry(LedgerEntryType.TRADE_PRINCIPAL, principal, "principal"))
            if costs:
                cash = replace(cash, settled=cash.settled - costs)

        if fill.commission:
            entries.append(entry(LedgerEntryType.COMMISSION, -fill.commission, "commission"))
        if fill.fees:
            entries.append(entry(LedgerEntryType.FEE, -fill.fees, "fee"))
        account.fees += costs
        account.cash[currency] = cash
        account.positions[fill.instrument] = position
        account.buying_power = cash.available
        return entries
