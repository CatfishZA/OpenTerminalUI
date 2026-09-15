from __future__ import annotations

import pytest

from backend.governance.service import GovernanceError, StrategyGovernanceService
from backend.models import AuditLogORM, DataVersionORM, StrategyGovernanceDecisionORM
from backend.simulation.persistence.models import SimulationRunORM
from backend.tests.governance_test_helpers import seed_actor, seed_baseline


def test_revocation_is_immutable_audited_and_preserves_source_evidence(governance_db) -> None:  # noqa: ANN001
    seed_actor(governance_db)
    baseline = seed_baseline(governance_db)
    service = StrategyGovernanceService(governance_db)
    promoted = service.promote(
        baseline_run_id=baseline.id, target_stage="STAGING",
        actor_user_id="actor-1", reason="reviewed",
    )
    revoked = service.revoke(
        promoted["governance_record_id"], actor_user_id="actor-1", reason="evidence retired"
    )
    assert revoked["decision_type"] == "REVOKE" and revoked["to_stage"] == "REVOKED"
    assert governance_db.get(SimulationRunORM, baseline.id) is baseline
    assert len(service.history(promoted["governance_record_id"])) == 2
    assert governance_db.query(AuditLogORM).filter_by(event_type="governance_strategy_revoked").count() == 1
    with pytest.raises(GovernanceError) as raised:
        service.revoke(promoted["governance_record_id"], actor_user_id="actor-1", reason="again")
    assert raised.value.code == "ALREADY_REVOKED"


def test_repromotion_after_revocation_rechecks_and_appends_new_decision(governance_db) -> None:  # noqa: ANN001
    seed_actor(governance_db)
    baseline = seed_baseline(governance_db)
    service = StrategyGovernanceService(governance_db)
    first = service.promote(baseline_run_id=baseline.id, target_stage="STAGING", actor_user_id="actor-1", reason="first")
    service.revoke(first["governance_record_id"], actor_user_id="actor-1", reason="pause")
    second = service.promote(baseline_run_id=baseline.id, target_stage="STAGING", actor_user_id="actor-1", reason="fresh review")
    assert second["id"] != first["id"] and second["from_stage"] == "REVOKED"
    assert governance_db.query(StrategyGovernanceDecisionORM).count() == 3


def test_evidence_hash_change_is_detectable_and_new_dataset_does_not_mutate_approval(governance_db) -> None:  # noqa: ANN001
    seed_actor(governance_db)
    baseline = seed_baseline(governance_db)
    service = StrategyGovernanceService(governance_db)
    promoted = service.promote(baseline_run_id=baseline.id, target_stage="STAGING", actor_user_id="actor-1", reason="reviewed")
    evidence_hash = promoted["evidence_hash"]
    governance_db.add(DataVersionORM(id="version-new", name="new", source="fixture", is_active=True, metadata_json={}))
    governance_db.commit()
    assert service.get(promoted["governance_record_id"])["latest_evidence_hash"] == evidence_hash
    baseline.result_hash = "mutated-source-hash"
    governance_db.commit()
    assert service.get(promoted["governance_record_id"])["evidence_current"] is False
