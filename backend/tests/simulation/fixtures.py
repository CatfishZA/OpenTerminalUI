from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.simulation.domain.enums import SimulationMode, VerificationLevel
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.run import SimulationRunSpec


def instrument() -> InstrumentId:
    return InstrumentId("AAPL", "NASDAQ", "EQUITY", "USD")


def run_spec(**changes) -> SimulationRunSpec:  # noqa: ANN003
    values = {
        "mode": SimulationMode.BACKTEST,
        "verification_level": VerificationLevel.RESEARCH,
        "strategy": "example:sma_crossover",
        "strategy_context": {"short_window": 20, "long_window": 50},
        "universe": (instrument(),),
        "start": date(2024, 1, 1),
        "end": date(2024, 12, 31),
        "initial_cash": Decimal("100000"),
        "base_currency": "USD",
        "data_version_id": None,
        "execution_profile": {"model": "fixed_bps", "slippage_bps": "2"},
        "commission_profile": {"model": "bps", "bps": "1"},
        "settlement_profile": {"settlement_days": 1},
        "seed": 42,
        "benchmark": None,
    }
    values.update(changes)
    return SimulationRunSpec(**values)
