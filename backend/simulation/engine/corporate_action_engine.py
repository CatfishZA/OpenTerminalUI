from __future__ import annotations

from backend.simulation.domain.account import AccountState
from backend.simulation.domain.corporate_actions import CorporateAction


class CorporateActionEngine:
    def apply(self, account: AccountState, action: CorporateAction) -> None:
        raise NotImplementedError("Corporate-action accounting is a Phase 1B task")
