from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from backend.simulation.domain.identifiers import InstrumentId


def as_decimal(value: Decimal | int | str | float, label: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{label} must be decimal-compatible") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be finite")
    return result


def require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class MarketBar:
    instrument: InstrumentId
    ts_open: datetime
    ts_close: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    data_version_id: str

    def __post_init__(self) -> None:
        require_aware(self.ts_open, "ts_open")
        require_aware(self.ts_close, "ts_close")
        if self.ts_close <= self.ts_open:
            raise ValueError("ts_close must be after ts_open")
        for name in ("open", "high", "low", "close", "volume"):
            object.__setattr__(self, name, as_decimal(getattr(self, name), name))
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC prices must be positive")
        if self.high < max(self.open, self.low, self.close) or self.low > min(self.open, self.high, self.close):
            raise ValueError("invalid OHLC range")
        if self.volume < 0:
            raise ValueError("volume cannot be negative")
        if not self.data_version_id:
            raise ValueError("data_version_id is required")


MarketEvent = MarketBar


@dataclass(frozen=True, slots=True)
class MarketDataManifest:
    data_version_id: str | None
    dataset_hash: str | None
    instruments: tuple[InstrumentId, ...]
    start: date
    end: date
    data_source: str
    adjusted: bool
    calendar_version: str | None = None
    corporate_action_version: str | None = None
    missing_data_summary: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("market-data manifest end precedes start")
