from __future__ import annotations

import pytest

from backend.governance.service import GovernanceError, StrategyGovernanceService
from backend.models import AuditLogORM, ModelRegistryORM, StrategyGovernanceDecisionORM, StrategyGovernanceRecordORM
from backend.simulation.persistence.models import SimulationOrderORM, SimulationRunORM
from backend.tests.governance_test_helpers import seed_actor, seed_baseline


def test_staging_persists_identity_decision_projection_audit_and_no_execution(governance_db) -> None:  # noqa: ANN001
    seed_actor(governance_db)
    baseline = seed_baseline(governance_db)
    before_runs = governance_db.query(SimulationRunORM).count()
    before_orders = governance_db.query(SimulationOrderORM).count()
    result = StrategyGovernanceService(governance_db).promote(
        baseline_run_id=baseline.id, target_stage="STAGING", actor_user_id="actor-1",
        reason="Canonical baseline reviewed", registry_name="main-model",
    )
    assert result["from_stage"] == "CANDIDATE" and result["to_stage"] == "STAGING"
    record = governance_db.get(StrategyGovernanceRecordORM, result["governance_record_id"])
    decision = governance_db.get(StrategyGovernanceDecisionORM, result["id"])
    projection = governance_db.query(ModelRegistryORM).filter_by(governance_record_id=record.id).one()
    assert (record.strategy_key, record.strategy_hash) == (baseline.strategy_key, baseline.strategy_hash)
    assert decision.evidence_json["baseline"]["simulation_run_id"] == baseline.id
    assert projection.evidence_level == "CANONICAL" and projection.governance_decision_id == decision.id
    assert governance_db.query(AuditLogORM).filter_by(event_type="governance_strategy_promoted").count() == 1
    assert governance_db.query(SimulationRunORM).count() == before_runs
    assert governance_db.query(SimulationOrderORM).count() == before_orders
    assert governance_db.query(SimulationRunORM).filter_by(mode="LIVE").count() == 0
    assert governance_db.query(SimulationRunORM).filter_by(mode="PAPER").count() == 0


def test_same_identity_is_idempotent_and_changed_hash_is_distinct(governance_db) -> None:  # noqa: ANN001
    seed_actor(governance_db)
    first_run = seed_baseline(governance_db)
    second_run = seed_baseline(governance_db, run_id="sim_other", strategy_hash="strategy-hash-b", result_hash="result-b", manifest_hash="manifest-b")
    service = StrategyGovernanceService(governance_db)
    first = service.promote(baseline_run_id=first_run.id, target_stage="STAGING", actor_user_id="actor-1", reason="reviewed")
    repeated = service.promote(baseline_run_id=first_run.id, target_stage="STAGING", actor_user_id="actor-1", reason="reviewed")
    second = service.promote(baseline_run_id=second_run.id, target_stage="STAGING", actor_user_id="actor-1", reason="reviewed")
    assert first["id"] == repeated["id"]
    assert first["governance_record_id"] != second["governance_record_id"]
    assert governance_db.query(StrategyGovernanceDecisionORM).count() == 2


def test_promotion_requires_actor_reason_and_nonempty_strategy_evidence(governance_db) -> None:  # noqa: ANN001
    seed_actor(governance_db)
    baseline = seed_baseline(governance_db)
    service = StrategyGovernanceService(governance_db)
    with pytest.raises(GovernanceError, match="AUTHENTICATION_REQUIRED"):
        service.promote(baseline_run_id=baseline.id, target_stage="STAGING", actor_user_id="", reason="reviewed")
    with pytest.raises(GovernanceError, match="AUTHENTICATION_REQUIRED"):
        service.promote(baseline_run_id=baseline.id, target_stage="STAGING", actor_user_id="not-a-user", reason="reviewed")
    with pytest.raises(GovernanceError, match="PROMOTION_REASON_REQUIRED"):
        service.promote(baseline_run_id=baseline.id, target_stage="STAGING", actor_user_id="actor-1", reason=" ")
