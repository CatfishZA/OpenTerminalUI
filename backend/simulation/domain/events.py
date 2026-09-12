from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from backend.simulation.domain.enums import EventType, LedgerEntryType
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.market import as_decimal, require_aware
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SimulationEvent:
    run_id: str
    sequence: int
    event_id: str
    event_type: EventType
    event_time: datetime
    processing_time: datetime
    instrument: InstrumentId | None = None
    order_id: str | None = None
    fill_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("event sequence cannot be negative")
        require_aware(self.event_time, "event_time")
        require_aware(self.processing_time, "processing_time")


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    id: str
    run_id: str
    account_id: str
    ts: datetime
    entry_type: LedgerEntryType
    currency: str
    amount: Decimal
    instrument: InstrumentId | None = None
    order_id: str | None = None
    fill_id: str | None = None
    corporate_action_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_aware(self.ts, "ts")
        object.__setattr__(self, "amount", as_decimal(self.amount, "amount"))
        currency = self.currency.strip().upper()
        if len(currency) != 3:
            raise ValueError("ledger currency must be a three-letter code")
        object.__setattr__(self, "currency", currency)
