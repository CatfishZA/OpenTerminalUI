from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.deps import get_db
from backend.api.routes.paper import router
from backend.auth.deps import get_current_user
from backend.tests.paper_deployment_test_helpers import bar, governed_deployment


def test_canonical_deployment_api_lifecycle_and_evidence(governance_db) -> None:  # noqa: ANN001
    actor, _baseline, seeded = governed_deployment(governance_db)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: governance_db
    app.dependency_overrides[get_current_user] = lambda: actor
    client = TestClient(app)
    created = client.post("/api/paper/deployments", json={
        "governance_record_id": seeded["governance_record_id"], "name": "API deployment",
        "risk_policy": {"max_order_notional": "1000"},
    })
    assert created.status_code == 200 and created.json()["status"] == "CREATED"
    deployment_id = created.json()["id"]
    assert client.post(f"/api/paper/deployments/{deployment_id}/start", json={}).json()["status"] == "RUNNING"
    observation = bar(source_event_id="api-bar")
    payload = {
        "deployment_id": deployment_id, "source_event_id": observation.source_event_id,
        "instrument": observation.instrument.key, "interval": "1d",
        "start_time": observation.start_time.isoformat(), "end_time": observation.end_time.isoformat(),
        "open": str(observation.open), "high": str(observation.high), "low": str(observation.low),
        "close": str(observation.close), "volume": str(observation.volume), "source": observation.source,
        "complete": True,
    }
    assert client.post("/api/paper/market/bar", json=payload).json()["status"] == "PROCESSED"
    assert len(client.get(f"/api/paper/deployments/{deployment_id}/intents").json()["items"]) == 1
    assert client.get(f"/api/paper/deployments/{deployment_id}/events").json()["items"]
    assert any(item["id"] == deployment_id for item in client.get("/api/paper/deployments").json()["items"])


def test_deployment_api_forbids_strategy_identity_overrides(governance_db) -> None:  # noqa: ANN001
    actor, _baseline, seeded = governed_deployment(governance_db)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: governance_db
    app.dependency_overrides[get_current_user] = lambda: actor
    response = TestClient(app).post("/api/paper/deployments", json={
        "governance_record_id": seeded["governance_record_id"],
        "strategy_hash": "spoof", "context": {"quantity": 999}, "symbol": "OTHER",
    })
    assert response.status_code == 422
