from __future__ import annotations

import asyncio
from sqlalchemy.orm import sessionmaker

from backend.simulation.persistence.models import SimulationCorporateActionEntitlementORM, SimulationLedgerEntryORM
from backend.simulation.services.replay_simulation_service import ReplaySimulationService
from backend.tests.simulation.replay_test_helpers import replay_spec, seed_replay_data
from backend.tests.simulation.test_corporate_action_equivalence import _seed_actions


def test_dividend_entitlement_survives_replay_restart_and_pays_once(db_session) -> None:  # noqa: ANN001
    seed_replay_data(db_session)
    _seed_actions(db_session)
    run_id = asyncio.run(ReplaySimulationService(db_session).create(replay_spec()))
    asyncio.run(ReplaySimulationService(db_session).advance(run_id, sessions=4))
    entitlement = db_session.query(SimulationCorporateActionEntitlementORM).filter_by(run_id=run_id).one()
    assert entitlement.status == "PENDING"
    bind = db_session.get_bind()
    db_session.close()
    fresh = sessionmaker(bind=bind, autocommit=False, autoflush=False)()
    try:
        asyncio.run(ReplaySimulationService(fresh).run_to_end(run_id))
        assert fresh.query(SimulationCorporateActionEntitlementORM).filter_by(run_id=run_id, status="PAID").count() == 1
        assert fresh.query(SimulationLedgerEntryORM).filter_by(run_id=run_id, entry_type="DIVIDEND").count() == 1
    finally:
        fresh.close()
