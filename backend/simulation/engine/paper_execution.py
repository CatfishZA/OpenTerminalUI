from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal

from backend.simulation.domain.account import AccountState
from backend.simulation.domain.cash import CashBalance
from backend.simulation.domain.enums import OrderSide, OrderStatus
from backend.simulation.domain.events import LedgerEntry
from backend.simulation.domain.fills import Fill
from backend.simulation.domain.orders import Order
from backend.simulation.domain.ticks import MarketTick
from backend.simulation.engine.account_engine import AccountEngine
from backend.simulation.engine.order_manager import OrderManager
from backend.simulation.engine.settlement_engine import SettlementEngine
from backend.simulation.engine.tick_matching_engine import TickMatchingEngine
from backend.simulation.engine.valuation_engine import ValuationEngine


@dataclass(frozen=True, slots=True)
class PaperExecutionResult:
    order: Order
    fill: Fill
    ledger: tuple[LedgerEntry, ...]
    triggered: bool
    liquidity_assumption: str
    realized_pnl_delta: Decimal


class PaperExecutionEngine:
    """Live-clock orchestration around the shared canonical financial engines."""

    def __init__(self, *, settlement_days: int = 1):
        self.account_engine = AccountEngine()
        self.order_manager = OrderManager()
        self.settlement_engine = SettlementEngine(settlement_days)
        self.valuation_engine = ValuationEngine()
        self.matching_engine = TickMatchingEngine()
        self.settlement_days = settlement_days

    def accept(
        self,
        account: AccountState,
        order: Order,
        *,
        accepted_at: datetime,
        eligible_at: datetime | None = None,
        reserve_price: Decimal | None,
        execution_model,
        commission_model,
    ) -> Order:
        if order.instrument.currency != account.base_currency:
            raise ValueError("INVALID_ORDER: instrument currency differs from portfolio base currency")
        if order.side is OrderSide.SELL:
            position = account.positions.get(order.instrument)
            already_committed = sum(
                (
                    item.remaining_quantity
                    for item in account.open_orders.values()
                    if item.instrument == order.instrument and item.side is OrderSide.SELL
                ),
                Decimal("0"),
            )
            if position is None or position.quantity - already_committed < order.quantity:
                raise ValueError("ORDER_REJECTED: shorting is disabled")
        reservation = Decimal("0")
        if order.side is OrderSide.BUY:
            cash = account.base_cash
            if reserve_price is None:
                # An unpriced MARKET order remains open without a fabricated
                # fill, but it must not allow the same buying power to be spent
                # again. Conservatively reserve the currently available account.
                reservation = cash.available
                if reservation <= 0:
                    raise ValueError("INSUFFICIENT_CASH")
            else:
                try:
                    worst_price = execution_model.execution_price(
                        reserve_price, order.side, order.quantity, order.quantity
                    )
                except TypeError:
                    worst_price = execution_model.execution_price(reserve_price, order.side)
                reservation = worst_price * order.quantity + commission_model.calculate(
                    order, order.quantity, worst_price
                )
            if cash.available < reservation:
                raise ValueError("INSUFFICIENT_CASH")
            account.cash[account.base_currency] = replace(cash, reserved=cash.reserved + reservation)
            account.buying_power = account.base_cash.available
        accepted = self.order_manager.accept(order, accepted_at, eligible_at or accepted_at)
        accepted = replace(accepted, metadata={**accepted.metadata, "cash_reservation": str(reservation)})
        account.open_orders[accepted.id] = accepted
        return accepted

    def cancel(self, account: AccountState, order: Order, *, at: datetime) -> Order:
        cancelled = self.order_manager.complete(order, OrderStatus.CANCELLED, at)
        self._release_reservation(account, order, Decimal(str(order.metadata.get("cash_reservation", "0"))))
        account.open_orders.pop(order.id, None)
        return cancelled

    def execute(
        self,
        account: AccountState,
        order: Order,
        tick: MarketTick,
        *,
        execution_model,
        commission_model,
        fill_id: str,
    ) -> PaperExecutionResult | None:
        matched = self.matching_engine.match(
            order,
            tick,
            execution_model=execution_model,
            commission_model=commission_model,
            fill_id=fill_id,
        )
        if matched is None:
            return None
        fill = matched.fill
        total_reservation = Decimal(str(order.metadata.get("cash_reservation", "0")))
        released = (
            total_reservation * fill.quantity / order.remaining_quantity
            if order.remaining_quantity
            else Decimal("0")
        )
        self._release_reservation(account, order, released)
        prior_realized = account.realized_pnl
        ledger = self.account_engine.apply_fill(
            account,
            fill,
            settlement_date=tick.ts.date() + timedelta(days=self.settlement_days),
        )
        remaining = order.remaining_quantity - fill.quantity
        status = OrderStatus.FILLED if remaining == 0 else OrderStatus.PARTIALLY_FILLED
        updated = self.order_manager.transition(order, status, remaining_quantity=remaining)
        updated = replace(
            updated,
            completed_at=tick.ts if status is OrderStatus.FILLED else None,
            metadata={**updated.metadata, "cash_reservation": str(total_reservation - released)},
        )
        if status is OrderStatus.FILLED:
            account.open_orders.pop(order.id, None)
        else:
            account.open_orders[order.id] = updated
        return PaperExecutionResult(
            order=updated,
            fill=fill,
            ledger=tuple(ledger),
            triggered=matched.triggered,
            liquidity_assumption=matched.liquidity_assumption,
            realized_pnl_delta=account.realized_pnl - prior_realized,
        )

    def settle(self, account: AccountState, session: date) -> list[str]:
        return self.settlement_engine.process(account, session)

    @staticmethod
    def _release_reservation(account: AccountState, order: Order, amount: Decimal) -> None:
        if order.side is not OrderSide.BUY or amount <= 0:
            return
        cash = account.base_cash
        account.cash[account.base_currency] = replace(
            cash, reserved=max(Decimal("0"), cash.reserved - amount)
        )
        account.buying_power = account.base_cash.available
