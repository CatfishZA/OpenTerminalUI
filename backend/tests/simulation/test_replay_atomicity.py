from __future__ import annotations

import asyncio

import pytest

from backend.simulation.persistence.models import SimulationEventORM, SimulationPortfolioSnapshotORM, SimulationRunORM
from backend.simulation.services.replay_simulation_service import ReplaySimulationError, ReplaySimulationService
from backend.tests.simulation.replay_test_helpers import replay_spec, seed_replay_data


def test_session_failure_rolls_back_all_artifacts_and_cursor(db_session) -> None:  # noqa: ANN001
    seed_replay_data(db_session)

    def fail(_run_id, _session) -> None:  # noqa: ANN001
        raise RuntimeError("injected session failure")

    service = ReplaySimulationService(db_session, failure_hook=fail)
    run_id = asyncio.run(service.create(replay_spec()))
    with pytest.raises(ReplaySimulationError, match="REPLAY_ENGINE_INVARIANT_FAILED"):
        asyncio.run(service.advance(run_id))
    state = asyncio.run(service.state(run_id))
    assert state.status.value == "FAILED" and state.completed_sessions == 0 and state.current_session is None
    assert db_session.query(SimulationEventORM).filter_by(run_id=run_id).count() == 0
    assert db_session.query(SimulationPortfolioSnapshotORM).filter_by(run_id=run_id).count() == 0
    assert db_session.get(SimulationRunORM, run_id).status == "FAILED"
