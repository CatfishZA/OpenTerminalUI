from __future__ import annotations

from dataclasses import dataclass, field
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
    _last_signal: dict[InstrumentId, int] = field(default_factory=dict, init=False)

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
        if event.event_type is not EventType.STRATEGY_CLOSE_CALLBACK or event.instrument is None:
            return []
        history = ctx.market.history(event.instrument, limit=int(self.strategy_context.get("history_limit", 10000)))
        if not history:
            return []
        import pandas as pd

        frame = pd.DataFrame(
            [{"open": float(bar.open), "high": float(bar.high), "low": float(bar.low),
              "close": float(bar.close), "volume": float(bar.volume)} for bar in history],
            index=[bar.ts_close for bar in history],
        )
        signals = self.run_signals(frame)
        signal = int(signals.iloc[-1] if hasattr(signals, "iloc") else signals[-1])
        previous = self._last_signal.get(event.instrument)
        self._last_signal[event.instrument] = signal
        if signal == previous:
            return []
        position = ctx.positions.get(event.instrument)
        held = position.quantity if position is not None else Decimal("0")
        if signal == 1 and held == 0:
            quantity = Decimal(str(self.strategy_context.get("quantity", "1")))
            intent = self.signal_to_intent(1, event.instrument, quantity, ctx.now)
            return [intent] if intent else []
        if signal == 0 and held > 0:
            return [StrategyIntent(event.instrument, OrderSide.SELL, held, ctx.now,
                metadata={"source": "legacy_strategy_runner", "eligible": "next_session_open"})]
        # Phase 1B is long-only; negative target signals are intentionally ignored.
        return []

    def on_finish(self, ctx: StrategyContext) -> None:
        return None
