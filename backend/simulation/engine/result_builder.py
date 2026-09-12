from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from decimal import Decimal

from backend.simulation.domain.events import LedgerEntry
from backend.simulation.domain.events import SimulationEvent
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
    events: list[SimulationEvent] = field(default_factory=list)

    def build(
        self,
        summary: dict[str, Any],
        *,
        data_quality: dict[str, Any],
        reconciliation: dict[str, Any] | None = None,
        result_hash: str = "",
    ) -> SimulationResult:
        equity_curve = tuple(
            {"timestamp": item.snapshot_time.isoformat(), "equity": item.equity}
            for item in self.portfolio_snapshots
        )
        daily_returns: list[Decimal] = []
        for previous, current in zip(self.portfolio_snapshots, self.portfolio_snapshots[1:]):
            daily_returns.append(current.equity / previous.equity - Decimal("1") if previous.equity else Decimal("0"))
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
            events=tuple(self.events),
            reconciliation=dict(reconciliation or {}),
            result_hash=result_hash,
            equity_curve=equity_curve,
            daily_returns=tuple(daily_returns),
        )
