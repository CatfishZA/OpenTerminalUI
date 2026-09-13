from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.simulation.domain.enums import OrderSide, OrderType
from backend.simulation.domain.fills import Fill
from backend.simulation.domain.orders import Order
from backend.simulation.domain.ticks import MarketTick


@dataclass(frozen=True, slots=True)
class TickMatch:
    fill: Fill
    triggered: bool = False
    liquidity_assumption: str = "observed"


class TickMatchingEngine:
    """Match canonical orders against normalized live ticks."""

    def match(self, order: Order, tick: MarketTick, *, execution_model, commission_model, fill_id: str) -> TickMatch | None:  # noqa: ANN001
        if tick.instrument != order.instrument:
            return None
        eligible_at = order.eligible_at or order.accepted_at or order.submitted_at
        if tick.ts < eligible_at:
            return None

        triggered = False
        if order.order_type is OrderType.LIMIT:
            if order.side is OrderSide.BUY and tick.price > order.limit_price:
                return None
            if order.side is OrderSide.SELL and tick.price < order.limit_price:
                return None
        elif order.order_type is OrderType.STOP:
            triggered = (
                tick.price >= order.stop_price
                if order.side is OrderSide.BUY
                else tick.price <= order.stop_price
            )
            if not triggered:
                return None

        if tick.size is None:
            quantity = order.remaining_quantity
            liquidity_assumption = "unknown_size_full_fill"
        else:
            available = execution_model.maximum_quantity(tick.size)
            quantity = min(order.remaining_quantity, available)
            liquidity_assumption = "observed"
        if quantity <= 0:
            return None

        try:
            price = execution_model.execution_price(tick.price, order.side, quantity, tick.size)
        except TypeError:
            price = execution_model.execution_price(tick.price, order.side)
        commission = commission_model.calculate(order, quantity, price)
        slippage_bps = abs((price / tick.price - Decimal("1")) * Decimal("10000"))
        return TickMatch(
            fill=Fill(
                id=fill_id,
                run_id=order.run_id,
                order_id=order.id,
                account_id=order.account_id,
                instrument=order.instrument,
                side=order.side,
                quantity=quantity,
                price=price,
                executed_at=tick.ts,
                commission=commission,
                slippage_bps=slippage_bps,
                liquidity_flag="UNKNOWN" if tick.size is None else "SIMULATED",
                execution_model=type(execution_model).__name__,
            ),
            triggered=triggered,
            liquidity_assumption=liquidity_assumption,
        )

