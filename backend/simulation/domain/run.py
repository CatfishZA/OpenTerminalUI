from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from backend.simulation.domain.enums import SimulationMode, SimulationRunStatus, VerificationLevel
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.market import as_decimal, require_aware

SUPPORTED_PHASE_1_ASSET_CLASSES = frozenset({"EQUITY"})


@dataclass(frozen=True, slots=True)
class SimulationRunSpec:
    mode: SimulationMode
    verification_level: VerificationLevel
    strategy: str
    strategy_context: dict[str, Any]
    universe: tuple[InstrumentId, ...]
    start: date
    end: date
    initial_cash: Decimal
    base_currency: str
    data_version_id: str | None
    execution_profile: dict[str, Any]
    commission_profile: dict[str, Any]
    settlement_profile: dict[str, Any]
    seed: int
    benchmark: InstrumentId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "universe", tuple(self.universe))
        object.__setattr__(self, "initial_cash", as_decimal(self.initial_cash, "initial_cash"))
        object.__setattr__(self, "base_currency", self.base_currency.strip().upper())
        if not self.strategy.strip():
            raise ValueError("strategy key is required")
        if not self.universe:
            raise ValueError("universe must contain at least one instrument")
        if self.end < self.start:
            raise ValueError("end date must not precede start date")
        if self.initial_cash <= 0:
            raise ValueError("initial cash must be positive")
        if len(self.base_currency) != 3:
            raise ValueError("base currency must be a three-letter code")
        unsupported = sorted({item.asset_class for item in self.universe if item.asset_class not in SUPPORTED_PHASE_1_ASSET_CLASSES})
        if unsupported:
            raise ValueError(f"UNSUPPORTED_ASSET_CLASS: {', '.join(unsupported)}")
        if self.verification_level is VerificationLevel.VERIFIED and not self.data_version_id:
            raise ValueError("DATA_VERSION_REQUIRED: VERIFIED simulations require data_version_id")


@dataclass(frozen=True, slots=True)
class RunManifest:
    run_id: str
    engine_version: str
    git_commit: str | None
    strategy_hash: str
    strategy_key: str
    strategy_context_hash: str
    data_version_id: str | None
    dataset_hash: str | None
    universe_hash: str
    corporate_actions_hash: str | None
    calendar_version: str | None
    execution_profile_hash: str
    commission_profile_hash: str
    settlement_profile_hash: str
    seed: int
    request_hash: str
    manifest_hash: str
    created_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class RunStatus:
    run_id: str
    status: SimulationRunStatus
    progress: int = 0
    stage: str = "not_executed"
    error: str | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.progress <= 100:
            raise ValueError("progress must be between 0 and 100")
