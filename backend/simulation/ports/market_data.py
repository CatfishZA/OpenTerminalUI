from __future__ import annotations

from datetime import date
from typing import Iterable, Protocol

from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.market import MarketDataManifest, MarketEvent


class MarketDataSource(Protocol):
    def manifest(self) -> MarketDataManifest: ...

    def iter_daily_events(
        self, instruments: list[InstrumentId], start: date, end: date
    ) -> Iterable[MarketEvent]: ...
