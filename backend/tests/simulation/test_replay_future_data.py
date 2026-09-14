from __future__ import annotations

import asyncio

from backend.simulation.services.replay_simulation_service import ReplaySimulationService
from backend.tests.simulation.replay_test_helpers import replay_instrument, replay_spec, seed_replay_data


def test_market_view_exposes_only_completed_sessions(db_session) -> None:  # noqa: ANN001
    seed_replay_data(db_session)
    service = ReplaySimulationService(db_session)
    run_id = asyncio.run(service.create(replay_spec()))
    assert asyncio.run(service.market(run_id, replay_instrument())) == []
    asyncio.run(service.advance(run_id))
    bars = asyncio.run(service.market(run_id, replay_instrument()))
    assert len(bars) == 1 and bars[0]["ts_close"].startswith("2024-01-01")
