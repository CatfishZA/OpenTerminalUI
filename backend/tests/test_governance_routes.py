from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.deps import get_db
from backend.api.routes.governance import router as governance_router
from backend.auth.deps import get_current_user
from backend.shared.db import Base
from backend.models import DataVersionORM, ModelExperiment, ModelRun, StrategyGovernanceDecisionORM
from backend.tests.governance_test_helpers import seed_actor, seed_baseline


def _build_app() -> tuple[TestClient, sessionmaker]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    app = FastAPI()
    app.include_router(governance_router, prefix="/api")

    def _db_override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def _user_override():
        return type("FakeUser", (), {"id": "u_test"})()

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_user] = _user_override
    return TestClient(app), SessionLocal


def test_governance_register_compare_promote() -> None:
    client, SessionLocal = _build_app()
    db = SessionLocal()
    try:
        dv = DataVersionORM(name="v1", description="", source="test", is_active=True, metadata_json={})
        exp = ModelExperiment(
            name="exp",
            description="",
            tags=[],
            model_key="example:sma_crossover",
            params_json={},
            universe_json={},
            benchmark_symbol=None,
            start_date="2024-01-01",
            end_date="2024-12-31",
            cost_model_json={},
        )
        db.add(dv)
        db.add(exp)
        db.commit()
        db.refresh(exp)
        run = ModelRun(experiment_id=exp.id, backtest_run_id="bt1", status="done")
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
        dv_id = dv.id
    finally:
        db.close()

    reg = client.post("/api/governance/runs/register", json={"run_id": run_id, "data_version_id": dv_id, "code_hash": "abc123", "execution_profile": {"slippage_bps": 3}})
    assert reg.status_code == 200
    cmp = client.get(f"/api/governance/runs/compare?run_ids={run_id}")
    assert cmp.status_code == 200
    assert len(cmp.json()["items"]) == 1
    promote = client.post("/api/governance/model-registry/promote", json={"registry_name": "main-model", "run_id": run_id, "stage": "staging", "reason": "reviewed"})
    assert promote.status_code == 409
    assert promote.json()["detail"]["code"] == "CANONICAL_EVIDENCE_REQUIRED"


def test_canonical_governance_api_lifecycle_and_client_hash_is_not_trusted() -> None:
    client, SessionLocal = _build_app()
    db = SessionLocal()
    try:
        seed_actor(db, "u_test")
        baseline = seed_baseline(db)
        baseline_id = baseline.id
        db.commit()
    finally:
        db.close()

    evaluation = client.post("/api/governance/strategies/evaluate", json={
        "baseline_run_id": baseline_id, "target_stage": "STAGING",
    })
    assert evaluation.status_code == 200 and evaluation.json()["eligible"] is True
    promoted = client.post("/api/governance/strategies/promote", json={
        "baseline_run_id": baseline_id, "target_stage": "STAGING",
        "reason": "API review", "registry_name": "api-model",
        "evidence_hash": "client-spoof",
    })
    assert promoted.status_code == 200
    body = promoted.json()
    assert body["evidence_hash"] != "client-spoof"
    record_id = body["governance_record_id"]
    assert client.get(f"/api/governance/strategies/{record_id}").status_code == 200
    history = client.get(f"/api/governance/strategies/{record_id}/history")
    assert len(history.json()["items"]) == 1
    listing = client.get("/api/governance/strategies?stage=STAGING&strategy_key=fixture:sma")
    assert [item["id"] for item in listing.json()["items"]] == [record_id]
    revoked = client.post(
        f"/api/governance/strategies/{record_id}/revoke", json={"reason": "API revoke"}
    )
    assert revoked.status_code == 200 and revoked.json()["to_stage"] == "REVOKED"
    db = SessionLocal()
    try:
        assert db.query(StrategyGovernanceDecisionORM).count() == 2
    finally:
        db.close()


def test_canonical_governance_api_requires_authentication() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    app = FastAPI()
    app.include_router(governance_router, prefix="/api")

    def _db_override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db_override
    response = TestClient(app).post("/api/governance/strategies/evaluate", json={
        "baseline_run_id": "sim_missing", "target_stage": "STAGING",
    })
    assert response.status_code == 401
