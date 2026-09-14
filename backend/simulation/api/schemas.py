from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.simulation.domain.enums import SimulationMode, VerificationLevel
from backend.simulation.domain.reconciliation import AlignmentPolicy


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InstrumentSchema(StrictModel):
    symbol: str = Field(min_length=1, max_length=64)
    venue: str = Field(min_length=1, max_length=64)
    asset_class: str = Field(min_length=1, max_length=32)
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("symbol", "venue", "asset_class", "currency")
    @classmethod
    def canonicalize(cls, value: str) -> str:
        canonical = value.strip().upper()
        if not canonical:
            raise ValueError("instrument identity fields cannot be blank")
        return canonical


class StrategySchema(StrictModel):
    key: str = Field(min_length=1, max_length=160)
    context: dict[str, Any] = Field(default_factory=dict)


class AccountSchema(StrictModel):
    initial_cash: Decimal = Field(gt=0)
    base_currency: str = Field(default="USD", min_length=3, max_length=3)
    settlement_days: int = Field(default=1, ge=0, le=30)

    @field_validator("base_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class ExecutionSchema(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str = Field(default="fixed_bps", min_length=1)
    max_participation: Decimal | None = Field(default=None, gt=0, le=1)
    base_slippage_bps: Decimal | None = Field(default=None, ge=0)
    slippage_bps: Decimal | None = Field(default=None, ge=0)
    daily_bar_path_policy: str = "WORST_CASE"


class CommissionSchema(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str = Field(default="bps", min_length=1)
    bps: Decimal = Field(default=Decimal("0"), ge=0)
    minimum: Decimal = Field(default=Decimal("0"), ge=0)


class SimulationRunCreate(StrictModel):
    mode: SimulationMode = SimulationMode.BACKTEST
    verification_level: VerificationLevel
    strategy: StrategySchema
    universe: list[InstrumentSchema] = Field(min_length=1)
    start: date
    end: date
    account: AccountSchema
    data_version_id: str | None = None
    execution: ExecutionSchema = Field(default_factory=ExecutionSchema)
    commission: CommissionSchema = Field(default_factory=CommissionSchema)
    seed: int = 42
    benchmark: InstrumentSchema | None = None

    @model_validator(mode="after")
    def validate_policy(self) -> "SimulationRunCreate":
        if self.end < self.start:
            raise ValueError("INVALID_DATE_RANGE: end date must not precede start date")
        if self.verification_level is VerificationLevel.VERIFIED and not self.data_version_id:
            raise ValueError("DATA_VERSION_REQUIRED: VERIFIED simulations require data_version_id")
        unsupported = sorted({item.asset_class for item in self.universe if item.asset_class != "EQUITY"})
        if unsupported:
            raise ValueError(f"UNSUPPORTED_ASSET_CLASS: {', '.join(unsupported)}")
        return self


class SimulationRunCreated(StrictModel):
    run_id: str
    status: str
    verification_level: VerificationLevel


class SimulationStatusResponse(StrictModel):
    run_id: str
    status: str
    progress: int
    stage: str
    error: str | None = None


class SimulationManifestResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    run_id: str
    manifest_hash: str
    engine_version: str
    created_at: datetime


class SimulationResultResponse(StrictModel):
    run_id: str
    status: str
    stage: str
    result: dict[str, Any] | None
    error: str | None = None


class CollectionResponse(StrictModel):
    run_id: str
    items: list[dict[str, Any]]
    count: int


class ReconciliationCreate(StrictModel):
    baseline_run_id: str = Field(min_length=1, max_length=64)
    paper_run_id: str = Field(min_length=1, max_length=64)
    paper_cutoff_sequence: int | None = Field(default=None, ge=1)
    alignment_policy: AlignmentPolicy = AlignmentPolicy.KEYED_THEN_SIGNATURE
    allow_research_baseline: bool = False
    include_low_confidence_matches: bool = True
