from __future__ import annotations

import asyncio

import pytest

from backend.models import PaperStrategyDeploymentORM, SimulationRunORM
from backend.paper_trading.deployment_domain import DeploymentError
from backend.paper_trading.strategy_deployment_service import StrategyDeploymentService
from backend.tests.paper_deployment_test_helpers import governed_deployment


def test_staging_deployment_copies_identity_and_creates_only_paper(governance_db) -> None:  # noqa: ANN001
    actor, baseline, result = governed_deployment(governance_db)
    deployment = governance_db.get(PaperStrategyDeploymentORM, result["id"])
    run = governance_db.get(SimulationRunORM, result["simulation_run_id"])
    assert result["status"] == "CREATED"
    assert (deployment.strategy_key, deployment.strategy_hash, deployment.code_hash) == (
        baseline.strategy_key, baseline.strategy_hash, baseline.code_hash,
    )
    assert run.mode == "PAPER" and run.verification_level == "RESEARCH" and run.status == "RUNNING"
    assert run.request_json["deployment"]["governance_record_id"] == deployment.governance_record_id
    assert governance_db.query(SimulationRunORM).filter_by(mode="LIVE").count() == 0


def test_candidate_revoked_and_stale_evidence_are_blocked(governance_db) -> None:  # noqa: ANN001
    actor, baseline, result = governed_deployment(governance_db)
    service = StrategyDeploymentService(governance_db)
    deployment = governance_db.get(PaperStrategyDeploymentORM, result["id"])
    record = service.db.get(__import__("backend.models", fromlist=["StrategyGovernanceRecordORM"]).StrategyGovernanceRecordORM, deployment.governance_record_id)
    record.current_stage = "REVOKED"
    governance_db.commit()
    with pytest.raises(DeploymentError, match="GOVERNANCE_STAGE_NOT_DEPLOYABLE"):
        service.create(governance_record_id=record.id, user_id=actor.id, name="blocked")
    record.current_stage = "STAGING"
    record.latest_evidence_hash = "drift"
    governance_db.commit()
    with pytest.raises(DeploymentError, match="GOVERNANCE_EVIDENCE_STALE"):
        asyncio.run(service.start(result["id"], user_id=actor.id))


def test_client_configuration_is_reconstructed_from_baseline(governance_db) -> None:  # noqa: ANN001
    _actor, baseline, result = governed_deployment(governance_db)
    deployment = governance_db.get(PaperStrategyDeploymentORM, result["id"])
    assert deployment.strategy_config_json["strategy_context"] == baseline.request_json["strategy_context"]
    assert deployment.symbols_json == baseline.request_json["universe"]
    assert deployment.strategy_config_hash


def test_prod_strategy_can_create_deployment(governance_db) -> None:  # noqa: ANN001
    _actor, _baseline, result = governed_deployment(governance_db, stage="PROD")
    assert result["status"] == "CREATED"


def test_unresolved_or_mismatched_baseline_configuration_is_blocked(governance_db) -> None:  # noqa: ANN001
    actor, baseline, result = governed_deployment(governance_db)
    deployment = governance_db.get(PaperStrategyDeploymentORM, result["id"])
    baseline.request_json = {"strategy": baseline.strategy_key}
    governance_db.commit()
    with pytest.raises(DeploymentError, match="STRATEGY_CONFIG_UNRESOLVED"):
        StrategyDeploymentService(governance_db).create(
            governance_record_id=deployment.governance_record_id, user_id=actor.id, name="bad",
        )
