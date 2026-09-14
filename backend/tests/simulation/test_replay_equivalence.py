from __future__ import annotations

import asyncio
from dataclasses import replace
from decimal import Decimal, InvalidOperation

from backend.simulation.domain.enums import SimulationMode
from backend.simulation.persistence.models import (
    SimulationEventORM, SimulationFillORM, SimulationLedgerEntryORM, SimulationOrderORM,
    SimulationPortfolioSnapshotORM,
)
from backend.simulation.services.replay_simulation_service import ReplaySimulationService
from backend.simulation.services.simulation_service import SimulationService
from backend.simulation.services.simulator_factory import build_daily_simulator
from backend.tests.simulation.replay_test_helpers import replay_spec, seed_replay_data


def _economic(db, run_id: str) -> dict:  # noqa: ANN001
    def event_payload(row):  # noqa: ANN001
        payload = dict(row.payload_json or {})
        if "fill_ids" in payload:
            payload["fill_ids"] = len(payload["fill_ids"])
        def normalize(value):  # noqa: ANN001
            if isinstance(value, dict):
                return {key: normalize(item) for key, item in value.items()}
            if isinstance(value, str):
                try:
                    return format(Decimal(value).normalize(), "f")
                except InvalidOperation:
                    return value
            return value
        return normalize(payload)

    return {
        "events": [(row.event_type, row.event_time, row.instrument_key, event_payload(row)) for row in db.query(SimulationEventORM).filter_by(run_id=run_id).order_by(SimulationEventORM.sequence)],
        "orders": [(row.instrument_key, row.side, row.order_type, row.quantity, row.remaining_quantity, row.tif, row.status, row.submitted_at, row.accepted_at, row.completed_at) for row in db.query(SimulationOrderORM).filter_by(run_id=run_id).order_by(SimulationOrderORM.submitted_at, SimulationOrderORM.id)],
        "fills": [(row.instrument_key, row.side, row.quantity, row.price, row.commission, row.fees, row.slippage_bps, row.executed_at) for row in db.query(SimulationFillORM).filter_by(run_id=run_id).order_by(SimulationFillORM.executed_at, SimulationFillORM.id)],
        "ledger": [(row.entry_type, row.currency, row.amount, row.event_time) for row in db.query(SimulationLedgerEntryORM).filter_by(run_id=run_id).order_by(SimulationLedgerEntryORM.event_time, SimulationLedgerEntryORM.id)],
        "portfolio": [(row.snapshot_time, row.cash_settled, row.cash_unsettled, row.cash_reserved, row.realized_pnl, row.unrealized_pnl, row.fees, row.equity, row.buying_power) for row in db.query(SimulationPortfolioSnapshotORM).filter_by(run_id=run_id).order_by(SimulationPortfolioSnapshotORM.snapshot_time)],
    }


def test_backtest_replay_and_step_sizes_are_economically_equivalent(db_session) -> None:  # noqa: ANN001
    seed_replay_data(db_session)
    backtest = replace(replay_spec(), mode=SimulationMode.BACKTEST)
    simulation = SimulationService(db_session)
    backtest_id = asyncio.run(simulation.submit(backtest))
    asyncio.run(simulation.execute(backtest_id, backtest, build_daily_simulator(db_session, backtest)))

    replay = ReplaySimulationService(db_session)
    stepped_id = asyncio.run(replay.create(replay_spec()))
    while asyncio.run(replay.state(stepped_id)).status.value != "DONE":
        asyncio.run(replay.advance(stepped_id))
    batch_id = asyncio.run(replay.create(replay_spec()))
    asyncio.run(replay.run_to_end(batch_id))

    assert _economic(db_session, backtest_id) == _economic(db_session, stepped_id)
    assert _economic(db_session, stepped_id) == _economic(db_session, batch_id)
