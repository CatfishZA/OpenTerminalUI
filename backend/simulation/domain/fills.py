from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from backend.simulation.domain.enums import OrderSide
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.market import as_decimal, require_aware


@dataclass(frozen=True, slots=True)
class Fill:
    id: str
    run_id: str
    order_id: str
    account_id: str
    instrument: InstrumentId
    side: OrderSide
    quantity: Decimal
    price: Decimal
    executed_at: datetime
    commission: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    slippage_bps: Decimal = Decimal("0")
    liquidity_flag: str | None = None
    execution_model: str = ""

    def __post_init__(self) -> None:
        require_aware(self.executed_at, "executed_at")
        for name in ("quantity", "price", "commission", "fees", "slippage_bps"):
            object.__setattr__(self, name, as_decimal(getattr(self, name), name))
        if self.quantity <= 0 or self.price <= 0:
            raise ValueError("fill quantity and price must be positive")
        if self.commission < 0 or self.fees < 0:
            raise ValueError("fill costs cannot be negative")
