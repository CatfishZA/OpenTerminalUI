from __future__ import annotations

from collections import defaultdict
from typing import Callable

from backend.simulation.domain.enums import EventType
from backend.simulation.domain.events import SimulationEvent

EventHandler = Callable[[SimulationEvent], None]


class EventDispatcher:
    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    def dispatch(self, event: SimulationEvent) -> None:
        for handler in tuple(self._handlers.get(event.event_type, ())):
            handler(event)
