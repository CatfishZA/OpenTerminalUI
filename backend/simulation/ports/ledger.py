from __future__ import annotations

from typing import Iterable, Protocol

from backend.simulation.domain.events import LedgerEntry, SimulationEvent


class EventStore(Protocol):
    def append(self, event: SimulationEvent) -> None: ...

    def iter_run(self, run_id: str) -> Iterable[SimulationEvent]: ...


class LedgerRepository(Protocol):
    def append(self, entry: LedgerEntry) -> None: ...

    def iter_run(self, run_id: str) -> Iterable[LedgerEntry]: ...
