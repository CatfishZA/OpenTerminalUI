from __future__ import annotations

from backend.simulation.domain.account import AccountState
from backend.simulation.domain.fills import Fill
from backend.simulation.domain.market import MarketBar
from backend.simulation.domain.orders import Order
from backend.simulation.ports.execution import ExecutionModel


class MatchingEngine:
    def __init__(self, execution_model: ExecutionModel):
        self.execution_model = execution_model

    def match(self, order: Order, bar: MarketBar, account: AccountState) -> list[Fill]:
        return self.execution_model.match(order, bar, account)
