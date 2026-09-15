from __future__ import annotations

import pytest

from backend.governance.service import StrategyGovernanceService
from backend.tests.governance_test_helpers import seed_baseline


def test_valid_verified_baseline_is_staging_eligible_and_hash_is_deterministic(governance_db) -> None:  # noqa: ANN001
    baseline = seed_baseline(governance_db, code_hash=None)
    governance_db.commit()
    service = StrategyGovernanceService(governance_db)
    first = service.evaluate(baseline_run_id=baseline.id, target_stage="STAGING")
    second = service.evaluate(baseline_run_id=baseline.id, target_stage="STAGING")
    assert first.eligible is True
    assert first.evidence_hash == second.evidence_hash
    code = next(check for check in first.checks if check.code == "CODE_HASH_PRESENT")
    assert code.passed is False and code.blocking is False and code.detail == "CODE_HASH_MISSING"
    assert first.evidence["baseline"]["data_integrity_hash"] == "integrity-hash-a"


@pytest.mark.parametrize(
    ("changes", "failure"),
    [
        ({"verification": "RESEARCH"}, "VERIFIED_BASELINE_REQUIRED"),
        ({"mode": "PAPER"}, "BASELINE_MODE_INVALID"),
        ({"status": "RUNNING"}, "BASELINE_NOT_DONE"),
        ({"result_hash": None}, "RESULT_HASH_REQUIRED"),
        ({"manifest_hash": None}, "MANIFEST_HASH_REQUIRED"),
        ({"data_status": "INVALID"}, "DATA_INTEGRITY_INVALID"),
        ({"accounting": False}, "CANONICAL_RECONCILIATION_FAILED"),
        ({"with_order": False}, "CANONICAL_EVIDENCE_REQUIRED"),
    ],
)
def test_staging_evidence_failures_are_blocking(governance_db, changes, failure) -> None:  # noqa: ANN001
    baseline = seed_baseline(governance_db, **changes)
    governance_db.commit()
    evaluation = StrategyGovernanceService(governance_db).evaluate(
        baseline_run_id=baseline.id, target_stage="STAGING"
    )
    assert evaluation.eligible is False
    assert failure in {
        check.failure_code for check in evaluation.checks if check.blocking and not check.passed
    }


def test_accounting_is_rerun_from_canonical_artifacts(governance_db) -> None:  # noqa: ANN001
    baseline = seed_baseline(governance_db)
    snapshot = baseline.id
    from backend.simulation.persistence.models import SimulationPortfolioSnapshotORM

    row = governance_db.query(SimulationPortfolioSnapshotORM).filter_by(run_id=snapshot).one()
    row.cash_settled = 8999
    governance_db.commit()
    result = StrategyGovernanceService(governance_db).evaluate(
        baseline_run_id=baseline.id, target_stage="STAGING"
    )
    check = next(item for item in result.checks if item.code == "CANONICAL_ACCOUNTING_RECONCILED")
    assert check.passed is False and check.failure_code == "CANONICAL_RECONCILIATION_FAILED"


def test_exact_strategy_and_canonical_provenance_are_required(governance_db) -> None:  # noqa: ANN001
    baseline = seed_baseline(governance_db)
    baseline.strategy_hash = ""
    baseline.data_version_id = None
    baseline.engine_version = ""
    governance_db.commit()
    evaluation = StrategyGovernanceService(governance_db).evaluate(
        baseline_run_id=baseline.id, target_stage="STAGING"
    )
    failures = {
        check.failure_code for check in evaluation.checks if check.blocking and not check.passed
    }
    assert {"STRATEGY_IDENTITY_MISMATCH", "DATA_INTEGRITY_INVALID", "CANONICAL_EVIDENCE_REQUIRED"} <= failures
