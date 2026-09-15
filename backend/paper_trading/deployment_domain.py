from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.market import as_decimal, require_aware


class DeploymentStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    HALTED = "HALTED"
    FAILED = "FAILED"


class StrategyCapability(str, Enum):
    COMPLETED_BAR = "COMPLETED_BAR"


TERMINAL_DEPLOYMENT_STATUSES = frozenset({
    DeploymentStatus.STOPPED,
    DeploymentStatus.HALTED,
    DeploymentStatus.FAILED,
})


class DeploymentError(ValueError):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)


@dataclass(frozen=True, slots=True)
class CompletedBarObservation:
    source_event_id: str
    instrument: InstrumentId
    interval: str
    start_time: datetime
    end_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str
    complete: bool = True

    def __post_init__(self) -> None:
        if not self.source_event_id.strip():
            raise DeploymentError("MARKET_INPUT_ID_REQUIRED")
        require_aware(self.start_time, "start_time")
        require_aware(self.end_time, "end_time")
        if self.end_time <= self.start_time or self.interval != "1d":
            raise DeploymentError("MARKET_INPUT_INVALID")
        for field in ("open", "high", "low", "close", "volume"):
            object.__setattr__(self, field, as_decimal(getattr(self, field), field))
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise DeploymentError("MARKET_INPUT_INVALID")
        if self.high < max(self.open, self.low, self.close) or self.low > min(self.open, self.high, self.close):
            raise DeploymentError("MARKET_INPUT_INVALID")
        if self.volume < 0:
            raise DeploymentError("MARKET_INPUT_INVALID")


@dataclass(frozen=True, slots=True)
class RiskDecision:
    accepted: bool
    reason: str | None = None

