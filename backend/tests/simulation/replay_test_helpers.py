from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.models import DataVersionORM, PriceEodORM
from backend.simulation.domain.enums import SimulationMode, VerificationLevel
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.run import SimulationRunSpec


def replay_instrument() -> InstrumentId:
    return InstrumentId("AAPL", "NASDAQ", "EQUITY", "USD")


def seed_replay_data(db, *, version_id: str = "replay-v1") -> None:  # noqa: ANN001
    db.add(DataVersionORM(
        id=version_id, name="replay fixture", source="internal", is_active=True,
        metadata_json={"dataset_hash": "replay-dataset", "calendar_version": "fixture-v1"},
    ))
    closes = [100, 102, 99, 104, 98, 106]
    for day, close in enumerate(closes, 1):
        db.add(PriceEodORM(
            symbol="AAPL", trade_date=f"2024-01-0{day}", open=close,
            high=close + 2, low=close - 2, close=close, volume=100000,
            data_version_id=version_id,
        ))
    db.commit()


def replay_spec(**changes) -> SimulationRunSpec:  # noqa: ANN003
    values = {
        "mode": SimulationMode.REPLAY,
        "verification_level": VerificationLevel.VERIFIED,
        "strategy": "example:sma_crossover",
        "strategy_context": {"short_window": 1, "long_window": 2, "quantity": 10},
        "universe": (replay_instrument(),),
        "start": date(2024, 1, 1),
        "end": date(2024, 1, 6),
        "initial_cash": Decimal("100000"),
        "base_currency": "USD",
        "data_version_id": "replay-v1",
        "execution_profile": {"model": "fixed_bps", "slippage_bps": "0", "daily_bar_path_policy": "WORST_CASE"},
        "commission_profile": {"model": "bps", "bps": "0", "minimum": "0"},
        "settlement_profile": {"settlement_days": 1},
        "seed": 42,
        "benchmark": None,
    }
    values.update(changes)
    return SimulationRunSpec(**values)
