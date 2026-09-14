from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.simulation.api.replay_routes import router
from backend.simulation.api.routes import router as simulation_router
from backend.simulation.api.routes import get_simulation_db
from backend.tests.simulation.replay_test_helpers import seed_replay_data


def test_replay_router_create_advance_market_and_finish(db_session) -> None:  # noqa: ANN001
    seed_replay_data(db_session)
    app = FastAPI()
    app.include_router(simulation_router)
    app.include_router(router)
    app.dependency_overrides[get_simulation_db] = lambda: db_session
    client = TestClient(app)
    payload = {
        "verification_level": "VERIFIED",
        "strategy": {"key": "example:sma_crossover", "context": {"short_window": 1, "long_window": 2, "quantity": 10}},
        "universe": [{"symbol": "AAPL", "venue": "NASDAQ", "asset_class": "EQUITY", "currency": "USD"}],
        "start": "2024-01-01", "end": "2024-01-06",
        "account": {"initial_cash": "100000", "base_currency": "USD", "settlement_days": 1},
        "data_version_id": "replay-v1",
        "execution": {"model": "fixed_bps", "slippage_bps": "0", "daily_bar_path_policy": "WORST_CASE"},
        "commission": {"model": "bps", "bps": "0", "minimum": "0"}, "seed": 42,
    }
    created = client.post("/api/v1/simulation/replays", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "READY"
    run_id = created.json()["run_id"]
    assert client.get(f"/api/v1/simulation/replays/{run_id}/market", params={"instrument": "NASDAQ:EQUITY:AAPL:USD"}).json()["count"] == 0
    assert client.post(f"/api/v1/simulation/replays/{run_id}/advance", json={"sessions": 1}).json()["completed_sessions"] == 1
    assert client.get(f"/api/v1/simulation/runs/{run_id}/events").json()["count"] > 0
    assert client.get(f"/api/v1/simulation/runs/{run_id}/portfolio").json()["count"] == 1
    assert client.get(f"/api/v1/simulation/replays/{run_id}/market", params={"instrument": "NASDAQ:EQUITY:AAPL:USD"}).json()["count"] == 1
    assert client.post(f"/api/v1/simulation/replays/{run_id}/run-to-end").json()["status"] == "DONE"
