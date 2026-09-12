from __future__ import annotations

from dataclasses import dataclass

from backend.simulation.domain.identifiers import InstrumentId


@dataclass(frozen=True, slots=True)
class Instrument:
    id: InstrumentId
    display_name: str = ""
    price_precision: int = 2
    quantity_precision: int = 0

    def __post_init__(self) -> None:
        if self.price_precision < 0 or self.quantity_precision < 0:
            raise ValueError("instrument precision cannot be negative")
