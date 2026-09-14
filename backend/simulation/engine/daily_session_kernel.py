from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.simulation.domain.account import AccountState
from backend.simulation.domain.enums import EventType, OrderSide, OrderStatus, OrderType, TimeInForce
from backend.simulation.domain.events import SimulationEvent
from backend.simulation.domain.market import MarketBar
from backend.simulation.domain.orders import Order
from backend.simulation.domain.results import PortfolioSnapshot, PositionSnapshot
from backend.simulation.domain.run import SimulationRunSpec
from backend.simulation.domain.strategy import StrategyContext, StrategyIntent
from backend.simulation.engine.account_engine import AccountEngine
from backend.simulation.engine.matching_engine import MatchingEngine
from backend.simulation.engine.order_manager import OrderManager
from backend.simulation.engine.result_builder import ResultBuilder
from backend.simulation.engine.settlement_engine import SettlementEngine
from backend.simulation.engine.valuation_engine import ValuationEngine


class DailyMarketReadModel:
    """History visible to a daily strategy at the current kernel boundary."""

    def __init__(self, values: dict[Any, list[MarketBar]]):
        self.values = values

    def history(self, instrument, *, limit: int):  # noqa: ANN001
        return tuple(self.values.get(instrument, ())[-limit:])


class DailyOrderAPI:
    def __init__(self):
        self.intents: list[StrategyIntent] = []
        self.cancellations: list[str] = []

    def submit(self, intent: StrategyIntent) -> None:
        self.intents.append(intent)

    def cancel(self, order_id: str) -> None:
        self.cancellations.append(order_id)


@dataclass(slots=True)
class DailySessionState:
    run_id: str
    spec: SimulationRunSpec
    account: AccountState
    result: ResultBuilder
    history: dict[Any, list[MarketBar]]
    marks: dict[Any, Decimal]
    sessions: list[Any]
    bars_by_session: dict[Any, dict[Any, MarketBar]]
    sequence: int = 0
    order_sequence: int = 0


class DailySessionKernel:
    """One behavior-preserving canonical daily session shared by BACKTEST and REPLAY."""

    def __init__(self, dependencies: Any, state: DailySessionState):
        self.d = dependencies
        self.state = state
        self.orders = OrderManager()
        self.matcher = MatchingEngine(dependencies.execution)
        self.accounting = AccountEngine()
        self.valuation = ValuationEngine()
        self.settlement = SettlementEngine(int(state.spec.settlement_profile.get("settlement_days", 1)))

    def context(self, now: datetime, orders: DailyOrderAPI | None = None) -> StrategyContext:
        account = self.state.account
        return StrategyContext(
            now,
            account,
            dict(account.positions),
            account.base_cash,
            DailyMarketReadModel(self.state.history),
            orders or DailyOrderAPI(),
        )

    def start(self, at: datetime) -> None:
        self.d.strategy.on_start(self.context(at))

    def finish(self, at: datetime) -> None:
        self.d.strategy.on_finish(self.context(at))

    def emit(self, kind, at, instrument=None, order_id=None, fill_id=None, payload=None):  # noqa: ANN001
        state = self.state
        state.sequence += 1
        event = SimulationEvent(
            state.run_id,
            state.sequence,
            f"evt_{state.sequence:08d}",
            kind,
            at,
            at,
            instrument,
            order_id,
            fill_id,
            payload or {},
        )
        state.result.events.append(event)
        self.d.event_store.append(event)
        return event

    def save_order(self, order: Order) -> None:
        result = self.state.result
        for index, existing in enumerate(result.orders):
            if existing.id == order.id:
                result.orders[index] = order
                break
        else:
            result.orders.append(order)
        if self.d.records:
            self.d.records.save_order(order)

    def submit(self, intent: StrategyIntent, bar: MarketBar, eligible_at: datetime) -> None:
        state = self.state
        account = state.account
        state.order_sequence += 1
        order = Order(
            f"ord_{state.run_id[4:]}_{state.order_sequence:08d}",
            state.run_id,
            account.account_id,
            intent.instrument,
            intent.side,
            intent.order_type,
            intent.quantity,
            intent.quantity,
            intent.tif,
            intent.created_at,
            limit_price=intent.limit_price,
            stop_price=intent.stop_price,
            metadata={
                **intent.metadata,
                "daily_bar_path_policy": state.spec.execution_profile.get("daily_bar_path_policy", "WORST_CASE"),
            },
        )
        self.emit(EventType.ORDER_SUBMITTED, intent.created_at, order.instrument, order.id)
        reference = intent.limit_price or intent.stop_price or bar.close
        reserve = intent.quantity * reference
        reserve += self.d.commission.calculate(order, intent.quantity, reference)
        position = account.positions.get(intent.instrument)
        reject = intent.side is OrderSide.BUY and account.base_cash.available < reserve
        reject = reject or (intent.side is OrderSide.SELL and (position is None or position.quantity < intent.quantity))
        if reject:
            order = replace(order, status=OrderStatus.REJECTED, completed_at=intent.created_at)
            self.save_order(order)
            self.emit(
                EventType.ORDER_REJECTED,
                intent.created_at,
                order.instrument,
                order.id,
                payload={"code": "INSUFFICIENT_CASH" if intent.side is OrderSide.BUY else "ORDER_REJECTED"},
            )
            return
        if intent.side is OrderSide.BUY:
            cash = account.base_cash
            account.cash[account.base_currency] = replace(cash, reserved=cash.reserved + reserve)
            order = replace(order, metadata={**order.metadata, "reserved": str(reserve)})
        order = self.orders.accept(order, intent.created_at, eligible_at)
        account.open_orders[order.id] = order
        self.save_order(order)
        self.emit(
            EventType.ORDER_ACCEPTED,
            intent.created_at,
            order.instrument,
            order.id,
            payload={"eligible_at": eligible_at.isoformat()},
        )

    def cancel(self, order_id: str, at: datetime) -> None:
        account = self.state.account
        order = account.open_orders.get(order_id)
        if order is None:
            return
        if order.side is OrderSide.BUY:
            cash = account.base_cash
            release = Decimal(str(order.metadata.get("reserved", 0)))
            account.cash[account.base_currency] = replace(cash, reserved=max(Decimal(0), cash.reserved - release))
        cancelled = self.orders.complete(order, OrderStatus.CANCELLED, at)
        account.open_orders.pop(order_id, None)
        self.save_order(cancelled)
        self.emit(EventType.ORDER_CANCELLED, at, order.instrument, order.id)

    def fill_order(self, order: Order, bar: MarketBar, at_open: bool, settle_date) -> bool:  # noqa: ANN001
        state = self.state
        account = state.account
        matches = self.matcher.match(order, bar, account, at_open=at_open)
        if not matches:
            return False
        raw = matches[0]
        fill = replace(raw, commission=self.d.commission.calculate(order, raw.quantity, raw.price))
        if order.order_type is OrderType.STOP:
            self.emit(EventType.ORDER_TRIGGERED, fill.executed_at, order.instrument, order.id)
        kind = EventType.ORDER_FILL if fill.quantity == order.remaining_quantity else EventType.ORDER_PARTIAL_FILL
        self.emit(
            kind,
            fill.executed_at,
            order.instrument,
            order.id,
            fill.id,
            {"quantity": str(fill.quantity), "price": str(fill.price)},
        )
        if order.side is OrderSide.BUY:
            reserved = Decimal(str(order.metadata.get("reserved", 0)))
            release = reserved * fill.quantity / order.remaining_quantity
            cash = account.base_cash
            account.cash[account.base_currency] = replace(cash, reserved=max(Decimal(0), cash.reserved - release))
            order = replace(order, metadata={**order.metadata, "reserved": str(reserved - release)})
        entries = self.accounting.apply_fill(account, fill, settlement_date=settle_date)
        state.result.fills.append(fill)
        for entry in entries:
            state.result.ledger.append(entry)
            self.d.ledger.append(entry)
            self.emit(
                EventType.LEDGER_ENTRY,
                fill.executed_at,
                order.instrument,
                order.id,
                fill.id,
                {"entry_type": entry.entry_type.value, "amount": str(entry.amount)},
            )
        remaining = order.remaining_quantity - fill.quantity
        status = OrderStatus.FILLED if remaining == 0 else OrderStatus.PARTIALLY_FILLED
        order = self.orders.transition(order, status, remaining_quantity=remaining)
        if status is OrderStatus.FILLED:
            order = replace(order, completed_at=fill.executed_at)
            account.open_orders.pop(order.id, None)
        else:
            account.open_orders[order.id] = order
        self.save_order(order)
        if self.d.records:
            self.d.records.save_fill(fill)
            for entry in entries:
                self.d.records.save_ledger(entry)
        return True

    def process_session(self, index: int) -> None:
        state = self.state
        account = state.account
        day = state.sessions[index]
        day_bars = state.bars_by_session[day]
        ordered = sorted(day_bars, key=lambda item: item.key)
        first = min(day_bars.values(), key=lambda item: item.ts_open)
        last = max(day_bars.values(), key=lambda item: item.ts_close)
        self.emit(EventType.SESSION_START, first.ts_open)
        self.emit(EventType.SETTLEMENT, first.ts_open, payload={"fill_ids": self.settlement.process(account, day)})
        self.emit(EventType.CORPORATE_ACTION, first.ts_open, payload={"applied": []})
        for instrument in ordered:
            self.emit(EventType.BAR_OPEN, day_bars[instrument].ts_open, instrument, payload={"open": str(day_bars[instrument].open)})
        self.emit(EventType.OPEN_ORDER_MATCH, first.ts_open)
        settlement_days = self.settlement.settlement_days
        settle_day = state.sessions[min(index + settlement_days, len(state.sessions) - 1)]
        matched: set[str] = set()
        for order in sorted(tuple(account.open_orders.values()), key=lambda item: item.id):
            bar = day_bars.get(order.instrument)
            if bar and self.fill_order(order, bar, True, settle_day):
                matched.add(order.id)
        open_callback = self.emit(EventType.STRATEGY_OPEN_CALLBACK, first.ts_open)
        for instrument in ordered:
            api = DailyOrderAPI()
            event = replace(open_callback, instrument=instrument)
            returned = self.d.strategy.on_event(self.context(day_bars[instrument].ts_open, api), event)
            for order_id in api.cancellations:
                self.cancel(order_id, day_bars[instrument].ts_open)
            for intent in [*returned, *api.intents]:
                self.submit(intent, day_bars[instrument], day_bars[instrument].ts_open)
        self.emit(EventType.INTRADAY_ORDER_PROCESSING, last.ts_close)
        for order in sorted(tuple(account.open_orders.values()), key=lambda item: item.id):
            if order.id not in matched and order.instrument in day_bars:
                self.fill_order(order, day_bars[order.instrument], False, settle_day)
        for instrument in ordered:
            bar = day_bars[instrument]
            state.history[instrument].append(bar)
            state.marks[instrument] = bar.close
            self.emit(EventType.BAR_CLOSE, bar.ts_close, instrument, payload={"close": str(bar.close)})
        pending_intents = []
        for instrument in ordered:
            bar = day_bars[instrument]
            callback = self.emit(EventType.STRATEGY_CLOSE_CALLBACK, bar.ts_close, instrument)
            api = DailyOrderAPI()
            next_open = (
                state.bars_by_session[state.sessions[index + 1]][instrument].ts_open
                if index + 1 < len(state.sessions) and instrument in state.bars_by_session[state.sessions[index + 1]]
                else bar.ts_close
            )
            returned = self.d.strategy.on_event(self.context(bar.ts_close, api), callback)
            for order_id in api.cancellations:
                self.cancel(order_id, bar.ts_close)
            for intent in [*returned, *api.intents]:
                pending_intents.append((intent, bar, next_open))
        for intent, bar, next_open in pending_intents:
            self.submit(intent, bar, next_open)
        self.emit(EventType.POST_CLOSE_ORDER_VALIDATION, last.ts_close)
        for order in sorted(tuple(account.open_orders.values()), key=lambda item: item.id):
            if order.tif is TimeInForce.DAY and order.eligible_at and order.eligible_at.date() <= day:
                if order.side is OrderSide.BUY:
                    cash = account.base_cash
                    release = Decimal(str(order.metadata.get("reserved", 0)))
                    account.cash[account.base_currency] = replace(
                        cash, reserved=max(Decimal(0), cash.reserved - release)
                    )
                expired = self.orders.complete(order, OrderStatus.EXPIRED, last.ts_close)
                account.open_orders.pop(order.id, None)
                self.save_order(expired)
                self.emit(EventType.ORDER_EXPIRED, last.ts_close, order.instrument, order.id)
        self.emit(
            EventType.MARK,
            last.ts_close,
            payload={instrument.key: str(mark) for instrument, mark in sorted(state.marks.items(), key=lambda pair: pair[0].key)},
        )
        self.valuation.value(account, state.marks)
        self.emit(EventType.VALUATION, last.ts_close, payload={"equity": str(account.equity)})
        snapshot = self.portfolio_snapshot(last.ts_close)
        state.result.portfolio_snapshots.append(snapshot)
        for instrument in sorted(account.positions, key=lambda item: item.key):
            position = account.positions[instrument]
            position_snapshot = PositionSnapshot(
                state.run_id,
                account.account_id,
                last.ts_close,
                instrument,
                position.quantity,
                position.average_cost,
                position.last_mark or Decimal(0),
                position.market_value,
                position.realized_pnl,
                position.unrealized_pnl,
            )
            state.result.position_snapshots.append(position_snapshot)
            if self.d.records:
                self.d.records.save_position_snapshot(position_snapshot)
        if self.d.records:
            self.d.records.save_portfolio_snapshot(snapshot)
        self.emit(EventType.PORTFOLIO_SNAPSHOT, last.ts_close, payload={"equity": str(snapshot.equity)})
        self.emit(EventType.SESSION_END, last.ts_close)

    def portfolio_snapshot(self, at: datetime) -> PortfolioSnapshot:
        account = self.state.account
        positions = tuple(account.positions.values())
        market_value = sum((position.market_value for position in positions), Decimal(0))
        return PortfolioSnapshot(
            self.state.run_id,
            account.account_id,
            at,
            account.base_cash.settled,
            account.base_cash.unsettled_receivable - account.base_cash.unsettled_payable,
            account.base_cash.reserved,
            sum((abs(position.market_value) for position in positions), Decimal(0)),
            market_value,
            market_value,
            account.realized_pnl,
            account.unrealized_pnl,
            account.fees,
            account.equity,
            account.buying_power,
        )
