from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.simulation.domain.events import LedgerEntry
from backend.simulation.domain.fills import Fill
from backend.simulation.domain.orders import Order
from backend.simulation.domain.results import PortfolioSnapshot, PositionSnapshot, SimulationResult
from backend.simulation.domain.run import RunManifest


@dataclass(slots=True)
class ResultBuilder:
    run_id: str
    manifest: RunManifest
    orders: list[Order] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    ledger: list[LedgerEntry] = field(default_factory=list)
    portfolio_snapshots: list[PortfolioSnapshot] = field(default_factory=list)
    position_snapshots: list[PositionSnapshot] = field(default_factory=list)

    def build(self, summary: dict[str, Any], *, data_quality: dict[str, Any]) -> SimulationResult:
        return SimulationResult(
            run_id=self.run_id,
            manifest=self.manifest,
            summary=dict(summary),
            orders=tuple(self.orders),
            fills=tuple(self.fills),
            ledger=tuple(self.ledger),
            portfolio_snapshots=tuple(self.portfolio_snapshots),
            position_snapshots=tuple(self.position_snapshots),
            data_quality=dict(data_quality),
        )
