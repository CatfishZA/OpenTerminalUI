from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from hashlib import sha256

from backend.simulation.domain.account import AccountState
from backend.simulation.domain.enums import OrderSide, OrderType
from backend.simulation.domain.fills import Fill
from backend.simulation.domain.market import MarketBar
from backend.simulation.domain.orders import Order
from backend.simulation.ports.execution import ExecutionModel


class MatchingEngine:
    def __init__(self, execution_model: ExecutionModel):
        self.execution_model = execution_model

    def match(self, order: Order, bar: MarketBar, account: AccountState, *, at_open: bool) -> list[Fill]:
        if order.eligible_at is None or bar.ts_open < order.eligible_at:
            return []
        reference: Decimal | None = None
        if order.order_type is OrderType.MARKET:
            if at_open:
                reference = bar.open
        elif order.order_type is OrderType.LIMIT:
            assert order.limit_price is not None
            if order.side is OrderSide.BUY:
                reference = bar.open if at_open and bar.open <= order.limit_price else order.limit_price if not at_open and bar.low <= order.limit_price else None
            else:
                reference = bar.open if at_open and bar.open >= order.limit_price else order.limit_price if not at_open and bar.high >= order.limit_price else None
        else:
            assert order.stop_price is not None
            if order.side is OrderSide.BUY:
                triggered = bar.open >= order.stop_price if at_open else bar.high >= order.stop_price
                reference = max(bar.open, order.stop_price) if at_open and triggered else order.stop_price if triggered else None
            else:
                triggered = bar.open <= order.stop_price if at_open else bar.low <= order.stop_price
                reference = min(bar.open, order.stop_price) if at_open and triggered else order.stop_price if triggered else None
        if reference is None:
            return []
        maximum = self.execution_model.maximum_quantity(bar.volume)
        quantity = min(order.remaining_quantity, maximum)
        if quantity <= 0:
            return []
        bps = getattr(self.execution_model, "slippage_bps", None)
        if bps is None:
            bps = self.execution_model.slippage_for(quantity, bar.volume)
        price = reference * (Decimal("1") + (bps / Decimal("10000")) * (Decimal("1") if order.side is OrderSide.BUY else Decimal("-1")))
        token = sha256(f"{order.id}|{bar.ts_open.isoformat()}|{at_open}|{order.remaining_quantity}".encode()).hexdigest()[:16]
        return [Fill(
            id=f"fill_{token}", run_id=order.run_id, order_id=order.id, account_id=order.account_id,
            instrument=order.instrument, side=order.side, quantity=quantity, price=price,
            executed_at=bar.ts_open if at_open else bar.ts_close, slippage_bps=bps,
            execution_model=type(self.execution_model).__name__,
        )]
