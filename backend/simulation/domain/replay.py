from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class ReplayControlStatus(str, Enum):
    READY = "READY"
    ADVANCING = "ADVANCING"
    PAUSED = "PAUSED"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class ReplayState:
    run_id: str
    status: ReplayControlStatus
    current_session: date | None
    next_session: date | None
    completed_sessions: int
    total_sessions: int
    current_time: datetime | None
    last_event_sequence: int
    progress: Decimal
    checkpoint_hash: str | None

