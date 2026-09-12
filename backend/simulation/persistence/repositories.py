from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy.orm import Session

from backend.simulation.domain.enums import SimulationRunStatus
from backend.simulation.domain.events import LedgerEntry, SimulationEvent
from backend.simulation.domain.run import RunManifest, RunStatus, SimulationRunSpec
from backend.simulation.persistence.models import (
    SimulationEventORM,
    SimulationFillORM,
    SimulationLedgerEntryORM,
    SimulationOrderORM,
    SimulationPortfolioSnapshotORM,
    SimulationPositionSnapshotORM,
    SimulationRunORM,
)
from backend.simulation.domain.fills import Fill
from backend.simulation.domain.orders import Order
from backend.simulation.domain.results import PortfolioSnapshot, PositionSnapshot
from backend.simulation.persistence.serializers import to_primitive


class SqlAlchemySimulationRunRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, run_id: str, spec: SimulationRunSpec, manifest: RunManifest) -> None:
        self.db.add(
            SimulationRunORM(
                id=run_id,
                mode=spec.mode.value,
                verification_level=spec.verification_level.value,
                status=SimulationRunStatus.QUEUED.value,
                strategy_key=spec.strategy,
                strategy_hash=manifest.strategy_hash,
                code_hash=manifest.git_commit,
                data_version_id=spec.data_version_id,
                engine_version=manifest.engine_version,
                seed=spec.seed,
                request_json=to_primitive(spec),
                manifest_json=to_primitive(manifest),
                created_at=manifest.created_at,
            )
        )
        self.db.commit()

    def get(self, run_id: str) -> SimulationRunORM | None:
        return self.db.get(SimulationRunORM, run_id)

    def get_status(self, run_id: str) -> RunStatus | None:
        row = self.get(run_id)
        if row is None:
            return None
        return RunStatus(
            run_id=row.id,
            status=SimulationRunStatus(row.status),
            progress=0 if row.status == SimulationRunStatus.QUEUED.value else 100 if row.status == SimulationRunStatus.DONE.value else 0,
            stage="not_executed" if row.status == SimulationRunStatus.QUEUED.value else row.status.lower(),
            error=row.error or None,
        )

    def get_manifest(self, run_id: str) -> RunManifest | None:
        row = self.get(run_id)
        if row is None:
            return None
        raw = row.manifest_json
        created_at = datetime.fromisoformat(raw["created_at"])
        return RunManifest(**{**raw, "created_at": created_at})

    def get_request(self, run_id: str) -> dict | None:
        row = self.get(run_id)
        return dict(row.request_json) if row is not None else None

    def update_status(self, run_id: str, status: SimulationRunStatus, *, error: str = "") -> bool:
        row = self.get(run_id)
        if row is None:
            return False
        row.status = status.value
        row.error = error
        if status is SimulationRunStatus.RUNNING and row.started_at is None:
            row.started_at = datetime.now().astimezone()
        if status in {SimulationRunStatus.DONE, SimulationRunStatus.FAILED, SimulationRunStatus.CANCELLED}:
            row.finished_at = datetime.now().astimezone()
        self.db.commit()
        return True


class SqlAlchemyEventStore:
    def __init__(self, db: Session):
        self.db = db

    def append(self, event: SimulationEvent) -> None:
        self.db.add(
            SimulationEventORM(
                run_id=event.run_id,
                sequence=event.sequence,
                event_id=event.event_id,
                event_type=event.event_type.value,
                event_time=event.event_time,
                processing_time=event.processing_time,
                instrument_key=event.instrument.key if event.instrument else None,
                order_id=event.order_id,
                fill_id=event.fill_id,
                payload_json=to_primitive(event.payload),
            )
        )
        self.db.commit()

    def iter_run(self, run_id: str) -> Iterable[SimulationEventORM]:
        return self.db.query(SimulationEventORM).filter_by(run_id=run_id).order_by(SimulationEventORM.sequence).all()


class SqlAlchemyLedgerRepository:
    def __init__(self, db: Session):
        self.db = db

    def append(self, entry: LedgerEntry) -> None:
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
        self.db.commit()

    def iter_run(self, run_id: str) -> Iterable[SimulationLedgerEntryORM]:
        return self.db.query(SimulationLedgerEntryORM).filter_by(run_id=run_id).order_by(SimulationLedgerEntryORM.event_time).all()


class SqlAlchemySimulationRecordRepository:
    """Canonical record sink used by the daily engine."""

    def __init__(self, db: Session):
        self.db = db

    def save_order(self, order: Order) -> None:
        row = self.db.get(SimulationOrderORM, order.id) or SimulationOrderORM(id=order.id, run_id=order.run_id)
        row.account_id = order.account_id; row.instrument_key = order.instrument.key
        row.side = order.side.value; row.order_type = order.order_type.value
        row.quantity = order.quantity; row.remaining_quantity = order.remaining_quantity; row.tif = order.tif.value
        row.limit_price = order.limit_price; row.stop_price = order.stop_price; row.status = order.status.value
        row.submitted_at = order.submitted_at; row.accepted_at = order.accepted_at; row.completed_at = order.completed_at
        row.strategy_order_id = order.strategy_order_id; row.parent_order_id = order.parent_order_id
        row.metadata_json = to_primitive({**order.metadata, "eligible_at": order.eligible_at})
        self.db.add(row); self.db.commit()

    def save_fill(self, fill: Fill) -> None:
        self.db.add(SimulationFillORM(
            id=fill.id, run_id=fill.run_id, order_id=fill.order_id, account_id=fill.account_id,
            instrument_key=fill.instrument.key, side=fill.side.value, quantity=fill.quantity, price=fill.price,
            commission=fill.commission, fees=fill.fees, slippage_bps=fill.slippage_bps,
            executed_at=fill.executed_at, execution_model=fill.execution_model,
            liquidity_flag=fill.liquidity_flag, metadata_json={},
        )); self.db.commit()

    def save_ledger(self, entry: LedgerEntry) -> None:
        if self.db.get(SimulationLedgerEntryORM, entry.id) is None:
            self.db.add(SimulationLedgerEntryORM(
                id=entry.id, run_id=entry.run_id, account_id=entry.account_id, event_time=entry.ts,
                entry_type=entry.entry_type.value, currency=entry.currency, amount=entry.amount,
                instrument_key=entry.instrument.key if entry.instrument else None, order_id=entry.order_id,
                fill_id=entry.fill_id, corporate_action_id=entry.corporate_action_id,
                metadata_json=to_primitive(entry.metadata),
            )); self.db.commit()

    def save_portfolio_snapshot(self, item: PortfolioSnapshot) -> None:
        self.db.add(SimulationPortfolioSnapshotORM(
            run_id=item.run_id, account_id=item.account_id, snapshot_time=item.snapshot_time,
            cash_settled=item.cash_settled, cash_unsettled=item.cash_unsettled, cash_reserved=item.cash_reserved,
            gross_exposure=item.gross_exposure, net_exposure=item.net_exposure, market_value=item.market_value,
            realized_pnl=item.realized_pnl, unrealized_pnl=item.unrealized_pnl, fees=item.fees,
            equity=item.equity, buying_power=item.buying_power,
        )); self.db.commit()

    def save_position_snapshot(self, item: PositionSnapshot) -> None:
        self.db.add(SimulationPositionSnapshotORM(
            run_id=item.run_id, account_id=item.account_id, snapshot_time=item.snapshot_time,
            instrument_key=item.instrument.key, quantity=item.quantity, average_cost=item.average_cost,
            mark_price=item.mark_price, market_value=item.market_value,
            realized_pnl=item.realized_pnl, unrealized_pnl=item.unrealized_pnl,
        )); self.db.commit()
