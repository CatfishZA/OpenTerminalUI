from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from backend.simulation.persistence.models import (
    SimulationEventORM,
    SimulationFillORM,
    SimulationLedgerEntryORM,
    SimulationOrderORM,
)
from backend.simulation.persistence.repositories import SqlAlchemySimulationRunRepository
from backend.simulation.services.manifest_service import ManifestService
from backend.services.price_series_service import get_price_series
from backend.tests.simulation.fixtures import run_spec


def _create_run(db_session) -> str:  # noqa: ANN001
    spec = run_spec()
    run_id = "sim_persist"
    manifest = ManifestService(git_commit="test").build(run_id, spec)
    repository = SqlAlchemySimulationRunRepository(db_session)
    repository.create(run_id, spec, manifest)
    return run_id


def test_simulation_run_can_be_inserted_and_read(db_session) -> None:  # noqa: ANN001
    run_id = _create_run(db_session)
    repository = SqlAlchemySimulationRunRepository(db_session)
    assert repository.get(run_id).strategy_key == "example:sma_crossover"
    assert repository.get_manifest(run_id).manifest_hash


def test_event_sequence_uniqueness_is_enforced(db_session) -> None:  # noqa: ANN001
    run_id = _create_run(db_session)
    now = datetime.now(timezone.utc)
    for event_id in ("evt_1", "evt_2"):
        db_session.add(
            SimulationEventORM(
                run_id=run_id,
                sequence=1,
                event_id=event_id,
                event_type="SESSION_START",
                event_time=now,
                processing_time=now,
                payload_json={},
            )
        )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_orders_fills_and_ledger_rows_persist_as_numeric(db_session) -> None:  # noqa: ANN001
    run_id = _create_run(db_session)
    now = datetime.now(timezone.utc)
    db_session.add(
        SimulationOrderORM(
            id="ord_1", run_id=run_id, account_id="acct_1", instrument_key="NASDAQ:EQUITY:AAPL:USD",
            side="BUY", order_type="MARKET", quantity=Decimal("10"), remaining_quantity=Decimal("0"),
            tif="DAY", status="FILLED", submitted_at=now, accepted_at=now, completed_at=now, metadata_json={},
        )
    )
    db_session.add(
        SimulationFillORM(
            id="fill_1", run_id=run_id, order_id="ord_1", account_id="acct_1",
            instrument_key="NASDAQ:EQUITY:AAPL:USD", side="BUY", quantity=Decimal("10"),
            price=Decimal("101.25"), commission=Decimal("1.00"), fees=Decimal("0"),
            slippage_bps=Decimal("2"), executed_at=now, execution_model="fixed_bps", metadata_json={},
        )
    )
    db_session.add(
        SimulationLedgerEntryORM(
            id="led_1", run_id=run_id, account_id="acct_1", event_time=now,
            entry_type="TRADE_PRINCIPAL", currency="USD", amount=Decimal("-1012.50"),
            instrument_key="NASDAQ:EQUITY:AAPL:USD", order_id="ord_1", fill_id="fill_1", metadata_json={},
        )
    )
    db_session.commit()
    assert db_session.get(SimulationFillORM, "fill_1").price == Decimal("101.250000000000000000")
    assert db_session.get(SimulationLedgerEntryORM, "led_1").amount == Decimal("-1012.500000000000000000")


def test_strict_versioned_price_mode_does_not_call_provider(db_session) -> None:  # noqa: ANN001
    class FailFetcher:
        async def fetch_history(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("provider fallback must not be called")

    version, points = asyncio.run(
        get_price_series(
            db_session,
            FailFetcher(),
            "AAPL",
            data_version_id="missing-version",
            strict_persisted=True,
        )
    )
    assert version == "missing-version"
    assert points == []
