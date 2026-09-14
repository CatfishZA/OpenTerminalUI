from __future__ import annotations

import asyncio
from dataclasses import replace
from decimal import Decimal

from backend.models import CorpActionORM, PriceEodORM
from backend.simulation.domain.enums import SimulationMode
from backend.simulation.persistence.models import (
    SimulationAppliedCorporateActionORM,
    SimulationCorporateActionEntitlementORM,
    SimulationEventORM,
    SimulationLedgerEntryORM,
    SimulationPositionSnapshotORM,
)
from backend.simulation.services.replay_simulation_service import ReplaySimulationService
from backend.simulation.services.simulation_service import SimulationService
from backend.simulation.services.simulator_factory import build_daily_simulator
from backend.tests.simulation.replay_test_helpers import replay_spec, seed_replay_data


def _seed_actions(db) -> None:  # noqa: ANN001
    # Persisted prices are unadjusted: price scale changes on the split session.
    for day, values in {
        "2024-01-04": (52, 54, 50, 52),
        "2024-01-05": (49, 51, 47, 49),
        "2024-01-06": (53, 55, 51, 53),
    }.items():
        row = db.query(PriceEodORM).filter_by(data_version_id="replay-v1", trade_date=day).one()
        row.open, row.high, row.low, row.close = values
    db.add_all([
        CorpActionORM(
            id="split-1", symbol="AAPL", action_date="2024-01-04", ex_date="2024-01-04",
            action_type="SPLIT", factor=2, amount=None, data_version_id="replay-v1",
            source="fixture", metadata_json={},
        ),
        CorpActionORM(
            id="div-1", symbol="AAPL", action_date="2024-01-04", ex_date="2024-01-04",
            pay_date="2024-01-06", action_type="CASH_DIVIDEND", factor=1,
            amount=2, currency="USD", data_version_id="replay-v1", source="fixture", metadata_json={},
        ),
    ])
    db.commit()


def _final_economics(db, run_id: str) -> tuple:  # noqa: ANN001
    position = db.query(SimulationPositionSnapshotORM).filter_by(run_id=run_id).order_by(
        SimulationPositionSnapshotORM.snapshot_time.desc()
    ).first()
    dividend = db.query(SimulationLedgerEntryORM).filter_by(run_id=run_id, entry_type="DIVIDEND").one()
    return (
        Decimal(str(position.quantity)), Decimal(str(position.average_cost)),
        Decimal(str(position.realized_pnl)), Decimal(str(position.unrealized_pnl)),
        Decimal(str(dividend.amount)),
    )


def test_split_and_dividend_backtest_replay_equivalence(db_session) -> None:  # noqa: ANN001
    seed_replay_data(db_session)
    _seed_actions(db_session)
    backtest_spec = replace(replay_spec(), mode=SimulationMode.BACKTEST)
    simulations = SimulationService(db_session)
    backtest_id = asyncio.run(simulations.submit(backtest_spec))
    asyncio.run(simulations.execute(backtest_id, backtest_spec, build_daily_simulator(db_session, backtest_spec)))

    replay = ReplaySimulationService(db_session)
    replay_id = asyncio.run(replay.create(replay_spec()))
    asyncio.run(replay.run_to_end(replay_id))

    assert _final_economics(db_session, backtest_id) == _final_economics(db_session, replay_id)
    assert _final_economics(db_session, replay_id)[:3] == (Decimal("20"), Decimal("49.5"), Decimal("0"))
    assert _final_economics(db_session, replay_id)[4] == Decimal("40")
    assert db_session.query(SimulationAppliedCorporateActionORM).filter_by(run_id=replay_id).count() == 2
    split = db_session.query(SimulationAppliedCorporateActionORM).filter_by(
        run_id=replay_id, corporate_action_source_id="split-1"
    ).one()
    assert Decimal(split.payload_json["factor"]) == 2
    assert Decimal(split.payload_json["old_quantity"]) == 10
    assert Decimal(split.payload_json["new_quantity"]) == 20
    corporate_events = db_session.query(SimulationEventORM).filter_by(
        run_id=replay_id, event_type="CORPORATE_ACTION"
    ).order_by(SimulationEventORM.sequence).all()
    assert any(event.payload_json.get("applied") for event in corporate_events)
    entitlement = db_session.query(SimulationCorporateActionEntitlementORM).filter_by(run_id=replay_id).one()
    assert entitlement.status == "PAID" and Decimal(str(entitlement.eligible_quantity)) == 20
