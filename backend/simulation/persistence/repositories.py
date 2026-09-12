from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy.orm import Session

from backend.simulation.domain.enums import SimulationRunStatus
from backend.simulation.domain.events import LedgerEntry, SimulationEvent
from backend.simulation.domain.run import RunManifest, RunStatus, SimulationRunSpec
from backend.simulation.persistence.models import (
    SimulationEventORM,
    SimulationLedgerEntryORM,
    SimulationRunORM,
)
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
