from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.simulation.api.routes import get_simulation_db, router


def _client(db_session) -> TestClient:  # noqa: ANN001
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_simulation_db] = lambda: db_session
    return TestClient(app)


def _payload() -> dict:
    return {
        "mode": "BACKTEST",
        "verification_level": "RESEARCH",
        "strategy": {"key": "example:sma_crossover", "context": {"short_window": 20, "long_window": 50}},
        "universe": [{"symbol": "AAPL", "venue": "NASDAQ", "asset_class": "EQUITY", "currency": "USD"}],
        "start": "2024-01-01",
        "end": "2024-12-31",
        "account": {"initial_cash": "100000", "base_currency": "USD", "settlement_days": 1},
        "execution": {"model": "fixed_bps", "slippage_bps": "2"},
        "commission": {"model": "bps", "bps": "1", "minimum": "0"},
        "seed": 42,
    }


def test_simulation_router_is_mounted(db_session) -> None:  # noqa: ANN001
    paths = set(_client(db_session).get("/openapi.json").json()["paths"])
    assert "/api/v1/simulation/runs" in paths
    assert "/api/v1/simulation/runs/{run_id}/manifest" in paths


def test_create_research_run_and_read_status(db_session) -> None:  # noqa: ANN001
    client = _client(db_session)
    response = client.post("/api/v1/simulation/runs", json=_payload())
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    status = client.get(f"/api/v1/simulation/runs/{body['run_id']}/status")
    assert status.status_code == 200
    assert status.json()["stage"] == "not_executed"


def test_verified_without_data_version_fails_validation(db_session) -> None:  # noqa: ANN001
    payload = _payload()
    payload["verification_level"] = "VERIFIED"
    response = _client(db_session).post("/api/v1/simulation/runs", json=payload)
    assert response.status_code == 422
    assert "DATA_VERSION_REQUIRED" in response.text


def test_malformed_instrument_identity_fails_validation(db_session) -> None:  # noqa: ANN001
    payload = _payload()
    payload["universe"][0]["venue"] = ""
    response = _client(db_session).post("/api/v1/simulation/runs", json=payload)
    assert response.status_code == 422


def test_scaffold_detail_endpoints_return_no_fabricated_records(db_session) -> None:  # noqa: ANN001
    client = _client(db_session)
    run_id = client.post("/api/v1/simulation/runs", json=_payload()).json()["run_id"]
    result = client.get(f"/api/v1/simulation/runs/{run_id}").json()
    assert result["result"] is None
    assert result["stage"] == "not_executed"
    for resource in ("orders", "fills", "ledger", "events", "portfolio", "positions"):
        response = client.get(f"/api/v1/simulation/runs/{run_id}/{resource}")
        assert response.status_code == 200
        assert response.json()["items"] == []
