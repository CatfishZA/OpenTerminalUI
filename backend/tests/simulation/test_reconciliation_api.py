from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.simulation.api.reconciliation_routes import router
from backend.simulation.api.routes import get_simulation_db
from backend.tests.simulation.reconciliation_test_helpers import INSTRUMENT, canonical_pair


def test_reconciliation_router_is_mounted_in_application() -> None:
    from backend.api.router import api_router

    app = FastAPI()
    app.include_router(api_router)
    paths = set(app.openapi()["paths"])
    assert "/api/v1/simulation/reconciliations" in paths
    assert "/api/v1/simulation/reconciliations/{reconciliation_id}/items" in paths
    assert "/api/v1/simulation/runs/{run_id}/reconciliations" in paths


def test_reconciliation_api_create_get_filter_paginate_and_list(db_session) -> None:  # noqa: ANN001
    baseline, paper, _ = canonical_pair(db_session)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_simulation_db] = lambda: db_session
    client = TestClient(app)
    created = client.post(
        "/api/v1/simulation/reconciliations",
        json={"baseline_run_id": baseline.id, "paper_run_id": paper.id},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "DONE"
    reconciliation_id = body["reconciliation_id"]
    report = client.get(f"/api/v1/simulation/reconciliations/{reconciliation_id}")
    assert report.status_code == 200
    assert report.json()["report_hash"] == body["report_hash"]
    items = client.get(
        f"/api/v1/simulation/reconciliations/{reconciliation_id}/items",
        params={"item_type": "ORDER", "match_status": "MATCHED", "instrument": INSTRUMENT, "offset": 0, "limit": 1},
    )
    assert items.status_code == 200
    assert items.json()["count"] == 1
    assert items.json()["items"][0]["match_confidence"] == "EXACT"
    listed = client.get(f"/api/v1/simulation/runs/{paper.id}/reconciliations", params={"limit": 1})
    assert listed.status_code == 200
    assert listed.json()["items"][0]["reconciliation_id"] == reconciliation_id


def test_reconciliation_api_returns_stable_validation_error(db_session) -> None:  # noqa: ANN001
    baseline, _, _ = canonical_pair(db_session)
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_simulation_db] = lambda: db_session
    response = TestClient(app).post(
        "/api/v1/simulation/reconciliations",
        json={"baseline_run_id": baseline.id, "paper_run_id": baseline.id},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "BASELINE_MODE_INVALID"
