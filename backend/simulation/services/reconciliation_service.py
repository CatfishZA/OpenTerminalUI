from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from backend.simulation.domain.events import LedgerEntry


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
