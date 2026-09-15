from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.deps import get_db
from backend.api.routes.paper import router as paper_router
from backend.auth.deps import get_current_user
from backend.paper_trading import get_paper_engine
from backend.simulation.api.routes import get_simulation_db, router as simulation_router


def _client(db_session) -> TestClient:  # noqa: ANN001
    app = FastAPI()
    app.include_router(paper_router, prefix="/api")
    app.include_router(simulation_router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_simulation_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="api-paper-user")
    return TestClient(app)


def test_public_paper_api_contract_and_canonical_artifacts(db_session) -> None:  # noqa: ANN001
    client = _client(db_session)
    created = client.post(
        "/api/paper/portfolios",
        json={"name": "API Paper", "initial_capital": "100000.25", "base_currency": "INR"},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["engine"] == "canonical"
    run_id = body["simulation_run_id"]
    portfolio_id = body["id"]

    listed = client.get("/api/paper/portfolios").json()["items"]
    assert listed[0]["simulation_run_id"] == run_id
    assert listed[0]["engine"] == "canonical"

    pending = client.post(
        "/api/paper/orders",
        json={
            "portfolio_id": portfolio_id,
            "symbol": "NSE:API1",
            "side": "buy",
            "order_type": "limit",
            "quantity": "2",
            "limit_price": "100",
        },
    )
    assert pending.status_code == 200
    assert pending.json()["status"] == "pending"
    assert pending.json()["canonical_status"] == "ACCEPTED"

    cancelled = client.post(f"/api/paper/orders/{pending.json()['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["canonical_status"] == "CANCELLED"

    now = datetime.now(timezone.utc).isoformat()
    get_paper_engine()._on_tick({"symbol": "NSE:API2", "ltp": 10, "timestamp": now, "source": "test"})
    filled = client.post(
        "/api/paper/orders",
        json={
            "portfolio_id": portfolio_id,
            "symbol": "NSE:API2",
            "side": "buy",
            "order_type": "market",
            "quantity": "10",
        },
    )
    assert filled.status_code == 200
    assert filled.json()["status"] == "filled"

    positions = client.get(f"/api/paper/portfolios/{portfolio_id}/positions")
    orders = client.get(f"/api/paper/portfolios/{portfolio_id}/orders")
    trades = client.get(f"/api/paper/portfolios/{portfolio_id}/trades")
    performance = client.get(f"/api/paper/portfolios/{portfolio_id}/performance")
    assert positions.status_code == orders.status_code == trades.status_code == performance.status_code == 200
    assert positions.json()["items"][0]["quantity"] == 10
    assert trades.json()["items"][0]["simulation_fill_id"]
    for key in ("equity", "pnl", "cumulative_return", "daily_pnl_curve", "trade_count"):
        assert key in performance.json()

    for artifact in ("orders", "fills", "ledger", "events", "portfolio", "positions"):
        response = client.get(f"/api/v1/simulation/runs/{run_id}/{artifact}")
        assert response.status_code == 200
        assert response.json()["count"] > 0

    second = client.post(
        "/api/paper/portfolios",
        json={"name": "P&L", "initial_capital": "10000", "base_currency": "INR", "settlement_days": 0},
    ).json()
    for side, price in (("buy", 10), ("sell", 12)):
        get_paper_engine()._on_tick(
            {"symbol": "NSE:PNL", "ltp": price, "timestamp": datetime.now(timezone.utc).isoformat(), "source": "test"}
        )
        response = client.post(
            "/api/paper/orders",
            json={
                "portfolio_id": second["id"], "symbol": "NSE:PNL", "side": side,
                "order_type": "market", "quantity": "100", "slippage_bps": "0",
            },
        )
        assert response.status_code == 200 and response.json()["status"] == "filled"
    pnl = client.get(f"/api/paper/portfolios/{second['id']}/performance").json()
    assert pnl["realized_pnl"] == 200


def test_legacy_deploy_strategy_payload_cannot_claim_governed_automation(db_session) -> None:  # noqa: ANN001
    client = _client(db_session)
    response = client.post(
        "/api/paper/deploy-strategy",
        json={
            "name": "Strategy",
            "initial_capital": "1000",
            "symbol": "ABC",
            "market": "NSE",
            "strategy": "example:sma",
            "context": {"window": 20},
        },
    )
    assert response.status_code == 422
