from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from statistics import mean, pstdev
from typing import Any
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models import VirtualOrder, VirtualOrderStatus, VirtualPortfolio, VirtualPosition, VirtualTrade
from backend.simulation.adapters.live_tick_adapter import instrument_from_legacy_symbol
from backend.simulation.adapters.paper_legacy_adapter import PaperLegacyProjection
from backend.simulation.domain.account import AccountState, SettlementObligation
from backend.simulation.domain.cash import CashBalance
from backend.simulation.domain.enums import (
    EventType,
    LedgerEntryType,
    OrderSide,
    OrderStatus,
    OrderType,
    SimulationMode,
    SimulationRunStatus,
    TimeInForce,
    VerificationLevel,
)
from backend.simulation.domain.events import LedgerEntry
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.orders import Order
from backend.simulation.domain.paper import PaperSessionSpec
from backend.simulation.domain.positions import Position
from backend.simulation.domain.results import PortfolioSnapshot, PositionSnapshot
from backend.simulation.domain.ticks import MarketTick
from backend.simulation.engine.paper_execution import PaperExecutionEngine
from backend.simulation.execution.commissions import BpsCommissionModel, FixedCommissionModel
from backend.simulation.execution.fixed_bps import FixedBpsExecutionModel
from backend.simulation.execution.volume_participation import VolumeParticipationExecutionModel
from backend.simulation.persistence.models import (
    SimulationEventORM,
    SimulationFillORM,
    SimulationLedgerEntryORM,
    SimulationOrderORM,
    SimulationPortfolioSnapshotORM,
    SimulationPositionSnapshotORM,
    SimulationRunORM,
)
from backend.simulation.persistence.paper_repositories import PaperSettlementRepository
from backend.simulation.persistence.reconciliation_repositories import ExecutionObservationRepository
from backend.simulation.persistence.serializers import to_primitive
from backend.simulation.services.manifest_service import sha256_value

PAPER_ENGINE_VERSION = "sim-paper-v2a"
DEFAULT_EXECUTION_PROFILE = {"model": "fixed_bps", "slippage_bps": "5", "max_participation": "1"}
DEFAULT_COMMISSION_PROFILE = {"model": "bps", "bps": "5"}
DEFAULT_SETTLEMENT_PROFILE = {"settlement_days": 1}

_RUN_LOCKS: dict[str, asyncio.Lock] = {}
_MARKS: dict[str, dict[InstrumentId, Decimal]] = {}
logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None and value.utcoffset() is not None else value.replace(tzinfo=timezone.utc)


def _decimal(value: Any) -> Decimal:
    # SQLite's NUMERIC adapter round-trips through binary float. Normalize that
    # adapter noise while retaining substantially more precision than currencies use.
    return Decimal(str(value)).quantize(Decimal("0.00000001")).normalize()


class PaperSimulationService:
    """Transactional canonical PAPER service with legacy API projections."""

    def __init__(self, db: Session, *, max_cached_tick_age_seconds: int = 15):
        self.db = db
        self.max_cached_tick_age_seconds = max_cached_tick_age_seconds
        self.projection = PaperLegacyProjection()
        self.settlements = PaperSettlementRepository(db)
        self.observations = ExecutionObservationRepository(db)

    @staticmethod
    def lock_for(run_id: str) -> asyncio.Lock:
        return _RUN_LOCKS.setdefault(run_id, asyncio.Lock())

    def create_portfolio(
        self,
        *,
        user_id: str,
        name: str,
        initial_cash: Decimal,
        base_currency: str = "INR",
        strategy_key: str = "manual:paper",
        strategy_context: dict[str, Any] | None = None,
        execution_profile: dict[str, Any] | None = None,
        commission_profile: dict[str, Any] | None = None,
        settlement_profile: dict[str, Any] | None = None,
    ) -> VirtualPortfolio:
        started_at = _now()
        portfolio = VirtualPortfolio(
            user_id=user_id,
            name=name.strip() or "Paper Portfolio",
            initial_capital=float(initial_cash),
            current_cash=float(initial_cash),
            is_active=True,
        )
        self.db.add(portfolio)
        self.db.flush()
        spec = PaperSessionSpec(
            portfolio_id=portfolio.id,
            initial_cash=initial_cash,
            base_currency=base_currency,
            execution_profile=dict(execution_profile or DEFAULT_EXECUTION_PROFILE),
            commission_profile=dict(commission_profile or DEFAULT_COMMISSION_PROFILE),
            settlement_profile=dict(settlement_profile or DEFAULT_SETTLEMENT_PROFILE),
            started_at=started_at,
            strategy_key=strategy_key,
            strategy_context=dict(strategy_context or {}),
        )
        run_id = f"sim_{uuid4().hex[:12]}"
        account_id = f"acct_{run_id[4:]}"
        request = to_primitive(spec)
        manifest_basis = {
            "engine_version": PAPER_ENGINE_VERSION,
            "git_commit": None,
            "strategy_hash": sha256_value({"key": spec.strategy_key, "context": spec.strategy_context}),
            "strategy_key": spec.strategy_key,
            "strategy_context_hash": sha256_value(spec.strategy_context),
            "data_version_id": None,
            "dataset_hash": None,
            "universe_hash": sha256_value([]),
            "corporate_actions_hash": None,
            "calendar_version": None,
            "execution_profile_hash": sha256_value(spec.execution_profile),
            "commission_profile_hash": sha256_value(spec.commission_profile),
            "settlement_profile_hash": sha256_value(spec.settlement_profile),
            "daily_bar_path_policy": "WORST_CASE",
            "seed": 0,
            "request_hash": sha256_value(request),
        }
        manifest = {
            "run_id": run_id,
            **manifest_basis,
            "manifest_hash": sha256_value(manifest_basis),
            "created_at": started_at.isoformat(),
        }
        self.db.add(
            SimulationRunORM(
                id=run_id,
                mode=SimulationMode.PAPER.value,
                verification_level=VerificationLevel.RESEARCH.value,
                status=SimulationRunStatus.RUNNING.value,
                strategy_key=spec.strategy_key,
                strategy_hash=manifest_basis["strategy_hash"],
                code_hash=None,
                data_version_id=None,
                engine_version=PAPER_ENGINE_VERSION,
                seed=0,
                request_json=request,
                manifest_json=manifest,
                created_at=started_at,
                started_at=started_at,
            )
        )
        self.db.flush()
        portfolio.simulation_run_id = run_id
        account = AccountState(
            account_id=account_id,
            base_currency=spec.base_currency,
            cash={spec.base_currency: CashBalance(spec.base_currency, settled=spec.initial_cash)},
            equity=spec.initial_cash,
            buying_power=spec.initial_cash,
        )
        opening = LedgerEntry(
            id=f"led_{run_id}_opening",
            run_id=run_id,
            account_id=account_id,
            ts=started_at,
            entry_type=LedgerEntryType.CASH_DEPOSIT,
            currency=spec.base_currency,
            amount=spec.initial_cash,
            metadata={"reason": "paper_portfolio_opening_cash"},
        )
        self._save_ledger(opening)
        self._append_event(run_id, EventType.LEDGER_ENTRY, started_at, payload={"ledger_entry_id": opening.id})
        self._save_snapshot(run_id, account, started_at)
        self._append_event(run_id, EventType.PORTFOLIO_SNAPSHOT, started_at, payload={"opening": True})
        self.db.commit()
        self.db.refresh(portfolio)
        return portfolio

    async def submit_order(
        self,
        *,
        portfolio: VirtualPortfolio,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        limit_price: Decimal | None,
        stop_price: Decimal | None,
        slippage_bps: Decimal,
        commission: Decimal,
        cached_tick: MarketTick | None = None,
        submitted_at: datetime | None = None,
        reconciliation_key: str | None = None,
        strategy_order_id: str | None = None,
    ) -> VirtualOrder:
        if not portfolio.simulation_run_id:
            raise ValueError("PAPER_PORTFOLIO_MIGRATION_REQUIRED")
        run_id = portfolio.simulation_run_id
        async with self.lock_for(run_id):
            try:
                now = submitted_at or _now()
                instrument = instrument_from_legacy_symbol(symbol)
                account = self._load_account(run_id)
                self._process_due_settlements(portfolio, account, now.date(), now)
                canonical_type = {"market": OrderType.MARKET, "limit": OrderType.LIMIT, "sl": OrderType.STOP}[order_type]
                canonical_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
                sequence = self._next_sequence(run_id)
                order_id = f"ord_{run_id[4:]}_{sequence}"
                virtual = VirtualOrder(
                    portfolio_id=portfolio.id,
                    symbol=f"{instrument.venue}:{instrument.symbol}",
                    side=side,
                    order_type=order_type,
                    quantity=float(quantity),
                    limit_price=float(limit_price) if limit_price is not None else None,
                    sl_price=float(stop_price) if stop_price is not None else None,
                    status=VirtualOrderStatus.PENDING.value,
                    slippage_bps=float(slippage_bps),
                    commission=float(commission),
                )
                self.db.add(virtual)
                self.db.flush()
                order = Order(
                    id=order_id,
                    run_id=run_id,
                    account_id=account.account_id,
                    instrument=instrument,
                    side=canonical_side,
                    order_type=canonical_type,
                    quantity=quantity,
                    remaining_quantity=quantity,
                    tif=TimeInForce.GTC,
                    submitted_at=now,
                    limit_price=limit_price,
                    stop_price=stop_price,
                    strategy_order_id=strategy_order_id,
                    metadata={
                        "virtual_order_id": virtual.id,
                        "slippage_bps": str(slippage_bps),
                        "commission": str(commission),
                        **({"reconciliation_key": reconciliation_key} if reconciliation_key else {}),
                    },
                )
                self._append_event(run_id, EventType.ORDER_SUBMITTED, now, order_id=order.id)
                execution_model = self._execution_model(order)
                commission_model = self._commission_model(order)
                fresh_tick = cached_tick if self._fresh(cached_tick, now) and cached_tick.instrument == instrument else None
                if fresh_tick is not None and fresh_tick.ts < now:
                    # A permitted fresh cache is evaluated at acceptance time; an
                    # older tick is never represented as a post-order market event.
                    fresh_tick = replace(fresh_tick, ts=now, source=f"{fresh_tick.source or 'live'}:fresh-cache")
                reserve_price = limit_price or stop_price or (fresh_tick.price if fresh_tick else None)
                try:
                    engine = self._engine_for(run_id)
                    order = engine.accept(
                        account,
                        order,
                        accepted_at=now,
                        reserve_price=reserve_price,
                        execution_model=execution_model,
                        commission_model=commission_model,
                    )
                    self._append_event(run_id, EventType.ORDER_ACCEPTED, now, order_id=order.id)
                except ValueError as exc:
                    order = replace(order, status=OrderStatus.REJECTED, completed_at=now, metadata={**order.metadata, "rejection": str(exc)})
                    self._append_event(run_id, EventType.ORDER_REJECTED, now, order_id=order.id, payload={"reason": str(exc)})
                self._save_order(order)
                self.db.flush()
                self.projection.project_order(virtual, order)
                self.projection.project_account(self.db, portfolio, account)
                self._save_snapshot(run_id, account, now)
                if order.status is OrderStatus.ACCEPTED and fresh_tick is not None:
                    self._apply_tick_to_order(portfolio, virtual, account, order, fresh_tick)
                self.db.commit()
                self.db.refresh(virtual)
                return virtual
            except Exception:
                self.db.rollback()
                raise

    async def cancel_order(self, portfolio: VirtualPortfolio, virtual_order: VirtualOrder, *, at: datetime | None = None) -> VirtualOrder:
        if not portfolio.simulation_run_id or not virtual_order.simulation_order_id:
            raise ValueError("PAPER_PORTFOLIO_MIGRATION_REQUIRED")
        run_id = portfolio.simulation_run_id
        async with self.lock_for(run_id):
            try:
                row = self.db.get(SimulationOrderORM, virtual_order.simulation_order_id)
                if row is None:
                    raise ValueError("PAPER_SESSION_NOT_FOUND")
                order = self._domain_order(row)
                if order.status in {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.EXPIRED, OrderStatus.REJECTED}:
                    raise ValueError("INVALID_ORDER: terminal order cannot be cancelled")
                now = at or _now()
                account = self._load_account(run_id)
                order = self._engine_for(run_id).cancel(account, order, at=now)
                self._save_order(order)
                self.projection.project_order(virtual_order, order)
                self.projection.project_account(self.db, portfolio, account)
                self._append_event(run_id, EventType.ORDER_CANCELLED, now, order_id=order.id)
                self._save_snapshot(run_id, account, now)
                self.db.commit()
                self.db.refresh(virtual_order)
                return virtual_order
            except Exception:
                self.db.rollback()
                raise

    async def consume_market_tick(self, tick: MarketTick) -> int:
        rows = (
            self.db.query(VirtualPortfolio)
            .join(SimulationRunORM, VirtualPortfolio.simulation_run_id == SimulationRunORM.id)
            .filter(
                SimulationRunORM.mode == SimulationMode.PAPER.value,
                SimulationRunORM.status == SimulationRunStatus.RUNNING.value,
            )
            .all()
        )
        processed = 0
        for portfolio in rows:
            run_id = portfolio.simulation_run_id
            async with self.lock_for(run_id):
                try:
                    _MARKS.setdefault(run_id, {})[tick.instrument] = tick.price
                    account = self._load_account(run_id)
                    self._process_due_settlements(portfolio, account, tick.ts.date(), tick.ts)
                    order_rows = (
                        self.db.query(SimulationOrderORM)
                        .filter(
                            SimulationOrderORM.run_id == run_id,
                            SimulationOrderORM.instrument_key == tick.instrument.key,
                            SimulationOrderORM.status.in_([OrderStatus.ACCEPTED.value, OrderStatus.PARTIALLY_FILLED.value]),
                        )
                        .order_by(SimulationOrderORM.submitted_at, SimulationOrderORM.id)
                        .all()
                    )
                    for row in order_rows:
                        virtual = self.db.query(VirtualOrder).filter_by(simulation_order_id=row.id).first()
                        if virtual and self._apply_tick_to_order(portfolio, virtual, account, self._domain_order(row), tick):
                            processed += 1
                    self.db.commit()
                except Exception:
                    self.db.rollback()
                    logger.exception(
                        "Canonical paper tick failed for one session",
                        extra={"run_id": run_id, "instrument": tick.instrument.key},
                    )
        return processed

    async def current_account(self, portfolio: VirtualPortfolio, *, at: datetime | None = None) -> AccountState:
        if not portfolio.simulation_run_id:
            raise ValueError("PAPER_PORTFOLIO_MIGRATION_REQUIRED")
        run_id = portfolio.simulation_run_id
        async with self.lock_for(run_id):
            now = at or _now()
            account = self._load_account(run_id)
            if self._process_due_settlements(portfolio, account, now.date(), now):
                self.db.commit()
            self._engine_for(run_id).valuation_engine.value(account, _MARKS.get(run_id, {}))
            return account

    async def performance(self, portfolio: VirtualPortfolio) -> dict[str, Any]:
        account = await self.current_account(portfolio)
        trades = (
            self.db.query(VirtualTrade)
            .filter_by(portfolio_id=portfolio.id)
            .order_by(VirtualTrade.timestamp)
            .all()
        )
        realized = [_decimal(row.pnl_realized) for row in trades if row.pnl_realized is not None]
        wins = [value for value in realized if value > 0]
        losses = [value for value in realized if value < 0]
        snapshots = (
            self.db.query(SimulationPortfolioSnapshotORM)
            .filter_by(run_id=portfolio.simulation_run_id)
            .order_by(SimulationPortfolioSnapshotORM.snapshot_time)
            .all()
        )
        curve = [{"t": _aware(row.snapshot_time).isoformat(), "equity": float(row.equity)} for row in snapshots]
        returns: list[float] = []
        for previous, current in zip(snapshots, snapshots[1:]):
            if previous.equity:
                returns.append(float((current.equity - previous.equity) / previous.equity))
        peak = Decimal("0")
        max_drawdown = Decimal("0")
        for row in snapshots:
            equity = _decimal(row.equity)
            peak = max(peak, equity)
            if peak:
                max_drawdown = min(max_drawdown, (equity - peak) / peak)
        sharpe = mean(returns) / pstdev(returns) * (252**0.5) if len(returns) > 1 and pstdev(returns) else 0.0
        initial = _decimal(portfolio.initial_capital)
        pnl = account.equity - initial
        return {
            "portfolio_id": portfolio.id,
            "equity": float(account.equity),
            "cash": float(account.base_cash.available),
            "settled_cash": float(account.base_cash.settled),
            "unsettled_cash": float(account.base_cash.unsettled_receivable),
            "buying_power": float(account.buying_power),
            "fees": float(account.fees),
            "realized_pnl": float(account.realized_pnl),
            "unrealized_pnl": float(account.unrealized_pnl),
            "pnl": float(pnl),
            "cumulative_return": float(pnl / initial) if initial else 0.0,
            "daily_pnl_curve": curve,
            "sharpe_ratio": sharpe,
            "max_drawdown": float(max_drawdown),
            "win_rate": len(wins) / len(realized) if realized else 0.0,
            "avg_win_loss_ratio": float((sum(wins) / len(wins)) / abs(sum(losses) / len(losses))) if wins and losses else 0.0,
            "profit_factor": float(sum(wins) / abs(sum(losses))) if losses else (float("inf") if wins else 0.0),
            "trade_count": len(trades),
        }

    def _apply_tick_to_order(self, portfolio, virtual, account, order, tick) -> bool:  # noqa: ANN001
        engine = self._engine_for(order.run_id)
        result = engine.execute(
            account,
            order,
            tick,
            execution_model=self._execution_model(order),
            commission_model=self._commission_model(order),
            fill_id=f"fill_{uuid4().hex[:16]}",
        )
        if result is None:
            return False
        if result.triggered:
            self._append_event(order.run_id, EventType.ORDER_TRIGGERED, tick.ts, order_id=order.id)
        self.db.add(
            SimulationFillORM(
                id=result.fill.id,
                run_id=result.fill.run_id,
                order_id=result.fill.order_id,
                account_id=result.fill.account_id,
                instrument_key=result.fill.instrument.key,
                side=result.fill.side.value,
                quantity=result.fill.quantity,
                price=result.fill.price,
                commission=result.fill.commission,
                fees=result.fill.fees,
                slippage_bps=result.fill.slippage_bps,
                executed_at=result.fill.executed_at,
                execution_model=result.fill.execution_model,
                liquidity_flag=result.fill.liquidity_flag,
                metadata_json={"liquidity_assumption": result.liquidity_assumption, "source": tick.source},
            )
        )
        self.observations.create_from_fill_tick(
            run_id=order.run_id,
            order_id=order.id,
            fill_id=result.fill.id,
            tick=tick,
            liquidity_assumption=result.liquidity_assumption,
        )
        for entry in result.ledger:
            self._save_ledger(entry)
            self._append_event(order.run_id, EventType.LEDGER_ENTRY, tick.ts, order_id=order.id, fill_id=result.fill.id, payload={"ledger_entry_id": entry.id})
        for obligation in account.settlements:
            if obligation.fill_id == result.fill.id:
                self.settlements.create(
                    obligation_id=f"set_{result.fill.id}",
                    run_id=order.run_id,
                    account_id=account.account_id,
                    fill_id=result.fill.id,
                    currency=obligation.currency,
                    amount=obligation.amount,
                    settlement_date=obligation.settlement_date,
                    created_at=tick.ts,
                )
        self._save_order(result.order)
        self.projection.project_order(virtual, result.order, fill=result.fill)
        self.projection.project_fill(
            self.db,
            portfolio=portfolio,
            order_row=virtual,
            fill=result.fill,
            realized_pnl=result.realized_pnl_delta,
        )
        engine.valuation_engine.value(account, _MARKS.get(order.run_id, {tick.instrument: tick.price}))
        self.projection.project_account(self.db, portfolio, account)
        event_type = EventType.ORDER_FILL if result.order.status is OrderStatus.FILLED else EventType.ORDER_PARTIAL_FILL
        self._append_event(order.run_id, event_type, tick.ts, order_id=order.id, fill_id=result.fill.id)
        self._save_snapshot(order.run_id, account, tick.ts)
        self._append_event(order.run_id, EventType.PORTFOLIO_SNAPSHOT, tick.ts, order_id=order.id, fill_id=result.fill.id)
        return True

    def _process_due_settlements(self, portfolio, account, session: date, at: datetime) -> bool:  # noqa: ANN001
        due = self.settlements.due(portfolio.simulation_run_id, session)
        if not due:
            return False
        settled_ids = self._engine_for(portfolio.simulation_run_id).settle(account, session)
        for row in due:
            if row.fill_id not in settled_ids:
                continue
            self.settlements.mark_settled(row, at)
            entry = LedgerEntry(
                id=f"led_{row.id}_settled",
                run_id=row.run_id,
                account_id=row.account_id,
                ts=at,
                entry_type=LedgerEntryType.SETTLEMENT,
                currency=row.currency,
                amount=Decimal("0"),
                fill_id=row.fill_id,
                metadata={"settled_amount": str(row.amount)},
            )
            self._save_ledger(entry)
            self._append_event(row.run_id, EventType.SETTLEMENT, at, fill_id=row.fill_id, payload={"amount": str(row.amount)})
        self.projection.project_account(self.db, portfolio, account)
        self._save_snapshot(portfolio.simulation_run_id, account, at)
        return True

    def _load_account(self, run_id: str) -> AccountState:
        run = self.db.get(SimulationRunORM, run_id)
        if run is None or run.mode != SimulationMode.PAPER.value:
            raise ValueError("PAPER_SESSION_NOT_FOUND")
        request = dict(run.request_json or {})
        currency = str(request.get("base_currency") or "INR")
        latest = (
            self.db.query(SimulationPortfolioSnapshotORM)
            .filter_by(run_id=run_id)
            .order_by(SimulationPortfolioSnapshotORM.snapshot_time.desc(), SimulationPortfolioSnapshotORM.id.desc())
            .first()
        )
        if latest is None:
            raise ValueError("PAPER_SESSION_NOT_FOUND: account snapshot missing")
        account = AccountState(
            account_id=latest.account_id,
            base_currency=currency,
            cash={
                currency: CashBalance(
                    currency,
                    settled=_decimal(latest.cash_settled),
                    unsettled_receivable=_decimal(latest.cash_unsettled),
                    reserved=_decimal(latest.cash_reserved),
                )
            },
            realized_pnl=_decimal(latest.realized_pnl),
            unrealized_pnl=_decimal(latest.unrealized_pnl),
            equity=_decimal(latest.equity),
            buying_power=_decimal(latest.buying_power),
            fees=_decimal(latest.fees),
        )
        seen: set[str] = set()
        position_rows = (
            self.db.query(SimulationPositionSnapshotORM)
            .filter_by(run_id=run_id)
            .order_by(SimulationPositionSnapshotORM.snapshot_time.desc(), SimulationPositionSnapshotORM.id.desc())
            .all()
        )
        for row in position_rows:
            if row.instrument_key in seen:
                continue
            seen.add(row.instrument_key)
            instrument = InstrumentId.parse(row.instrument_key)
            account.positions[instrument] = Position(
                instrument=instrument,
                quantity=_decimal(row.quantity),
                average_cost=_decimal(row.average_cost),
                realized_pnl=_decimal(row.realized_pnl),
                unrealized_pnl=_decimal(row.unrealized_pnl),
                market_value=_decimal(row.market_value),
                last_mark=_decimal(row.mark_price) if row.mark_price is not None else None,
            )
        for row in self.settlements.outstanding(run_id):
            account.settlements.append(
                SettlementObligation(row.settlement_date, row.currency, _decimal(row.amount), row.fill_id)
            )
        open_rows = (
            self.db.query(SimulationOrderORM)
            .filter(
                SimulationOrderORM.run_id == run_id,
                SimulationOrderORM.status.in_([OrderStatus.ACCEPTED.value, OrderStatus.PARTIALLY_FILLED.value]),
            )
            .all()
        )
        for row in open_rows:
            order = self._domain_order(row)
            account.open_orders[order.id] = order
        return account

    def _save_snapshot(self, run_id: str, account: AccountState, at: datetime) -> None:
        latest_time = (
            self.db.query(func.max(SimulationPortfolioSnapshotORM.snapshot_time))
            .filter_by(run_id=run_id)
            .scalar()
        )
        latest_time = _aware(latest_time)
        if latest_time is not None and at <= latest_time:
            at = latest_time + timedelta(microseconds=1)
        marks = _MARKS.get(run_id, {})
        PaperExecutionEngine().valuation_engine.value(account, marks)
        market_value = sum((position.market_value for position in account.positions.values()), Decimal("0"))
        snapshot = PortfolioSnapshot(
            run_id=run_id,
            account_id=account.account_id,
            snapshot_time=at,
            cash_settled=account.base_cash.settled,
            cash_unsettled=account.base_cash.unsettled_receivable,
            cash_reserved=account.base_cash.reserved,
            gross_exposure=sum((abs(position.market_value) for position in account.positions.values()), Decimal("0")),
            net_exposure=market_value,
            market_value=market_value,
            realized_pnl=account.realized_pnl,
            unrealized_pnl=account.unrealized_pnl,
            fees=account.fees,
            equity=account.equity,
            buying_power=account.buying_power,
        )
        self.db.add(
            SimulationPortfolioSnapshotORM(
                run_id=snapshot.run_id,
                account_id=snapshot.account_id,
                snapshot_time=snapshot.snapshot_time,
                cash_settled=snapshot.cash_settled,
                cash_unsettled=snapshot.cash_unsettled,
                cash_reserved=snapshot.cash_reserved,
                gross_exposure=snapshot.gross_exposure,
                net_exposure=snapshot.net_exposure,
                market_value=snapshot.market_value,
                realized_pnl=snapshot.realized_pnl,
                unrealized_pnl=snapshot.unrealized_pnl,
                fees=snapshot.fees,
                equity=snapshot.equity,
                buying_power=snapshot.buying_power,
            )
        )
        for instrument, position in account.positions.items():
            mark = marks.get(instrument, position.last_mark or position.average_cost)
            item = PositionSnapshot(
                run_id=run_id,
                account_id=account.account_id,
                snapshot_time=at,
                instrument=instrument,
                quantity=position.quantity,
                average_cost=position.average_cost,
                mark_price=mark,
                market_value=position.quantity * mark,
                realized_pnl=position.realized_pnl,
                unrealized_pnl=position.quantity * (mark - position.average_cost),
            )
            self.db.add(
                SimulationPositionSnapshotORM(
                    run_id=item.run_id,
                    account_id=item.account_id,
                    snapshot_time=item.snapshot_time,
                    instrument_key=instrument.key,
                    quantity=item.quantity,
                    average_cost=item.average_cost,
                    mark_price=item.mark_price,
                    market_value=item.market_value,
                    realized_pnl=item.realized_pnl,
                    unrealized_pnl=item.unrealized_pnl,
                )
            )

    def _save_order(self, order: Order) -> None:
        row = self.db.get(SimulationOrderORM, order.id)
        if row is None:
            row = SimulationOrderORM(id=order.id, run_id=order.run_id)
        row.account_id = order.account_id
        row.instrument_key = order.instrument.key
        row.side = order.side.value
        row.order_type = order.order_type.value
        row.quantity = order.quantity
        row.remaining_quantity = order.remaining_quantity
        row.tif = order.tif.value
        row.limit_price = order.limit_price
        row.stop_price = order.stop_price
        row.status = order.status.value
        row.submitted_at = order.submitted_at
        row.accepted_at = order.accepted_at
        row.completed_at = order.completed_at
        row.strategy_order_id = order.strategy_order_id
        row.parent_order_id = order.parent_order_id
        row.metadata_json = to_primitive({**order.metadata, "eligible_at": order.eligible_at})
        self.db.add(row)

    def _save_ledger(self, entry: LedgerEntry) -> None:
        self.db.add(
            SimulationLedgerEntryORM(
                id=entry.id,
                run_id=entry.run_id,
                account_id=entry.account_id,
                event_time=entry.ts,
                entry_type=entry.entry_type.value,
                currency=entry.currency,
                amount=entry.amount,
                instrument_key=entry.instrument.key if entry.instrument else None,
                order_id=entry.order_id,
                fill_id=entry.fill_id,
                corporate_action_id=entry.corporate_action_id,
                metadata_json=to_primitive(entry.metadata),
            )
        )

    def _append_event(self, run_id: str, event_type: EventType, at: datetime, *, order_id: str | None = None, fill_id: str | None = None, payload: dict[str, Any] | None = None) -> None:
        sequence = self._next_sequence(run_id)
        self.db.add(
            SimulationEventORM(
                run_id=run_id,
                sequence=sequence,
                event_id=f"evt_{run_id[4:]}_{sequence}",
                event_type=event_type.value,
                event_time=at,
                processing_time=_now(),
                order_id=order_id,
                fill_id=fill_id,
                payload_json=payload or {},
            )
        )
        self.db.flush()

    def _next_sequence(self, run_id: str) -> int:
        return int(self.db.query(func.coalesce(func.max(SimulationEventORM.sequence), 0)).filter_by(run_id=run_id).scalar()) + 1

    def _engine_for(self, run_id: str) -> PaperExecutionEngine:
        run = self.db.get(SimulationRunORM, run_id)
        days = int(dict(run.request_json or {}).get("settlement_profile", {}).get("settlement_days", 1))
        return PaperExecutionEngine(settlement_days=days)

    @staticmethod
    def _domain_order(row: SimulationOrderORM) -> Order:
        metadata = dict(row.metadata_json or {})
        eligible_raw = metadata.pop("eligible_at", None)
        eligible = datetime.fromisoformat(eligible_raw) if isinstance(eligible_raw, str) else _aware(eligible_raw)
        if eligible is not None:
            eligible = _aware(eligible)
        return Order(
            id=row.id,
            run_id=row.run_id,
            account_id=row.account_id,
            instrument=InstrumentId.parse(row.instrument_key),
            side=OrderSide(row.side),
            order_type=OrderType(row.order_type),
            quantity=_decimal(row.quantity),
            remaining_quantity=_decimal(row.remaining_quantity),
            tif=TimeInForce(row.tif),
            submitted_at=_aware(row.submitted_at),
            accepted_at=_aware(row.accepted_at),
            eligible_at=eligible,
            completed_at=_aware(row.completed_at),
            limit_price=_decimal(row.limit_price) if row.limit_price is not None else None,
            stop_price=_decimal(row.stop_price) if row.stop_price is not None else None,
            status=OrderStatus(row.status),
            strategy_order_id=row.strategy_order_id,
            parent_order_id=row.parent_order_id,
            metadata=metadata,
        )

    @staticmethod
    def _execution_model(order: Order):  # noqa: ANN205
        bps = _decimal(order.metadata.get("slippage_bps", "5"))
        participation = _decimal(order.metadata.get("max_participation", "1"))
        if participation < 1:
            return VolumeParticipationExecutionModel(max_participation=participation, base_slippage_bps=bps)
        return FixedBpsExecutionModel(slippage_bps=bps, max_participation=participation)

    @staticmethod
    def _commission_model(order: Order):  # noqa: ANN205
        fixed = _decimal(order.metadata.get("commission", "0"))
        return FixedCommissionModel(fixed) if fixed > 0 else BpsCommissionModel(Decimal("5"))

    def _fresh(self, tick: MarketTick | None, now: datetime) -> bool:
        if tick is None or tick.ts > now:
            return False
        return (now - tick.ts).total_seconds() <= self.max_cached_tick_age_seconds
