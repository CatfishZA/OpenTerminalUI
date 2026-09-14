from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from backend.simulation.domain.events import LedgerEntry
from backend.simulation.domain.account import AccountState
from backend.simulation.domain.corporate_actions import CorporateAction
from backend.simulation.domain.enums import CorporateActionType, OrderSide
from backend.simulation.domain.fills import Fill
from backend.simulation.domain.positions import Position


class ReconciliationService:
    """Phase 1A ledger identity helper; engine reconciliation arrives in Phase 1B."""

    @staticmethod
    def cash_from_ledger(opening_cash: Decimal, entries: Iterable[LedgerEntry], currency: str) -> Decimal:
        return opening_cash + sum(
            (entry.amount for entry in entries if entry.currency == currency.upper()),
            start=Decimal("0"),
        )

    @staticmethod
    def assert_cash(expected: Decimal, actual: Decimal) -> None:
        if expected != actual:
            raise ValueError(f"LEDGER_RECONCILIATION_FAILED: expected {expected}, actual {actual}")

    def reconcile(
        self,
        opening_cash: Decimal,
        entries: Iterable[LedgerEntry],
        fills: Iterable[Fill],
        account: AccountState,
        corporate_actions: Iterable[CorporateAction] = (),
        applied_corporate_action_ids: set[str] | None = None,
    ) -> dict[str, bool]:
        entries = tuple(entries)
        economic_entries = tuple(entry for entry in entries if not entry.metadata.get("opening_balance"))
        ledger_cash = self.cash_from_ledger(opening_cash, economic_entries, account.base_currency)
        self.assert_cash(ledger_cash, account.base_cash.total)
        applied_corporate_action_ids = applied_corporate_action_ids or set()
        splits = tuple(
            action
            for action in corporate_actions
            if action.action_type is CorporateActionType.SPLIT
            and action.id in applied_corporate_action_ids
        )
        quantities = {}
        for fill in fills:
            direction = Decimal("1") if fill.side is OrderSide.BUY else Decimal("-1")
            adjusted_quantity = fill.quantity
            for action in splits:
                if action.instrument == fill.instrument and fill.executed_at.date() < action.ex_date:
                    adjusted_quantity *= action.factor
            quantities[fill.instrument] = quantities.get(fill.instrument, Decimal("0")) + direction * adjusted_quantity
        for instrument in set(quantities) | set(account.positions):
            if quantities.get(instrument, Decimal("0")) != account.positions.get(instrument, Position(instrument)).quantity:
                raise ValueError("LEDGER_RECONCILIATION_FAILED: fill-derived position mismatch")
        market_value = sum((position.market_value for position in account.positions.values()), Decimal("0"))
        if account.equity != account.base_cash.total + market_value:
            raise ValueError("LEDGER_RECONCILIATION_FAILED: equity mismatch")
        return {"cash": True, "positions": True, "equity": True}
