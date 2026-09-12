from __future__ import annotations

from datetime import date
from typing import Iterable, Protocol

from backend.simulation.domain.corporate_actions import CorporateAction
from backend.simulation.domain.identifiers import InstrumentId


class CorporateActionSource(Protocol):
    def events(
        self,
        instruments: list[InstrumentId],
        start: date,
        end: date,
        data_version_id: str,
    ) -> Iterable[CorporateAction]: ...
