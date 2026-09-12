from __future__ import annotations

import asyncio
import json

from sqlalchemy.orm import sessionmaker

from backend.api.routes import backtests
from backend.simulation.api import routes as simulation_routes
from backend.models import BacktestRun, DataVersionORM, PriceEodORM
from backend.services import backtest_jobs
from backend.services.backtest_jobs import BacktestJobRequest, BacktestJobService
from backend.simulation.persistence.models import SimulationRunORM
from backend.simulation.services.simulation_service import SimulationService


def _seed(db_session) -> None:  # noqa: ANN001
    db_session.add(DataVersionORM(
        id="version-1", name="verified", source="internal", is_active=True,
        metadata_json={"dataset_hash": "dataset-1", "calendar_version": "fixture-v1"},
    ))
    closes = [100, 101, 103, 104]
    for day, close in enumerate(closes, start=1):
        db_session.add(PriceEodORM(
            symbol="AAPL", trade_date=f"2024-01-0{day}", open=close,
            high=close + 1, low=close - 1, close=close, volume=100000,
            data_version_id="version-1",
        ))
    db_session.commit()


def _request(**changes) -> BacktestJobRequest:  # noqa: ANN003
    values = dict(
        symbol="AAPL", market="NASDAQ", start="2024-01-01", end="2024-01-04",
        strategy="example:sma_crossover",
        context={"short_window": 1, "long_window": 2, "quantity": 10},
        config={"allow_short": False}, verification_level="VERIFIED",
        data_version_id="version-1", currency="USD",
    )
    values.update(changes)
    return BacktestJobRequest(**values)


def _service(db_session, monkeypatch) -> tuple[BacktestJobService, sessionmaker]:  # noqa: ANN001
    factory = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    monkeypatch.setattr(backtest_jobs, "get_db", lambda: iter([factory()]))
    async def quiet_worker() -> None:
        return None
    async def quiet_broadcast(payload) -> None:  # noqa: ANN001
        return None
    service = BacktestJobService()
    monkeypatch.setattr(service, "ensure_worker", quiet_worker)
    monkeypatch.setattr(backtest_jobs.ws_manager, "broadcast_to_all", quiet_broadcast)
    return service, factory


def test_research_submission_does_not_create_simulation(db_session, monkeypatch) -> None:  # noqa: ANN001
    service, factory = _service(db_session, monkeypatch)
    run_id = asyncio.run(service.submit(BacktestJobRequest(symbol="AAPL")))
    db = factory()
    try:
        row = db.query(BacktestRun).filter_by(run_id=run_id).one()
        assert run_id.startswith("bt_") and row.simulation_run_id is None
        assert db.query(SimulationRunORM).count() == 0
    finally:
        db.close()


def test_verified_run_links_executes_without_fallback_and_is_durable(db_session, monkeypatch) -> None:  # noqa: ANN001
    _seed(db_session)
    service, factory = _service(db_session, monkeypatch)
    monkeypatch.setattr(backtest_jobs.BacktestEngine, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy engine called")))
    monkeypatch.setattr(service, "_fetch_with_market_fallback", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("market fallback called")))
    monkeypatch.setattr(service, "_build_synthetic_frame", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("synthetic fallback called")))

    bt_id = asyncio.run(service.submit(_request()))
    db = factory()
    try:
        linked = db.query(BacktestRun).filter_by(run_id=bt_id).one()
        sim_id = linked.simulation_run_id
        assert bt_id.startswith("bt_") and sim_id.startswith("sim_")
        assert db.get(SimulationRunORM, sim_id).verification_level == "VERIFIED"
    finally:
        db.close()

    asyncio.run(service._execute(bt_id))
    legacy = asyncio.run(service.get_result(bt_id))
    assert legacy["status"] == "done" and legacy["result"] is not None
    assert asyncio.run(service.get_status(bt_id)) == {"run_id": bt_id, "status": "done"}
    assert legacy["result"]["simulation_run_id"] == sim_id
    assert legacy["result"]["verification_level"] == "VERIFIED"
    assert legacy["result"]["result_hash"]
    assert legacy["result"]["manifest_hash"]

    fresh_db = factory()
    try:
        canonical = asyncio.run(SimulationService(fresh_db).result(sim_id))
        assert canonical["status"] == "DONE"
        assert canonical["result"]["result_hash"] == legacy["result"]["result_hash"]
        api_result = asyncio.run(simulation_routes.run_result(sim_id, SimulationService(fresh_db)))
        assert api_result.result["result_hash"] == legacy["result"]["result_hash"]
    finally:
        fresh_db.close()

    monkeypatch.setattr(backtests, "get_backtest_job_service", lambda: service)
    analytics = asyncio.run(backtests.backtest_analytics(bt_id, rolling_window=10, histogram_bins=10))
    robustness = asyncio.run(backtests.backtest_robustness(bt_id, n_permutations=50, n_windows=2))
    assert "analytics" in analytics and "robustness" in robustness


def test_verified_missing_persisted_data_fails_without_fallback(db_session, monkeypatch) -> None:  # noqa: ANN001
    db_session.add(DataVersionORM(id="version-1", name="empty", source="internal", metadata_json={}))
    db_session.commit()
    service, factory = _service(db_session, monkeypatch)
    monkeypatch.setattr(service, "_fetch_with_market_fallback", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("market fallback called")))
    monkeypatch.setattr(service, "_build_synthetic_frame", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("synthetic fallback called")))
    bt_id = asyncio.run(service.submit(_request()))
    asyncio.run(service._execute(bt_id))
    result = asyncio.run(service.get_result(bt_id))
    assert result["status"] == "failed"
    assert "INSTRUMENT_DATA_NOT_FOUND" in result["error"]
    db = factory()
    try:
        linked = db.query(BacktestRun).filter_by(run_id=bt_id).one()
        simulation_id = linked.simulation_run_id
        assert db.get(SimulationRunORM, simulation_id).status == "FAILED"
        canonical = asyncio.run(SimulationService(db).result(simulation_id))
        assert canonical["result"] is None
        assert "INSTRUMENT_DATA_NOT_FOUND" in canonical["error"]
    finally:
        db.close()
