from __future__ import annotations

from backend.simulation.domain.account import AccountState
from backend.simulation.domain.fills import Fill


class AccountEngine:
    """Phase 1A account mutation boundary."""

    def apply_fill(self, account: AccountState, fill: Fill) -> None:
        raise NotImplementedError("Account fill accounting is a Phase 1B task")
