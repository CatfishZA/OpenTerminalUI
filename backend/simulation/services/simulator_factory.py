from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from backend.models import DataVersionORM
from backend.simulation.adapters.corporate_actions_adapter import CorporateActionsAdapter
from backend.simulation.adapters.strategy_runner_adapter import StrategyRunnerAdapter
from backend.simulation.adapters.versioned_data_adapter import VersionedDataAdapter
from backend.simulation.domain.run import SimulationRunSpec
from backend.simulation.engine.daily_simulator import DailySimulator, DailySimulatorDependencies
from backend.simulation.execution.commissions import BpsCommissionModel
from backend.simulation.execution.fixed_bps import FixedBpsExecutionModel
from backend.simulation.execution.volume_participation import VolumeParticipationExecutionModel
from backend.simulation.persistence.repositories import (
    SqlAlchemyEventStore,
    SqlAlchemyLedgerRepository,
    SqlAlchemySimulationRecordRepository,
)


def build_daily_simulator(db: Session, spec: SimulationRunSpec) -> DailySimulator:
    version = db.get(DataVersionORM, spec.data_version_id)
    if version is None:
        raise ValueError(f"DATA_VERSION_NOT_FOUND: {spec.data_version_id}")
    metadata = dict(version.metadata_json or {})
    if str(version.source).strip().lower() in {"synthetic", "generated", "demo"}:
        raise ValueError("VERIFIED_DATA_MISSING: synthetic data version is prohibited")

    execution_name = str(spec.execution_profile.get("model", "")).lower()
    if execution_name == "fixed_bps":
        execution = FixedBpsExecutionModel(
            Decimal(str(spec.execution_profile.get("slippage_bps", 0))),
            Decimal(str(spec.execution_profile.get("max_participation", 1))),
        )
    elif execution_name == "volume_participation":
        execution = VolumeParticipationExecutionModel(
            Decimal(str(spec.execution_profile.get("max_participation", "0.1"))),
            Decimal(str(spec.execution_profile.get("base_slippage_bps", 0))),
            Decimal(str(spec.execution_profile.get("volume_weighted_bps", 0))),
        )
    else:
        raise ValueError(f"UNSUPPORTED_EXECUTION_MODEL: {execution_name}")

    commission_name = str(spec.commission_profile.get("model", "")).lower()
    if commission_name != "bps":
        raise ValueError(f"UNSUPPORTED_COMMISSION_MODEL: {commission_name}")
    commission = BpsCommissionModel(
        Decimal(str(spec.commission_profile.get("bps", 0))),
        Decimal(str(spec.commission_profile.get("minimum", 0))),
    )
    market_data = VersionedDataAdapter(
        db,
        data_version_id=spec.data_version_id,
        instruments=list(spec.universe),
        start=spec.start,
        end=spec.end,
        dataset_hash=metadata.get("dataset_hash"),
        calendar_version=metadata.get("calendar_version"),
    )
    return DailySimulator(DailySimulatorDependencies(
        market_data=market_data,
        corporate_actions=CorporateActionsAdapter(db),
        strategy=StrategyRunnerAdapter(spec.strategy, spec.strategy_context),
        execution=execution,
        commission=commission,
        event_store=SqlAlchemyEventStore(db),
        ledger=SqlAlchemyLedgerRepository(db),
        records=SqlAlchemySimulationRecordRepository(db),
    ))
