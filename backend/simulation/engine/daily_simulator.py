from __future__ import annotations

from dataclasses import dataclass

from backend.simulation.domain.results import SimulationResult
from backend.simulation.domain.run import SimulationRunSpec
from backend.simulation.ports.corporate_actions import CorporateActionSource
from backend.simulation.ports.execution import ExecutionModel
from backend.simulation.ports.fees import CommissionModel
from backend.simulation.ports.ledger import EventStore, LedgerRepository
from backend.simulation.ports.market_data import MarketDataSource
from backend.simulation.ports.strategy import StrategyAdapter


@dataclass(slots=True)
class DailySimulatorDependencies:
    market_data: MarketDataSource
    corporate_actions: CorporateActionSource
    strategy: StrategyAdapter
    execution: ExecutionModel
    commission: CommissionModel
    event_store: EventStore
    ledger: LedgerRepository


class DailySimulator:
    """Stable insertion point for the deterministic Phase 1B loop."""

    def __init__(self, dependencies: DailySimulatorDependencies):
        self.dependencies = dependencies

    def run(self, spec: SimulationRunSpec) -> SimulationResult:
        raise NotImplementedError("Deterministic daily simulation is intentionally deferred to Phase 1B")
