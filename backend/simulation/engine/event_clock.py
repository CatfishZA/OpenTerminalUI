from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.simulation.domain.enums import EventType
from backend.simulation.domain.events import SimulationEvent

EVENT_PRIORITY: dict[EventType, int] = {
    EventType.SESSION_START: 10,
    EventType.SETTLEMENT: 20,
    EventType.CORPORATE_ACTION: 30,
    EventType.BAR_OPEN: 40,
    EventType.OPEN_ORDER_MATCH: 50,
    EventType.STRATEGY_OPEN_CALLBACK: 60,
    EventType.INTRADAY_ORDER_PROCESSING: 70,
    EventType.BAR_CLOSE: 80,
    EventType.STRATEGY_CLOSE_CALLBACK: 90,
    EventType.STRATEGY_CALLBACK: 90,
    EventType.POST_CLOSE_ORDER_VALIDATION: 100,
    EventType.MARK: 110,
    EventType.VALUATION: 120,
    EventType.PORTFOLIO_SNAPSHOT: 130,
    EventType.SESSION_END: 140,
}


@dataclass(frozen=True, slots=True)
class EventClock:
    """Deterministic ordering contract; session production is a Phase 1B task."""

    def sort_key(self, event: SimulationEvent) -> tuple[datetime, int, str]:
        return (event.event_time, EVENT_PRIORITY.get(event.event_type, 75), event.event_id)

    def order(self, events: list[SimulationEvent]) -> list[SimulationEvent]:
        return sorted(events, key=self.sort_key)
