from __future__ import annotations

import pytest

from backend.governance.service import GovernanceError, StrategyGovernanceService
from backend.simulation.persistence.models import SimulationOrderORM
from backend.tests.governance_test_helpers import seed_actor, seed_baseline, seed_paper, seed_reconciliation


def _staged(governance_db):  # noqa: ANN001
    seed_actor(governance_db)
    baseline = seed_baseline(governance_db)
    service = StrategyGovernanceService(governance_db)
    service.promote(
        baseline_run_id=baseline.id, target_stage="STAGING",
        actor_user_id="actor-1", reason="baseline reviewed",
    )
    return service, baseline


def test_candidate_to_prod_is_blocked(governance_db) -> None:  # noqa: ANN001
    seed_actor(governance_db)
    baseline = seed_baseline(governance_db)
    with pytest.raises(GovernanceError) as raised:
        StrategyGovernanceService(governance_db).promote(
            baseline_run_id=baseline.id, target_stage="PROD",
            actor_user_id="actor-1", reason="approve",
        )
    assert raised.value.code == "STAGING_APPROVAL_REQUIRED"


def test_valid_paper_and_reconciliation_permit_prod_without_profit_gate_or_side_effect(governance_db) -> None:  # noqa: ANN001
    service, baseline = _staged(governance_db)
    paper = seed_paper(governance_db, baseline)
    reconciliation = seed_reconciliation(governance_db, baseline, paper)
    counts = {
        "runs": governance_db.query(type(baseline)).count(),
        "orders": governance_db.query(SimulationOrderORM).count(),
    }
    result = service.promote(
        baseline_run_id=baseline.id, target_stage="PROD", paper_run_id=paper.id,
        reconciliation_id=reconciliation.id, actor_user_id="actor-1",
        reason="paper execution reviewed",
    )
    assert result["to_stage"] == "PROD"
    assert baseline.result_json["summary"]["total_return"] == "-0.10"
    assert governance_db.query(type(baseline)).count() == counts["runs"]
    assert governance_db.query(SimulationOrderORM).count() == counts["orders"]
    assert governance_db.query(type(baseline)).filter_by(mode="LIVE").count() == 0


@pytest.mark.parametrize(
    ("case", "failure"),
    [
        ("code", "CODE_HASH_REQUIRED_FOR_PROD"),
        ("paper_missing", "PAPER_RUN_REQUIRED"),
        ("paper_mode", "PAPER_MODE_INVALID"),
        ("paper_strategy", "PAPER_STRATEGY_MISMATCH"),
        ("reconciliation_missing", "RECONCILIATION_REQUIRED"),
        ("pair", "RECONCILIATION_PAIR_MISMATCH"),
        ("intent", "RECONCILIATION_NOT_COMPARABLE"),
        ("accounting", "RECONCILIATION_NOT_COMPARABLE"),
        ("ambiguous", "RECONCILIATION_AMBIGUOUS"),
        ("low", "RECONCILIATION_NOT_COMPARABLE"),
        ("baseline_only", "RECONCILIATION_NOT_COMPARABLE"),
        ("paper_only", "RECONCILIATION_NOT_COMPARABLE"),
        ("empty", "PAPER_EVIDENCE_EMPTY"),
        ("source_hash", "EVIDENCE_INTEGRITY_MISMATCH"),
    ],
)
def test_prod_default_policy_blocks_weak_or_mismatched_evidence(governance_db, case: str, failure: str) -> None:  # noqa: ANN001
    service, baseline = _staged(governance_db)
    paper = seed_paper(governance_db, baseline)
    kwargs = {}
    if case == "code": baseline.code_hash = None
    if case == "paper_mode": paper.mode = "BACKTEST"
    if case == "paper_strategy": paper.strategy_hash = "other"
    if case == "intent": kwargs["intent"] = False
    if case == "accounting": kwargs["accounting"] = False
    if case == "ambiguous": kwargs["ambiguous"] = 1
    if case == "low": kwargs["low"] = 1
    if case == "baseline_only": kwargs["baseline_only"] = 1
    if case == "paper_only": kwargs["paper_only"] = 1
    if case == "empty": kwargs.update(matched=0, paper_fills=0)
    reconciliation = seed_reconciliation(governance_db, baseline, paper, **kwargs)
    paper_id = None if case == "paper_missing" else paper.id
    reconciliation_id = None if case == "reconciliation_missing" else reconciliation.id
    if case == "pair":
        other = seed_paper(governance_db, baseline, run_id="sim_other_paper")
        reconciliation.paper_run_id = other.id
    if case == "source_hash":
        reconciliation.baseline_result_hash = "tampered"
    governance_db.commit()
    with pytest.raises(GovernanceError) as raised:
        service.promote(
            baseline_run_id=baseline.id, target_stage="PROD", paper_run_id=paper_id,
            reconciliation_id=reconciliation_id, actor_user_id="actor-1", reason="approve",
        )
    assert raised.value.code == failure


def test_reconciliation_must_be_done_with_report_hash(governance_db) -> None:  # noqa: ANN001
    service, baseline = _staged(governance_db)
    paper = seed_paper(governance_db, baseline)
    reconciliation = seed_reconciliation(governance_db, baseline, paper, status="FAILED")
    reconciliation.report_hash = None
    governance_db.commit()
    with pytest.raises(GovernanceError) as raised:
        service.promote(
            baseline_run_id=baseline.id, target_stage="PROD", paper_run_id=paper.id,
            reconciliation_id=reconciliation.id, actor_user_id="actor-1", reason="approve",
        )
    assert raised.value.code == "RECONCILIATION_REQUIRED"
