from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.simulation.domain.ticks import MarketTick
from backend.simulation.persistence.models import (
    SimulationExecutionObservationORM,
    SimulationReconciliationItemORM,
    SimulationReconciliationORM,
)


class ReconciliationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, reconciliation_id: str) -> SimulationReconciliationORM | None:
        return self.db.get(SimulationReconciliationORM, reconciliation_id)

    def by_request_hash(self, request_hash: str) -> SimulationReconciliationORM | None:
        return self.db.query(SimulationReconciliationORM).filter_by(request_hash=request_hash).first()

    def add_report(self, row: SimulationReconciliationORM, items: list[dict[str, Any]]) -> None:
        self.db.add(row)
        self.db.flush()
        for item in items:
            self.db.add(SimulationReconciliationItemORM(reconciliation_id=row.id, **item))

    def items(
        self,
        reconciliation_id: str,
        *,
        item_type: str | None = None,
        match_status: str | None = None,
        instrument: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[SimulationReconciliationItemORM]:
        query = self.db.query(SimulationReconciliationItemORM).filter_by(reconciliation_id=reconciliation_id)
        if item_type:
            query = query.filter(SimulationReconciliationItemORM.item_type == item_type)
        if match_status:
            query = query.filter(SimulationReconciliationItemORM.match_status == match_status)
        if instrument:
            query = query.filter(SimulationReconciliationItemORM.instrument_key == instrument)
        return query.order_by(SimulationReconciliationItemORM.sequence).offset(offset).limit(limit).all()

    def list_for_run(self, run_id: str, *, offset: int = 0, limit: int = 100) -> list[SimulationReconciliationORM]:
        return (
            self.db.query(SimulationReconciliationORM)
            .filter(or_(SimulationReconciliationORM.baseline_run_id == run_id, SimulationReconciliationORM.paper_run_id == run_id))
            .order_by(SimulationReconciliationORM.created_at.desc(), SimulationReconciliationORM.id)
            .offset(offset)
            .limit(limit)
            .all()
        )


class ExecutionObservationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_from_fill_tick(
        self,
        *,
        run_id: str,
        order_id: str,
        fill_id: str,
        tick: MarketTick,
        liquidity_assumption: str | None,
    ) -> SimulationExecutionObservationORM:
        row = SimulationExecutionObservationORM(
            id=f"obs_{fill_id.removeprefix('fill_')}",
            run_id=run_id,
            order_id=order_id,
            fill_id=fill_id,
            instrument_key=tick.instrument.key,
            observed_at=tick.ts,
            tick_price=tick.price,
            bid=tick.bid,
            ask=tick.ask,
            tick_size=tick.size,
            tick_source=tick.source,
            liquidity_assumption=liquidity_assumption,
            metadata_json={"paper_execution": "simulated"},
        )
        self.db.add(row)
        return row

    def for_fills(self, fill_ids: set[str]) -> list[SimulationExecutionObservationORM]:
        if not fill_ids:
            return []
        return self.db.query(SimulationExecutionObservationORM).filter(SimulationExecutionObservationORM.fill_id.in_(fill_ids)).all()


def decimal_or_none(value: object | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def aware_or_none(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.astimezone()

