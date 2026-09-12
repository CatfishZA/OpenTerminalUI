from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Protocol


class SimulationClock(Protocol):
    @property
    def now(self) -> datetime: ...

    def sessions(self, start: date, end: date) -> Iterable[date]: ...
