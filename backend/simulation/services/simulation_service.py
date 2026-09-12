from __future__ import annotations

from uuid import uuid4
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from backend.simulation.domain.run import RunManifest, RunStatus, SimulationRunSpec
from backend.simulation.persistence.models import (
    SimulationEventORM,
    SimulationFillORM,
    SimulationLedgerEntryORM,
    SimulationOrderORM,
    SimulationPortfolioSnapshotORM,
    SimulationPositionSnapshotORM,
)
from backend.simulation.persistence.repositories import SqlAlchemySimulationRunRepository
from backend.simulation.services.manifest_service import ManifestService
from backend.simulation.domain.enums import SimulationRunStatus
from backend.simulation.domain.results import SimulationResult
if TYPE_CHECKING:
    from backend.simulation.engine.daily_simulator import DailySimulator


class SimulationNotFoundError(LookupError):
    pass


class SimulationService:
    def __init__(
        self,
        db: Session,
        *,
        run_repository: SqlAlchemySimulationRunRepository | None = None,
        manifest_service: ManifestService | None = None,
    ):
        self.db = db
        self.run_repository = run_repository or SqlAlchemySimulationRunRepository(db)
        self.manifest_service = manifest_service or ManifestService()

    async def submit(self, spec: SimulationRunSpec) -> str:
        # Domain construction has already applied all Phase 1A request validation.
        run_id = f"sim_{uuid4().hex[:12]}"
        manifest = self.manifest_service.build(run_id, spec)
        self.run_repository.create(run_id, spec, manifest)
        return run_id

    async def execute(self, run_id: str, spec: SimulationRunSpec, simulator: DailySimulator) -> SimulationResult:
        """Run the deterministic engine and enforce the canonical status lifecycle."""
        try:
            self.run_repository.update_status(run_id, SimulationRunStatus.VALIDATING_DATA)
            self.run_repository.update_status(run_id, SimulationRunStatus.BUILDING_MANIFEST)
            manifest = self.run_repository.get_manifest(run_id)
            if manifest is None:
                raise SimulationNotFoundError(run_id)
            self.run_repository.update_status(run_id, SimulationRunStatus.RUNNING)
            result = simulator.run(spec, run_id=run_id, manifest=manifest)
            self.run_repository.update_status(run_id, SimulationRunStatus.FINALIZING)
            self.run_repository.update_status(run_id, SimulationRunStatus.DONE)
            return result
        except Exception as exc:
            self.db.rollback()
            self.run_repository.update_status(run_id, SimulationRunStatus.FAILED, error=str(exc))
            raise

    def _require(self, run_id: str):
        row = self.run_repository.get(run_id)
        if row is None:
            raise SimulationNotFoundError(run_id)
        return row

    async def status(self, run_id: str) -> RunStatus:
        status = self.run_repository.get_status(run_id)
        if status is None:
            raise SimulationNotFoundError(run_id)
        return status

    async def result(self, run_id: str) -> dict:
        row = self._require(run_id)
        return {"run_id": row.id, "status": row.status, "stage": "not_executed", "result": None}

    async def manifest(self, run_id: str) -> RunManifest:
        manifest = self.run_repository.get_manifest(run_id)
        if manifest is None:
            raise SimulationNotFoundError(run_id)
        return manifest

    async def orders(self, run_id: str, *, offset: int = 0, limit: int = 100) -> list[SimulationOrderORM]:
        self._require(run_id)
        return self.db.query(SimulationOrderORM).filter_by(run_id=run_id).order_by(SimulationOrderORM.submitted_at).offset(offset).limit(limit).all()

    async def fills(self, run_id: str, *, offset: int = 0, limit: int = 100) -> list[SimulationFillORM]:
        self._require(run_id)
        return self.db.query(SimulationFillORM).filter_by(run_id=run_id).order_by(SimulationFillORM.executed_at).offset(offset).limit(limit).all()

    async def events(
        self,
        run_id: str,
        *,
        from_sequence: int | None = None,
        to_sequence: int | None = None,
        event_type: str | None = None,
        instrument: str | None = None,
        limit: int = 100,
    ) -> list[SimulationEventORM]:
        self._require(run_id)
        query = self.db.query(SimulationEventORM).filter_by(run_id=run_id)
        if from_sequence is not None:
            query = query.filter(SimulationEventORM.sequence >= from_sequence)
        if to_sequence is not None:
            query = query.filter(SimulationEventORM.sequence <= to_sequence)
        if event_type:
            query = query.filter(SimulationEventORM.event_type == event_type)
        if instrument:
            query = query.filter(SimulationEventORM.instrument_key == instrument)
        return query.order_by(SimulationEventORM.sequence).limit(limit).all()

    async def ledger(self, run_id: str, *, offset: int = 0, limit: int = 100) -> list[SimulationLedgerEntryORM]:
        self._require(run_id)
        return self.db.query(SimulationLedgerEntryORM).filter_by(run_id=run_id).order_by(SimulationLedgerEntryORM.event_time).offset(offset).limit(limit).all()

    async def portfolio(self, run_id: str, *, offset: int = 0, limit: int = 100) -> list[SimulationPortfolioSnapshotORM]:
        self._require(run_id)
        return self.db.query(SimulationPortfolioSnapshotORM).filter_by(run_id=run_id).order_by(SimulationPortfolioSnapshotORM.snapshot_time).offset(offset).limit(limit).all()

    async def positions(self, run_id: str, *, offset: int = 0, limit: int = 100) -> list[SimulationPositionSnapshotORM]:
        self._require(run_id)
        return self.db.query(SimulationPositionSnapshotORM).filter_by(run_id=run_id).order_by(SimulationPositionSnapshotORM.snapshot_time).offset(offset).limit(limit).all()
