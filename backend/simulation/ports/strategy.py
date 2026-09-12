from __future__ import annotations

from typing import Protocol

from backend.simulation.domain.events import SimulationEvent
from backend.simulation.domain.strategy import StrategyContext, StrategyIntent


class StrategyAdapter(Protocol):
    def on_start(self, ctx: StrategyContext) -> None: ...

    def on_event(self, ctx: StrategyContext, event: SimulationEvent) -> list[StrategyIntent]: ...

    def on_finish(self, ctx: StrategyContext) -> None: ...
