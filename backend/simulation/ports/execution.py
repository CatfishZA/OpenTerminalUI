from __future__ import annotations

from typing import Protocol

from backend.simulation.domain.account import AccountState
from backend.simulation.domain.fills import Fill
from backend.simulation.domain.market import MarketBar
from backend.simulation.domain.orders import Order


class ExecutionModel(Protocol):
    def match(self, order: Order, market_event: MarketBar, account: AccountState) -> list[Fill]: ...
