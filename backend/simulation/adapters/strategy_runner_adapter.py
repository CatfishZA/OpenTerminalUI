from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.simulation.domain.enums import EventType, OrderSide
from backend.simulation.domain.events import SimulationEvent
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.strategy import StrategyContext, StrategyIntent


@dataclass(slots=True)
class StrategyRunnerAdapter:
    """Boundary around the legacy signal generator.

    Phase 1A exposes signal conversion without giving legacy strategy code account
    or persistence access. Phase 1B will supply bar history at BAR_CLOSE.
    """

    strategy_key: str
    strategy_context: dict[str, Any]

    def run_signals(self, frame: Any) -> Any:
        from backend.core.strategy_runner import StrategyRunner

        return StrategyRunner().run(self.strategy_key, frame, self.strategy_context).signals

    def signal_to_intent(
        self,
        signal: int,
        instrument: InstrumentId,
        quantity: Decimal,
        available_at: datetime,
    ) -> StrategyIntent | None:
        if signal == 0:
            return None
        if signal not in {-1, 1}:
            raise ValueError("legacy strategy signals must be -1, 0, or 1")
        return StrategyIntent(
            instrument=instrument,
            side=OrderSide.BUY if signal == 1 else OrderSide.SELL,
            quantity=quantity,
            created_at=available_at,
            metadata={"source": "legacy_strategy_runner", "eligible": "next_session_open"},
        )

    def on_start(self, ctx: StrategyContext) -> None:
        return None

    def on_event(self, ctx: StrategyContext, event: SimulationEvent) -> list[StrategyIntent]:
        # Signal evaluation requires the immutable history view introduced in 1B.
        if event.event_type is not EventType.STRATEGY_CLOSE_CALLBACK:
            return []
        return []

    def on_finish(self, ctx: StrategyContext) -> None:
        return None
