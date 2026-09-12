from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from backend.simulation.domain.orders import Order


class CommissionModel(Protocol):
    def calculate(self, order: Order, fill_quantity: Decimal, fill_price: Decimal) -> Decimal: ...
