from __future__ import annotations

import asyncio

import pytest

from backend.simulation.persistence.models import SimulationEventORM, SimulationPortfolioSnapshotORM, SimulationRunORM
from backend.simulation.services.replay_simulation_service import ReplaySimulationService
from backend.simulation.services.replay_simulation_service import ReplaySimulationError
from backend.tests.simulation.replay_test_helpers import replay_spec, seed_replay_data


def test_advance_one_then_run_to_end_builds_canonical_result(db_session) -> None:  # noqa: ANN001
    seed_replay_data(db_session)
    service = ReplaySimulationService(db_session)
    run_id = asyncio.run(service.create(replay_spec()))
    state = asyncio.run(service.advance(run_id))
    assert state.status.value == "PAUSED" and state.completed_sessions == 1
    assert db_session.query(SimulationPortfolioSnapshotORM).filter_by(run_id=run_id).count() == 1
    assert db_session.query(SimulationEventORM).filter_by(run_id=run_id).count() > 0
    done = asyncio.run(service.run_to_end(run_id))
    run = db_session.get(SimulationRunORM, run_id)
    assert done.status.value == "DONE" and done.completed_sessions == done.total_sessions == 6
    assert run.status == "DONE" and run.result_json and run.result_hash


def test_run_to_stops_on_target(db_session) -> None:  # noqa: ANN001
    seed_replay_data(db_session)
    service = ReplaySimulationService(db_session)
    run_id = asyncio.run(service.create(replay_spec()))
    from datetime import date
    state = asyncio.run(service.run_to(run_id, target_session=date(2024, 1, 3)))
    assert state.current_session == date(2024, 1, 3)
    assert state.completed_sessions == 3 and state.status.value == "PAUSED"


def test_cancel_preserves_artifacts_and_blocks_advance(db_session) -> None:  # noqa: ANN001
    seed_replay_data(db_session)
    service = ReplaySimulationService(db_session)
    run_id = asyncio.run(service.create(replay_spec()))
    asyncio.run(service.advance(run_id))
    before = db_session.query(SimulationEventORM).filter_by(run_id=run_id).count()
    cancelled = asyncio.run(service.cancel(run_id))
    assert cancelled.status.value == "CANCELLED"
    assert db_session.query(SimulationEventORM).filter_by(run_id=run_id).count() == before
    with pytest.raises(ReplaySimulationError, match="REPLAY_CANCELLED"):
        asyncio.run(service.advance(run_id))


def test_concurrent_advance_serializes_two_distinct_sessions(db_session) -> None:  # noqa: ANN001
    seed_replay_data(db_session)
    service = ReplaySimulationService(db_session)
    run_id = asyncio.run(service.create(replay_spec()))

    async def advance_twice():
        return await asyncio.gather(service.advance(run_id), service.advance(run_id))

    asyncio.run(advance_twice())
    state = asyncio.run(service.state(run_id))
    assert state.completed_sessions == 2
    starts = db_session.query(SimulationEventORM).filter_by(run_id=run_id, event_type="SESSION_START").count()
    assert starts == 2
