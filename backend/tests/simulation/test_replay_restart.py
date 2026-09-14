from __future__ import annotations

import asyncio

from sqlalchemy.orm import sessionmaker

from backend.simulation.persistence.models import SimulationEventORM, SimulationSettlementObligationORM
from backend.simulation.services.replay_simulation_service import ReplaySimulationService
from backend.tests.simulation.replay_test_helpers import replay_spec, seed_replay_data


def test_restart_restores_checkpoint_strategy_orders_and_settlements(db_session) -> None:  # noqa: ANN001
    seed_replay_data(db_session)
    service = ReplaySimulationService(db_session)
    strategy = "def generate_signals(df, context):\n    return [1 if i == 1 else 0 for i in range(len(df))]"
    run_id = asyncio.run(service.create(replay_spec(
        strategy=strategy, settlement_profile={"settlement_days": 2},
    )))
    asyncio.run(service.advance(run_id, sessions=4))
    checkpoint = asyncio.run(service.state(run_id)).checkpoint_hash
    assert db_session.query(SimulationSettlementObligationORM).filter_by(run_id=run_id, status="PENDING").count() == 1
    db_session.close()

    fresh = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)()
    try:
        restarted = ReplaySimulationService(fresh)
        assert asyncio.run(restarted.state(run_id)).checkpoint_hash == checkpoint
        done = asyncio.run(restarted.run_to_end(run_id))
        sequences = [row.sequence for row in fresh.query(SimulationEventORM).filter_by(run_id=run_id).order_by(SimulationEventORM.sequence)]
        assert done.status.value == "DONE"
        assert sequences == list(range(1, len(sequences) + 1))
        assert fresh.query(SimulationSettlementObligationORM).filter_by(run_id=run_id, status="PENDING").count() == 0
    finally:
        fresh.close()


def test_t_zero_and_t_one_settlement_are_persistently_supported(db_session) -> None:  # noqa: ANN001
    seed_replay_data(db_session)
    strategy = "def generate_signals(df, context):\n    return [1 if i == 1 else 0 for i in range(len(df))]"
    service = ReplaySimulationService(db_session)
    t0 = asyncio.run(service.create(replay_spec(strategy=strategy, settlement_profile={"settlement_days": 0})))
    asyncio.run(service.advance(t0, sessions=4))
    assert db_session.query(SimulationSettlementObligationORM).filter_by(run_id=t0).count() == 0

    t1 = asyncio.run(service.create(replay_spec(strategy=strategy, settlement_profile={"settlement_days": 1})))
    asyncio.run(service.advance(t1, sessions=4))
    assert db_session.query(SimulationSettlementObligationORM).filter_by(run_id=t1, status="PENDING").count() == 1
    asyncio.run(service.advance(t1))
    assert db_session.query(SimulationSettlementObligationORM).filter_by(run_id=t1, status="SETTLED").count() == 1
