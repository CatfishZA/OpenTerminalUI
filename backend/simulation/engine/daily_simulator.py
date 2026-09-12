from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.simulation.domain.account import AccountState
from backend.simulation.domain.cash import CashBalance
from backend.simulation.domain.enums import EventType, LedgerEntryType, OrderSide, OrderStatus, OrderType, TimeInForce
from backend.simulation.domain.events import LedgerEntry, SimulationEvent
from backend.simulation.domain.market import MarketBar
from backend.simulation.domain.orders import Order
from backend.simulation.domain.results import PortfolioSnapshot, PositionSnapshot, SimulationResult
from backend.simulation.domain.run import RunManifest, SimulationRunSpec
from backend.simulation.domain.strategy import StrategyContext, StrategyIntent
from backend.simulation.engine.account_engine import AccountEngine
from backend.simulation.engine.matching_engine import MatchingEngine
from backend.simulation.engine.order_manager import OrderManager
from backend.simulation.engine.result_builder import ResultBuilder
from backend.simulation.engine.settlement_engine import SettlementEngine
from backend.simulation.engine.valuation_engine import ValuationEngine
from backend.simulation.persistence.serializers import to_primitive
from backend.simulation.services.manifest_service import ManifestService, sha256_value
from backend.simulation.services.reconciliation_service import ReconciliationService


@dataclass(slots=True)
class DailySimulatorDependencies:
    market_data: Any
    corporate_actions: Any
    strategy: Any
    execution: Any
    commission: Any
    event_store: Any
    ledger: Any
    records: Any | None = None


class _History:
    def __init__(self, values): self.values = values  # noqa: ANN001
    def history(self, instrument, *, limit: int): return tuple(self.values.get(instrument, ())[-limit:])  # noqa: ANN001


class _Orders:
    def __init__(self): self.intents, self.cancellations = [], []
    def submit(self, intent): self.intents.append(intent)  # noqa: ANN001
    def cancel(self, order_id): self.cancellations.append(order_id)  # noqa: ANN001


class DailySimulator:
    """Deterministic long-only daily cash-equity reference simulator."""

    def __init__(self, dependencies: DailySimulatorDependencies):
        self.d = dependencies
        self.orders = OrderManager()
        self.matcher = MatchingEngine(dependencies.execution)
        self.accounting = AccountEngine()
        self.valuation = ValuationEngine()

    def run(self, spec: SimulationRunSpec, *, run_id: str | None = None, manifest: RunManifest | None = None) -> SimulationResult:
        data_manifest = self.d.market_data.manifest()
        bars = list(self.d.market_data.iter_daily_events(list(spec.universe), spec.start, spec.end))
        self._validate(spec, bars)
        run_id = run_id or f"sim_{sha256_value(spec)[:12]}"
        manifest = manifest or ManifestService(engine_version="sim-daily-v1b").build(
            run_id, spec, dataset_hash=data_manifest.dataset_hash,
            calendar_version=data_manifest.calendar_version, created_at=min(x.ts_open for x in bars),
        )
        out = ResultBuilder(run_id, manifest)
        account = AccountState(f"acct_{run_id[4:]}", spec.base_currency,
            cash={spec.base_currency: CashBalance(spec.base_currency, settled=spec.initial_cash)},
            equity=spec.initial_cash, buying_power=spec.initial_cash)
        sequence = order_seq = 0
        history = {instrument: [] for instrument in spec.universe}
        marks = {}
        by_day = {}
        for bar in bars: by_day.setdefault(bar.ts_open.date(), {})[bar.instrument] = bar
        sessions = sorted(by_day)
        settlement_days = int(spec.settlement_profile.get("settlement_days", 1))
        settlement = SettlementEngine(settlement_days)

        opening = LedgerEntry(f"led_{run_id}_opening", run_id, account.account_id, min(x.ts_open for x in bars),
            LedgerEntryType.CASH_DEPOSIT, spec.base_currency, spec.initial_cash, metadata={"opening_balance": True})
        out.ledger.append(opening); self.d.ledger.append(opening)

        def emit(kind, at, instrument=None, order_id=None, fill_id=None, payload=None):  # noqa: ANN001
            nonlocal sequence
            sequence += 1
            event = SimulationEvent(run_id, sequence, f"evt_{sequence:08d}", kind, at, at,
                instrument, order_id, fill_id, payload or {})
            out.events.append(event); self.d.event_store.append(event)
            return event

        def save_order(order):  # noqa: ANN001
            for idx, existing in enumerate(out.orders):
                if existing.id == order.id: out.orders[idx] = order; break
            else: out.orders.append(order)
            if self.d.records: self.d.records.save_order(order)

        def submit(intent: StrategyIntent, bar: MarketBar, eligible_at: datetime):
            nonlocal order_seq
            order_seq += 1
            order = Order(f"ord_{order_seq:08d}", run_id, account.account_id, intent.instrument, intent.side,
                intent.order_type, intent.quantity, intent.quantity, intent.tif, intent.created_at,
                limit_price=intent.limit_price, stop_price=intent.stop_price,
                metadata={**intent.metadata, "daily_bar_path_policy": spec.execution_profile.get("daily_bar_path_policy", "WORST_CASE")})
            emit(EventType.ORDER_SUBMITTED, intent.created_at, order.instrument, order.id)
            reference = intent.limit_price or intent.stop_price or bar.close
            reserve = intent.quantity * reference
            reserve += self.d.commission.calculate(order, intent.quantity, reference)
            position = account.positions.get(intent.instrument)
            reject = intent.side is OrderSide.BUY and account.base_cash.available < reserve
            reject = reject or (intent.side is OrderSide.SELL and (position is None or position.quantity < intent.quantity))
            if reject:
                order = replace(order, status=OrderStatus.REJECTED, completed_at=intent.created_at)
                save_order(order); emit(EventType.ORDER_REJECTED, intent.created_at, order.instrument, order.id,
                    payload={"code": "INSUFFICIENT_CASH" if intent.side is OrderSide.BUY else "ORDER_REJECTED"}); return
            if intent.side is OrderSide.BUY:
                cash = account.base_cash
                account.cash[account.base_currency] = replace(cash, reserved=cash.reserved + reserve)
                order = replace(order, metadata={**order.metadata, "reserved": str(reserve)})
            order = self.orders.accept(order, intent.created_at, eligible_at)
            account.open_orders[order.id] = order; save_order(order)
            emit(EventType.ORDER_ACCEPTED, intent.created_at, order.instrument, order.id, payload={"eligible_at": eligible_at.isoformat()})

        def cancel(order_id: str, at: datetime) -> None:
            order = account.open_orders.get(order_id)
            if order is None:
                return
            if order.side is OrderSide.BUY:
                cash = account.base_cash; release = Decimal(str(order.metadata.get("reserved", 0)))
                account.cash[account.base_currency] = replace(cash, reserved=max(Decimal(0), cash.reserved-release))
            cancelled = self.orders.complete(order, OrderStatus.CANCELLED, at)
            account.open_orders.pop(order_id, None); save_order(cancelled)
            emit(EventType.ORDER_CANCELLED, at, order.instrument, order.id)

        def fill_order(order: Order, bar: MarketBar, at_open: bool, settle_date) -> bool:  # noqa: ANN001
            matches = self.matcher.match(order, bar, account, at_open=at_open)
            if not matches: return False
            raw = matches[0]
            fill = replace(raw, commission=self.d.commission.calculate(order, raw.quantity, raw.price))
            if order.order_type is OrderType.STOP: emit(EventType.ORDER_TRIGGERED, fill.executed_at, order.instrument, order.id)
            kind = EventType.ORDER_FILL if fill.quantity == order.remaining_quantity else EventType.ORDER_PARTIAL_FILL
            emit(kind, fill.executed_at, order.instrument, order.id, fill.id, {"quantity": str(fill.quantity), "price": str(fill.price)})
            if order.side is OrderSide.BUY:
                reserved = Decimal(str(order.metadata.get("reserved", 0)))
                release = reserved * fill.quantity / order.remaining_quantity
                cash = account.base_cash
                account.cash[account.base_currency] = replace(cash, reserved=max(Decimal(0), cash.reserved-release))
                order = replace(order, metadata={**order.metadata, "reserved": str(reserved-release)})
            entries = self.accounting.apply_fill(account, fill, settlement_date=settle_date)
            out.fills.append(fill)
            for entry in entries:
                out.ledger.append(entry); self.d.ledger.append(entry)
                emit(EventType.LEDGER_ENTRY, fill.executed_at, order.instrument, order.id, fill.id,
                    {"entry_type": entry.entry_type.value, "amount": str(entry.amount)})
            remaining = order.remaining_quantity-fill.quantity
            status = OrderStatus.FILLED if remaining == 0 else OrderStatus.PARTIALLY_FILLED
            order = self.orders.transition(order, status, remaining_quantity=remaining)
            if status is OrderStatus.FILLED: order = replace(order, completed_at=fill.executed_at); account.open_orders.pop(order.id, None)
            else: account.open_orders[order.id] = order
            save_order(order)
            if self.d.records:
                self.d.records.save_fill(fill)
                for entry in entries: self.d.records.save_ledger(entry)
            return True

        self.d.strategy.on_start(self._ctx(min(x.ts_open for x in bars), account, history, _Orders()))
        for index, day in enumerate(sessions):
            day_bars = by_day[day]; ordered = sorted(day_bars, key=lambda x: x.key)
            first, last = min(day_bars.values(), key=lambda x: x.ts_open), max(day_bars.values(), key=lambda x: x.ts_close)
            emit(EventType.SESSION_START, first.ts_open)
            emit(EventType.SETTLEMENT, first.ts_open, payload={"fill_ids": settlement.process(account, day)})
            emit(EventType.CORPORATE_ACTION, first.ts_open, payload={"applied": []})
            for instrument in ordered: emit(EventType.BAR_OPEN, day_bars[instrument].ts_open, instrument, payload={"open": str(day_bars[instrument].open)})
            emit(EventType.OPEN_ORDER_MATCH, first.ts_open)
            settle_day = sessions[min(index+settlement_days, len(sessions)-1)]
            matched = set()
            for order in sorted(tuple(account.open_orders.values()), key=lambda x: x.id):
                bar = day_bars.get(order.instrument)
                if bar and fill_order(order, bar, True, settle_day): matched.add(order.id)
            open_callback = emit(EventType.STRATEGY_OPEN_CALLBACK, first.ts_open)
            for instrument in ordered:
                api = _Orders(); event = replace(open_callback, instrument=instrument)
                returned = self.d.strategy.on_event(self._ctx(day_bars[instrument].ts_open, account, history, api), event)
                for order_id in api.cancellations: cancel(order_id, day_bars[instrument].ts_open)
                for intent in [*returned, *api.intents]:
                    submit(intent, day_bars[instrument], day_bars[instrument].ts_open)
            emit(EventType.INTRADAY_ORDER_PROCESSING, last.ts_close)
            for order in sorted(tuple(account.open_orders.values()), key=lambda x: x.id):
                if order.id not in matched and order.instrument in day_bars: fill_order(order, day_bars[order.instrument], False, settle_day)
            for instrument in ordered:
                bar = day_bars[instrument]; history[instrument].append(bar); marks[instrument] = bar.close
                emit(EventType.BAR_CLOSE, bar.ts_close, instrument, payload={"close": str(bar.close)})
            pending_intents = []
            for instrument in ordered:
                bar = day_bars[instrument]
                callback = emit(EventType.STRATEGY_CLOSE_CALLBACK, bar.ts_close, instrument); api = _Orders()
                next_open = by_day[sessions[index+1]][instrument].ts_open if index+1 < len(sessions) and instrument in by_day[sessions[index+1]] else bar.ts_close
                returned = self.d.strategy.on_event(self._ctx(bar.ts_close, account, history, api), callback)
                for order_id in api.cancellations: cancel(order_id, bar.ts_close)
                for intent in [*returned, *api.intents]:
                    pending_intents.append((intent, bar, next_open))
            for intent, bar, next_open in pending_intents: submit(intent, bar, next_open)
            emit(EventType.POST_CLOSE_ORDER_VALIDATION, last.ts_close)
            for order in sorted(tuple(account.open_orders.values()), key=lambda x: x.id):
                if order.tif is TimeInForce.DAY and order.eligible_at and order.eligible_at.date() <= day:
                    if order.side is OrderSide.BUY:
                        cash=account.base_cash; release=Decimal(str(order.metadata.get("reserved", 0)))
                        account.cash[account.base_currency]=replace(cash,reserved=max(Decimal(0),cash.reserved-release))
                    expired=self.orders.complete(order,OrderStatus.EXPIRED,last.ts_close); account.open_orders.pop(order.id,None); save_order(expired)
                    emit(EventType.ORDER_EXPIRED,last.ts_close,order.instrument,order.id)
            emit(EventType.MARK,last.ts_close,payload={x.key:str(y) for x,y in sorted(marks.items(),key=lambda z:z[0].key)})
            self.valuation.value(account,marks); emit(EventType.VALUATION,last.ts_close,payload={"equity":str(account.equity)})
            snapshot=self._snapshot(run_id,account,last.ts_close); out.portfolio_snapshots.append(snapshot)
            for instrument in sorted(account.positions,key=lambda x:x.key):
                p=account.positions[instrument]; ps=PositionSnapshot(run_id,account.account_id,last.ts_close,instrument,p.quantity,p.average_cost,p.last_mark or Decimal(0),p.market_value,p.realized_pnl,p.unrealized_pnl); out.position_snapshots.append(ps)
                if self.d.records:self.d.records.save_position_snapshot(ps)
            if self.d.records:self.d.records.save_portfolio_snapshot(snapshot)
            emit(EventType.PORTFOLIO_SNAPSHOT,last.ts_close,payload={"equity":str(snapshot.equity)}); emit(EventType.SESSION_END,last.ts_close)
        self.d.strategy.on_finish(self._ctx(last.ts_close,account,history,_Orders()))
        reconciliation=ReconciliationService().reconcile(spec.initial_cash,out.ledger,out.fills,account)
        summary={"status":"DONE","initial_cash":spec.initial_cash,"final_equity":account.equity,"ending_cash":account.base_cash.total,
            "realized_pnl":account.realized_pnl,"unrealized_pnl":account.unrealized_pnl,"total_return":account.equity/spec.initial_cash-Decimal(1),
            "daily_bar_path_policy":spec.execution_profile.get("daily_bar_path_policy","WORST_CASE")}
        result_hash=sha256_value({"events":out.events,"orders":out.orders,"fills":out.fills,"ledger":out.ledger,"portfolio":out.portfolio_snapshots,"positions":out.position_snapshots,"summary":summary})
        return out.build(summary,data_quality={"status":"VALID"},reconciliation=reconciliation,result_hash=result_hash)

    @staticmethod
    def _ctx(now,account,history,orders): return StrategyContext(now,account,dict(account.positions),account.base_cash,_History(history),orders)  # noqa: ANN001

    @staticmethod
    def _snapshot(run_id,account,at):  # noqa: ANN001
        positions=tuple(account.positions.values()); mv=sum((p.market_value for p in positions),Decimal(0))
        return PortfolioSnapshot(run_id,account.account_id,at,account.base_cash.settled,account.base_cash.unsettled_receivable-account.base_cash.unsettled_payable,
            account.base_cash.reserved,sum((abs(p.market_value) for p in positions),Decimal(0)),mv,mv,account.realized_pnl,account.unrealized_pnl,account.fees,account.equity,account.buying_power)

    @staticmethod
    def _validate(spec,bars):  # noqa: ANN001
        grouped={x:[] for x in spec.universe}
        for bar in bars:
            if bar.instrument not in grouped: raise ValueError(f"INSTRUMENT_DATA_NOT_FOUND: {bar.instrument.key}")
            if spec.data_version_id and bar.data_version_id != spec.data_version_id: raise ValueError("VERIFIED_DATA_MISSING: data version mismatch")
            grouped[bar.instrument].append(bar)
        for instrument,values in grouped.items():
            if not values: raise ValueError(f"INSTRUMENT_DATA_NOT_FOUND: {instrument.key}")
            if values != sorted(values,key=lambda x:x.ts_open): raise ValueError("VERIFIED_DATA_MISSING: sessions are not monotonic")
            if len({x.ts_open.date() for x in values}) != len(values): raise ValueError("DUPLICATE_BAR")
        if spec.verification_level.value == "VERIFIED":
            expected = sorted({bar.ts_open.date() for bar in bars})
            for instrument, values in grouped.items():
                present = {bar.ts_open.date() for bar in values}
                missing = [day.isoformat() for day in expected if day not in present]
                if missing:
                    raise ValueError(
                        f"VERIFIED_DATA_MISSING: instrument={instrument.key}; missing_sessions={missing}"
                    )
