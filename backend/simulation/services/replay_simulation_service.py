from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models import DataVersionORM
from backend.simulation.adapters.strategy_runner_adapter import StrategyRunnerAdapter
from backend.simulation.domain.account import AccountState, SettlementObligation
from backend.simulation.domain.cash import CashBalance
from backend.simulation.domain.enums import (
    EventType, LedgerEntryType, OrderSide, OrderStatus, OrderType, SimulationMode,
    SimulationRunStatus, TimeInForce, VerificationLevel,
)
from backend.simulation.domain.events import LedgerEntry, SimulationEvent
from backend.simulation.domain.fills import Fill
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.orders import Order
from backend.simulation.domain.positions import Position
from backend.simulation.domain.replay import ReplayControlStatus, ReplayState
from backend.simulation.domain.results import PortfolioSnapshot, PositionSnapshot
from backend.simulation.domain.run import RunManifest, SimulationRunSpec
from backend.simulation.engine.daily_simulator import DailySimulator
from backend.simulation.engine.daily_session_kernel import DailySessionKernel, DailySessionState
from backend.simulation.engine.result_builder import ResultBuilder
from backend.simulation.persistence.models import (
    SimulationAppliedCorporateActionORM, SimulationEventORM, SimulationFillORM, SimulationLedgerEntryORM, SimulationOrderORM,
    SimulationPortfolioSnapshotORM, SimulationPositionSnapshotORM, SimulationReplaySessionORM,
    SimulationRunORM, SimulationSettlementObligationORM,
)
from backend.simulation.persistence.replay_repositories import (
    ReplayEventStore, ReplayLedgerRepository, ReplayRecordRepository,
)
from backend.simulation.persistence.corporate_action_repositories import CorporateActionRepository
from backend.simulation.persistence.serializers import to_primitive
from backend.simulation.services.manifest_service import ManifestService, sha256_value
from backend.simulation.services.reconciliation_service import ReconciliationService
from backend.simulation.services.simulator_factory import build_daily_simulator


REPLAY_ENGINE_VERSION = "sim-daily-v1b"
_REPLAY_LOCKS: dict[str, asyncio.Lock] = {}


class ReplaySimulationError(ValueError):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None and value.utcoffset() is not None else value.replace(tzinfo=timezone.utc)


class ReplaySimulationService:
    """Restart-safe session-at-a-time orchestration over the shared daily kernel."""

    def __init__(self, db: Session, *, failure_hook: Callable[[str, date], None] | None = None):
        self.db = db
        self.failure_hook = failure_hook

    @staticmethod
    def lock_for(run_id: str) -> asyncio.Lock:
        return _REPLAY_LOCKS.setdefault(run_id, asyncio.Lock())

    async def create(self, spec: SimulationRunSpec) -> str:
        if spec.mode is not SimulationMode.REPLAY:
            raise ReplaySimulationError("REPLAY_MODE_INVALID")
        if spec.verification_level is VerificationLevel.SYNTHETIC:
            raise ReplaySimulationError("REPLAY_SYNTHETIC_UNSUPPORTED")
        if not spec.data_version_id:
            raise ReplaySimulationError("REPLAY_DATA_VERSION_REQUIRED")
        version = self.db.get(DataVersionORM, spec.data_version_id)
        if version is None:
            raise ReplaySimulationError("REPLAY_DATA_MISSING", f"data version {spec.data_version_id} not found")
        if str(version.source).strip().lower() in {"synthetic", "generated", "demo"}:
            raise ReplaySimulationError("REPLAY_SYNTHETIC_UNSUPPORTED")
        try:
            simulator = build_daily_simulator(self.db, spec)
            bars = list(simulator.d.market_data.iter_daily_events(list(spec.universe), spec.start, spec.end))
            actions = list(simulator.d.corporate_actions.events(
                list(spec.universe), spec.start, spec.end, spec.data_version_id,
                verification_level=spec.verification_level,
            ))
            DailySimulator._validate(spec, bars, actions=actions, manifest=simulator.d.market_data.manifest())
        except ReplaySimulationError:
            raise
        except Exception as exc:
            code = str(exc).split(":", 1)[0]
            if code.startswith("CORPORATE_ACTION_") or code in {
                "INVALID_OHLC", "DUPLICATE_BAR", "VERIFIED_DATA_MISSING",
                "ADJUSTED_DATA_CORPORATE_ACTION_CONFLICT",
            }:
                raise ReplaySimulationError(code, str(exc)) from exc
            raise ReplaySimulationError("REPLAY_DATA_MISSING", str(exc)) from exc
        sessions = sorted({bar.ts_open.date() for bar in bars})
        if not sessions:
            raise ReplaySimulationError("REPLAY_DATA_MISSING")
        run_id = f"sim_{uuid4().hex[:12]}"
        metadata = dict(version.metadata_json or {})
        manifest = ManifestService(engine_version=REPLAY_ENGINE_VERSION).build(
            run_id, spec, dataset_hash=metadata.get("dataset_hash"),
            calendar_version=metadata.get("calendar_version"),
            created_at=min(bar.ts_open for bar in bars),
        )
        started = _now()
        account_id = f"acct_{run_id[4:]}"
        try:
            self.db.add(SimulationRunORM(
                id=run_id, mode=SimulationMode.REPLAY.value,
                verification_level=spec.verification_level.value,
                status=SimulationRunStatus.RUNNING.value, strategy_key=spec.strategy,
                strategy_hash=manifest.strategy_hash, code_hash=manifest.git_commit,
                data_version_id=spec.data_version_id, engine_version=manifest.engine_version,
                seed=spec.seed, request_json=to_primitive(spec), manifest_json=to_primitive(manifest),
                created_at=manifest.created_at, started_at=started,
            ))
            self.db.add(SimulationReplaySessionORM(
                run_id=run_id, control_status=ReplayControlStatus.READY.value,
                start_session=sessions[0], end_session=sessions[-1], current_session=None,
                next_session=sessions[0], completed_sessions=0, total_sessions=len(sessions),
                last_event_sequence=0, strategy_state_json={}, initialized=False,
                finish_called=False, checkpoint_hash=None, created_at=started, updated_at=started,
            ))
            self.db.add(SimulationLedgerEntryORM(
                id=f"led_{run_id}_opening", run_id=run_id, account_id=account_id,
                event_time=min(bar.ts_open for bar in bars),
                entry_type=LedgerEntryType.CASH_DEPOSIT.value, currency=spec.base_currency,
                amount=spec.initial_cash, metadata_json={"opening_balance": True},
            ))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return run_id

    async def state(self, run_id: str) -> ReplayState:
        return self._state(self._require_replay(run_id))

    async def advance(self, run_id: str, *, sessions: int = 1) -> ReplayState:
        if not 1 <= sessions <= 100:
            raise ReplaySimulationError("REPLAY_ADVANCE_INVALID")
        async with self.lock_for(run_id):
            return self._advance_locked(run_id, sessions)

    async def run_to(self, run_id: str, *, target_session: date) -> ReplayState:
        async with self.lock_for(run_id):
            replay = self._require_replay(run_id)
            if replay.current_session == target_session:
                return self._state(replay)
            all_sessions = self._sessions(run_id)
            if target_session not in all_sessions:
                raise ReplaySimulationError("REPLAY_TARGET_INVALID")
            target_index = all_sessions.index(target_session)
            if target_index < replay.completed_sessions:
                raise ReplaySimulationError("REPLAY_TARGET_INVALID")
            return self._advance_locked(run_id, target_index - replay.completed_sessions + 1)

    async def run_to_end(self, run_id: str) -> ReplayState:
        async with self.lock_for(run_id):
            replay = self._require_replay(run_id)
            return self._advance_locked(run_id, replay.total_sessions - replay.completed_sessions)

    async def cancel(self, run_id: str) -> ReplayState:
        async with self.lock_for(run_id):
            replay = self._require_replay(run_id)
            control = ReplayControlStatus(replay.control_status)
            if control is ReplayControlStatus.DONE:
                raise ReplaySimulationError("REPLAY_ALREADY_DONE")
            if control is ReplayControlStatus.CANCELLED:
                return self._state(replay)
            replay.control_status = ReplayControlStatus.CANCELLED.value
            replay.updated_at = _now()
            replay.completed_at = replay.updated_at
            run = self.db.get(SimulationRunORM, run_id)
            run.status = SimulationRunStatus.CANCELLED.value
            run.finished_at = replay.updated_at
            self.db.commit()
            return self._state(replay)

    async def market(self, run_id: str, instrument: InstrumentId, *, limit: int = 100) -> list[dict[str, Any]]:
        replay = self._require_replay(run_id)
        if replay.current_session is None:
            return []
        spec = self._spec(run_id)
        if instrument not in spec.universe:
            raise ReplaySimulationError("REPLAY_DATA_MISSING", "instrument is outside replay universe")
        simulator = build_daily_simulator(self.db, spec)
        bars = [
            bar for bar in simulator.d.market_data.iter_daily_events([instrument], spec.start, replay.current_session)
            if bar.ts_open.date() <= replay.current_session
        ]
        return [to_primitive(bar) for bar in bars[-limit:]]

    def _advance_locked(self, run_id: str, requested: int) -> ReplayState:
        replay = self._require_replay(run_id)
        control = ReplayControlStatus(replay.control_status)
        if control is ReplayControlStatus.DONE:
            raise ReplaySimulationError("REPLAY_ALREADY_DONE")
        if control is ReplayControlStatus.CANCELLED:
            raise ReplaySimulationError("REPLAY_CANCELLED")
        if control is ReplayControlStatus.FAILED:
            raise ReplaySimulationError("REPLAY_FAILED")
        remaining = replay.total_sessions - replay.completed_sessions
        for _ in range(min(requested, remaining)):
            self._process_one(run_id)
        return self._state(self._require_replay(run_id))

    def _process_one(self, run_id: str) -> None:
        replay = self._require_replay(run_id)
        spec = self._spec(run_id)
        try:
            simulator = build_daily_simulator(self.db, spec)
            bars = list(simulator.d.market_data.iter_daily_events(list(spec.universe), spec.start, spec.end))
            actions = list(simulator.d.corporate_actions.events(
                list(spec.universe), spec.start, spec.end, spec.data_version_id,
                verification_level=spec.verification_level,
            ))
            integrity = DailySimulator._validate(
                spec, bars, actions=actions, manifest=simulator.d.market_data.manifest()
            )
            bars_by_session: dict[date, dict[InstrumentId, Any]] = {}
            for bar in bars:
                bars_by_session.setdefault(bar.ts_open.date(), {})[bar.instrument] = bar
            sessions = sorted(bars_by_session)
            if replay.completed_sessions >= len(sessions):
                raise ReplaySimulationError("REPLAY_ENGINE_INVARIANT_FAILED", "cursor beyond calendar")
            account, marks = self._restore_account(run_id, spec)
            result = self._load_result(run_id)
            strategy = simulator.d.strategy
            if not isinstance(strategy, StrategyRunnerAdapter):
                raise ReplaySimulationError("REPLAY_ENGINE_INVARIANT_FAILED", "strategy is not restart-safe")
            strategy.import_state(dict(replay.strategy_state_json or {}))
            history = {instrument: [] for instrument in spec.universe}
            for prior in sessions[:replay.completed_sessions]:
                for instrument, bar in bars_by_session[prior].items():
                    history[instrument].append(bar)
            dependencies = replace(
                simulator.d,
                strategy=strategy,
                event_store=ReplayEventStore(self.db),
                ledger=ReplayLedgerRepository(self.db),
                records=ReplayRecordRepository(self.db),
                corporate_action_records=CorporateActionRepository(self.db, auto_commit=False),
            )
            sequence = int(self.db.query(func.coalesce(func.max(SimulationEventORM.sequence), 0)).filter_by(run_id=run_id).scalar())
            order_sequence = int(self.db.query(func.count(SimulationOrderORM.id)).filter_by(run_id=run_id).scalar())
            if sequence != replay.last_event_sequence:
                raise ReplaySimulationError("REPLAY_CHECKPOINT_MISMATCH", "event sequence diverged")
            action_records = dependencies.corporate_action_records
            actions_by_session = {}
            for action in actions:
                actions_by_session.setdefault(action.ex_date, []).append(action)
            state = DailySessionState(
                run_id, spec, account, result, history, marks, sessions, bars_by_session,
                sequence=sequence, order_sequence=order_sequence,
                corporate_actions_by_session=actions_by_session,
                applied_action_ids=action_records.applied_ids(run_id),
                dividend_entitlements=action_records.entitlements(run_id),
            )
            kernel = DailySessionKernel(dependencies, state)
            replay.control_status = ReplayControlStatus.ADVANCING.value
            if replay.checkpoint_hash and replay.checkpoint_hash != self._checkpoint_hash(replay, account, strategy.export_state()):
                raise ReplaySimulationError("REPLAY_CHECKPOINT_MISMATCH")
            if not replay.initialized:
                kernel.start(min(bar.ts_open for bar in bars))
                replay.initialized = True
            index = replay.completed_sessions
            session = sessions[index]
            kernel.process_session(index)
            self._sync_settlements(run_id, account, bars_by_session[session])
            if self.failure_hook:
                self.failure_hook(run_id, session)
            replay.current_session = session
            replay.completed_sessions = index + 1
            replay.next_session = sessions[index + 1] if index + 1 < len(sessions) else None
            replay.last_event_sequence = state.sequence
            replay.strategy_state_json = strategy.export_state()
            replay.updated_at = _now()
            run = self.db.get(SimulationRunORM, run_id)
            if replay.completed_sessions == replay.total_sessions:
                last = max(bars_by_session[session].values(), key=lambda item: item.ts_close)
                if not replay.finish_called:
                    kernel.finish(last.ts_close)
                    replay.finish_called = True
                self._finalize(
                    run, replay, spec, result, account, integrity, actions, state.applied_action_ids
                )
            else:
                replay.control_status = ReplayControlStatus.PAUSED.value
            replay.checkpoint_hash = self._checkpoint_hash(replay, account, replay.strategy_state_json)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            failed_replay = self.db.get(SimulationReplaySessionORM, run_id)
            failed_run = self.db.get(SimulationRunORM, run_id)
            if failed_replay is not None:
                failed_replay.control_status = ReplayControlStatus.FAILED.value
                failed_replay.updated_at = _now()
            if failed_run is not None:
                failed_run.status = SimulationRunStatus.FAILED.value
                failed_run.error = str(exc)
                failed_run.finished_at = _now()
            self.db.commit()
            if isinstance(exc, ReplaySimulationError):
                raise
            raise ReplaySimulationError("REPLAY_ENGINE_INVARIANT_FAILED", str(exc)) from exc

    def _finalize(self, run, replay, spec, result, account, integrity, actions, applied_ids) -> None:  # noqa: ANN001
        reconciliation = ReconciliationService().reconcile(
            spec.initial_cash,
            result.ledger,
            result.fills,
            account,
            corporate_actions=actions,
            applied_corporate_action_ids=applied_ids,
        )
        summary = {
            "status": "DONE", "initial_cash": spec.initial_cash, "final_equity": account.equity,
            "ending_cash": account.base_cash.total, "realized_pnl": account.realized_pnl,
            "unrealized_pnl": account.unrealized_pnl,
            "total_return": account.equity / spec.initial_cash - Decimal(1),
            "daily_bar_path_policy": spec.execution_profile.get("daily_bar_path_policy", "WORST_CASE"),
        }
        result_hash = sha256_value({
            "events": result.events, "orders": result.orders, "fills": result.fills,
            "ledger": result.ledger, "portfolio": result.portfolio_snapshots,
            "positions": result.position_snapshots, "summary": summary,
        })
        built = result.build(
            summary, data_quality=integrity.as_dict(applied=len(applied_ids)),
            reconciliation=reconciliation, result_hash=result_hash,
        )
        run.status = SimulationRunStatus.DONE.value
        run.result_json = to_primitive(built)
        run.result_hash = result_hash
        run.finished_at = _now()
        replay.control_status = ReplayControlStatus.DONE.value
        replay.completed_at = run.finished_at

    def _restore_account(self, run_id: str, spec: SimulationRunSpec) -> tuple[AccountState, dict[InstrumentId, Decimal]]:
        account_id = f"acct_{run_id[4:]}"
        latest = self.db.query(SimulationPortfolioSnapshotORM).filter_by(run_id=run_id).order_by(
            SimulationPortfolioSnapshotORM.snapshot_time.desc()
        ).first()
        if latest is None:
            return AccountState(
                account_id, spec.base_currency,
                cash={spec.base_currency: CashBalance(spec.base_currency, settled=spec.initial_cash)},
                equity=spec.initial_cash, buying_power=spec.initial_cash,
            ), {}
        position_rows = self.db.query(SimulationPositionSnapshotORM).filter_by(
            run_id=run_id, snapshot_time=latest.snapshot_time
        ).all()
        positions = {}
        marks = {}
        for row in position_rows:
            instrument = InstrumentId.parse(row.instrument_key)
            mark = Decimal(str(row.mark_price))
            positions[instrument] = Position(
                instrument, Decimal(str(row.quantity)), Decimal(str(row.average_cost)),
                Decimal(str(row.realized_pnl)), Decimal(str(row.unrealized_pnl)),
                Decimal(str(row.market_value)), mark,
            )
            marks[instrument] = mark
        open_rows = self.db.query(SimulationOrderORM).filter(
            SimulationOrderORM.run_id == run_id,
            SimulationOrderORM.status.in_([OrderStatus.ACCEPTED.value, OrderStatus.PARTIALLY_FILLED.value]),
        ).all()
        open_orders = {row.id: self._order(row) for row in open_rows}
        obligations = [
            SettlementObligation(row.settlement_date, row.currency, Decimal(str(row.amount)), row.fill_id)
            for row in self.db.query(SimulationSettlementObligationORM).filter_by(run_id=run_id, status="PENDING").all()
        ]
        unsettled = sum((item.amount for item in obligations), Decimal(0))
        account = AccountState(
            account_id, spec.base_currency,
            cash={spec.base_currency: CashBalance(
                spec.base_currency, settled=Decimal(str(latest.cash_settled)),
                unsettled_receivable=unsettled, reserved=Decimal(str(latest.cash_reserved)),
            )},
            positions=positions, open_orders=open_orders,
            realized_pnl=Decimal(str(latest.realized_pnl)),
            unrealized_pnl=Decimal(str(latest.unrealized_pnl)),
            equity=Decimal(str(latest.equity)), buying_power=Decimal(str(latest.buying_power)),
            fees=Decimal(str(latest.fees)), settlements=obligations,
        )
        return account, marks

    def _sync_settlements(self, run_id: str, account: AccountState, day_bars: dict) -> None:  # noqa: ANN001
        pending = {item.fill_id: item for item in account.settlements}
        rows = self.db.query(SimulationSettlementObligationORM).filter_by(run_id=run_id).all()
        at = min(day_bars.values(), key=lambda item: item.ts_open).ts_open
        existing = {row.fill_id: row for row in rows}
        for row in rows:
            if row.status == "PENDING" and row.fill_id not in pending:
                row.status = "SETTLED"
                row.settled_at = at
        for fill_id, obligation in pending.items():
            if fill_id not in existing:
                self.db.add(SimulationSettlementObligationORM(
                    id=f"settle_{fill_id}", run_id=run_id, account_id=account.account_id,
                    fill_id=fill_id, currency=obligation.currency, amount=obligation.amount,
                    settlement_date=obligation.settlement_date, status="PENDING", created_at=at,
                ))

    def _checkpoint_hash(self, replay, account: AccountState, strategy_state: dict) -> str:  # noqa: ANN001
        def amount(value: Decimal) -> str:
            return format(Decimal(value).normalize(), "f")

        return sha256_value({
            "run_id": replay.run_id, "current_session": replay.current_session,
            "last_event_sequence": replay.last_event_sequence,
            "account": {
                "cash": {currency: {
                    "settled": amount(cash.settled),
                    "unsettled_receivable": amount(cash.unsettled_receivable),
                    "unsettled_payable": amount(cash.unsettled_payable),
                    "reserved": amount(cash.reserved),
                } for currency, cash in sorted(account.cash.items())},
                "positions": [{
                    "instrument": instrument.key, "quantity": amount(position.quantity),
                    "average_cost": amount(position.average_cost),
                    "realized_pnl": amount(position.realized_pnl),
                    "unrealized_pnl": amount(position.unrealized_pnl),
                    "market_value": amount(position.market_value),
                    "last_mark": amount(position.last_mark) if position.last_mark is not None else None,
                } for instrument, position in sorted(account.positions.items(), key=lambda item: item[0].key)],
                "open_orders": [{
                    "id": order.id, "instrument": order.instrument.key, "side": order.side.value,
                    "type": order.order_type.value, "quantity": amount(order.quantity),
                    "remaining": amount(order.remaining_quantity), "status": order.status.value,
                    "eligible_at": order.eligible_at, "metadata": order.metadata,
                } for order in sorted(account.open_orders.values(), key=lambda item: item.id)],
                "settlements": [{
                    "date": item.settlement_date, "currency": item.currency,
                    "amount": amount(item.amount), "fill_id": item.fill_id,
                } for item in sorted(account.settlements, key=lambda item: (item.settlement_date, item.fill_id))],
                "realized_pnl": amount(account.realized_pnl),
                "unrealized_pnl": amount(account.unrealized_pnl),
                "equity": amount(account.equity), "buying_power": amount(account.buying_power),
                "fees": amount(account.fees),
            },
            "strategy_state": strategy_state,
            "applied_corporate_actions": sorted(
                row.corporate_action_source_id
                for row in self.db.query(SimulationAppliedCorporateActionORM).filter_by(run_id=replay.run_id).all()
            ),
            "dividend_entitlements": [
                {
                    "id": item.id, "source": item.corporate_action_source_id,
                    "pay_date": item.pay_date, "quantity": amount(item.eligible_quantity),
                    "amount": amount(item.total_amount), "status": item.status,
                }
                for item in CorporateActionRepository(self.db, auto_commit=False).entitlements(replay.run_id)
            ],
        })

    def _load_result(self, run_id: str) -> ResultBuilder:
        run = self.db.get(SimulationRunORM, run_id)
        raw = dict(run.manifest_json)
        manifest = RunManifest(**{**raw, "created_at": _aware(datetime.fromisoformat(raw["created_at"]))})
        result = ResultBuilder(run_id, manifest)
        result.orders = [self._order(row) for row in self.db.query(SimulationOrderORM).filter_by(run_id=run_id).order_by(SimulationOrderORM.submitted_at, SimulationOrderORM.id)]
        result.fills = [self._fill(row) for row in self.db.query(SimulationFillORM).filter_by(run_id=run_id).order_by(SimulationFillORM.executed_at, SimulationFillORM.id)]
        result.ledger = [self._ledger(row) for row in self.db.query(SimulationLedgerEntryORM).filter_by(run_id=run_id).order_by(SimulationLedgerEntryORM.event_time, SimulationLedgerEntryORM.id)]
        result.events = [self._event(row) for row in self.db.query(SimulationEventORM).filter_by(run_id=run_id).order_by(SimulationEventORM.sequence)]
        result.portfolio_snapshots = [self._portfolio(row) for row in self.db.query(SimulationPortfolioSnapshotORM).filter_by(run_id=run_id).order_by(SimulationPortfolioSnapshotORM.snapshot_time)]
        result.position_snapshots = [self._position_snapshot(row) for row in self.db.query(SimulationPositionSnapshotORM).filter_by(run_id=run_id).order_by(SimulationPositionSnapshotORM.snapshot_time, SimulationPositionSnapshotORM.instrument_key)]
        return result

    def _sessions(self, run_id: str) -> list[date]:
        spec = self._spec(run_id)
        simulator = build_daily_simulator(self.db, spec)
        return sorted({bar.ts_open.date() for bar in simulator.d.market_data.iter_daily_events(list(spec.universe), spec.start, spec.end)})

    def _spec(self, run_id: str) -> SimulationRunSpec:
        run = self.db.get(SimulationRunORM, run_id)
        if run is None or run.mode != SimulationMode.REPLAY.value:
            raise ReplaySimulationError("REPLAY_RUN_NOT_FOUND")
        raw = dict(run.request_json)
        return SimulationRunSpec(
            mode=SimulationMode(raw["mode"]), verification_level=VerificationLevel(raw["verification_level"]),
            strategy=raw["strategy"], strategy_context=dict(raw.get("strategy_context") or {}),
            universe=tuple(self._instrument(item) for item in raw["universe"]),
            start=date.fromisoformat(raw["start"]), end=date.fromisoformat(raw["end"]),
            initial_cash=Decimal(str(raw["initial_cash"])), base_currency=raw["base_currency"],
            data_version_id=raw.get("data_version_id"), execution_profile=dict(raw["execution_profile"]),
            commission_profile=dict(raw["commission_profile"]), settlement_profile=dict(raw["settlement_profile"]),
            seed=int(raw["seed"]), benchmark=self._instrument(raw["benchmark"]) if raw.get("benchmark") else None,
        )

    @staticmethod
    def _instrument(value: Any) -> InstrumentId:
        if isinstance(value, str):
            return InstrumentId.parse(value)
        return InstrumentId(
            symbol=value["symbol"], venue=value["venue"],
            asset_class=value["asset_class"], currency=value["currency"],
        )

    def _require_replay(self, run_id: str) -> SimulationReplaySessionORM:
        row = self.db.get(SimulationReplaySessionORM, run_id)
        if row is None:
            raise ReplaySimulationError("REPLAY_RUN_NOT_FOUND")
        return row

    def _state(self, row: SimulationReplaySessionORM) -> ReplayState:
        total = row.total_sessions
        current_time = None
        if row.current_session is not None:
            current_time = _aware(self.db.query(func.max(SimulationEventORM.event_time)).filter_by(run_id=row.run_id).scalar())
        return ReplayState(
            row.run_id, ReplayControlStatus(row.control_status), row.current_session, row.next_session,
            row.completed_sessions, total, current_time,
            row.last_event_sequence,
            Decimal(row.completed_sessions) / Decimal(total) if total else Decimal(1), row.checkpoint_hash,
        )

    @staticmethod
    def _order(row: SimulationOrderORM) -> Order:
        metadata = dict(row.metadata_json or {})
        eligible_raw = metadata.pop("eligible_at", None)
        eligible = _aware(datetime.fromisoformat(eligible_raw)) if isinstance(eligible_raw, str) else _aware(eligible_raw)
        return Order(
            row.id, row.run_id, row.account_id, InstrumentId.parse(row.instrument_key), OrderSide(row.side),
            OrderType(row.order_type), Decimal(str(row.quantity)), Decimal(str(row.remaining_quantity)),
            TimeInForce(row.tif), _aware(row.submitted_at), _aware(row.accepted_at), eligible,
            _aware(row.completed_at), Decimal(str(row.limit_price)) if row.limit_price is not None else None,
            Decimal(str(row.stop_price)) if row.stop_price is not None else None, OrderStatus(row.status),
            row.strategy_order_id, row.parent_order_id, metadata,
        )

    @staticmethod
    def _fill(row: SimulationFillORM) -> Fill:
        return Fill(
            row.id, row.run_id, row.order_id, row.account_id, InstrumentId.parse(row.instrument_key),
            OrderSide(row.side), Decimal(str(row.quantity)), Decimal(str(row.price)), _aware(row.executed_at),
            Decimal(str(row.commission)), Decimal(str(row.fees)), Decimal(str(row.slippage_bps)),
            row.liquidity_flag, row.execution_model,
        )

    @staticmethod
    def _ledger(row: SimulationLedgerEntryORM) -> LedgerEntry:
        return LedgerEntry(
            row.id, row.run_id, row.account_id, _aware(row.event_time), LedgerEntryType(row.entry_type),
            row.currency, Decimal(str(row.amount)), InstrumentId.parse(row.instrument_key) if row.instrument_key else None,
            row.order_id, row.fill_id, row.corporate_action_id, dict(row.metadata_json or {}),
        )

    @staticmethod
    def _event(row: SimulationEventORM) -> SimulationEvent:
        return SimulationEvent(
            row.run_id, row.sequence, row.event_id, EventType(row.event_type), _aware(row.event_time),
            _aware(row.processing_time), InstrumentId.parse(row.instrument_key) if row.instrument_key else None,
            row.order_id, row.fill_id, dict(row.payload_json or {}),
        )

    @staticmethod
    def _portfolio(row: SimulationPortfolioSnapshotORM) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            row.run_id, row.account_id, _aware(row.snapshot_time), Decimal(str(row.cash_settled)),
            Decimal(str(row.cash_unsettled)), Decimal(str(row.cash_reserved)), Decimal(str(row.gross_exposure)),
            Decimal(str(row.net_exposure)), Decimal(str(row.market_value)), Decimal(str(row.realized_pnl)),
            Decimal(str(row.unrealized_pnl)), Decimal(str(row.fees)), Decimal(str(row.equity)),
            Decimal(str(row.buying_power)),
        )

    @staticmethod
    def _position_snapshot(row: SimulationPositionSnapshotORM) -> PositionSnapshot:
        return PositionSnapshot(
            row.run_id, row.account_id, _aware(row.snapshot_time), InstrumentId.parse(row.instrument_key),
            Decimal(str(row.quantity)), Decimal(str(row.average_cost)), Decimal(str(row.mark_price)),
            Decimal(str(row.market_value)), Decimal(str(row.realized_pnl)), Decimal(str(row.unrealized_pnl)),
        )
