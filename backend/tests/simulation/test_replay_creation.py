from __future__ import annotations

import asyncio

import pytest

from backend.models import DataVersionORM
from backend.simulation.domain.enums import SimulationMode, SimulationRunStatus, VerificationLevel
from backend.simulation.persistence.models import SimulationLedgerEntryORM, SimulationRunORM
from backend.simulation.services.replay_simulation_service import ReplaySimulationError, ReplaySimulationService
from backend.tests.simulation.replay_test_helpers import replay_spec, seed_replay_data


def test_create_verified_replay_is_ready_without_processing_sessions(db_session) -> None:  # noqa: ANN001
    seed_replay_data(db_session)
    service = ReplaySimulationService(db_session)
    run_id = asyncio.run(service.create(replay_spec()))
    state = asyncio.run(service.state(run_id))
    run = db_session.get(SimulationRunORM, run_id)
    assert run.mode == SimulationMode.REPLAY.value
    assert run.verification_level == VerificationLevel.VERIFIED.value
    assert run.status == SimulationRunStatus.RUNNING.value
    assert state.status.value == "READY" and state.completed_sessions == 0
    assert state.current_session is None and state.next_session.isoformat() == "2024-01-01"
    assert db_session.query(SimulationLedgerEntryORM).filter_by(run_id=run_id).count() == 1


def test_replay_requires_version_and_rejects_synthetic(db_session) -> None:  # noqa: ANN001
    service = ReplaySimulationService(db_session)
    with pytest.raises(ReplaySimulationError, match="REPLAY_DATA_VERSION_REQUIRED"):
        asyncio.run(service.create(replay_spec(verification_level=VerificationLevel.RESEARCH, data_version_id=None)))
    with pytest.raises(ReplaySimulationError, match="REPLAY_SYNTHETIC_UNSUPPORTED"):
        asyncio.run(service.create(replay_spec(verification_level=VerificationLevel.SYNTHETIC)))


def test_missing_persisted_history_fails_without_fallback(db_session, monkeypatch) -> None:  # noqa: ANN001
    db_session.add(DataVersionORM(
        id="replay-v1", name="empty", source="internal", metadata_json={},
    ))
    db_session.commit()
    monkeypatch.setattr(
        "backend.services.price_series_service.get_price_series",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider path called")),
    )
    with pytest.raises(ReplaySimulationError, match="REPLAY_DATA_MISSING"):
        asyncio.run(ReplaySimulationService(db_session).create(replay_spec()))
