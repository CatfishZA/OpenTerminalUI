from __future__ import annotations

import pytest

from backend.governance.service import GovernanceError, StrategyGovernanceService
from backend.models import BacktestRun, ModelExperiment, ModelRegistryORM, ModelRun
from backend.tests.governance_test_helpers import seed_actor, seed_baseline


def _legacy_model_run(db, baseline_id: str | None):  # noqa: ANN001
    experiment = ModelExperiment(
        name="legacy", description="", tags=[], model_key="fixture:sma", params_json={},
        universe_json={}, benchmark_symbol=None, start_date="2024-01-01",
        end_date="2024-12-31", cost_model_json={},
    )
    db.add(experiment)
    db.flush()
    backtest = BacktestRun(
        run_id="bt-legacy", status="done", request_json="{}", result_json="{}",
        simulation_run_id=baseline_id,
    )
    db.add(backtest)
    db.flush()
    model_run = ModelRun(
        experiment_id=experiment.id, backtest_run_id=backtest.run_id, status="done",
        data_version_id="version-a", code_hash="client-spoof", execution_profile_json={"spoof": True},
    )
    db.add(model_run)
    db.flush()
    return model_run


def test_linked_legacy_model_run_resolves_canonical_evidence_and_projects_registry(governance_db) -> None:  # noqa: ANN001
    seed_actor(governance_db)
    baseline = seed_baseline(governance_db)
    model_run = _legacy_model_run(governance_db, baseline.id)
    service = StrategyGovernanceService(governance_db)
    resolved_model, resolved_run = service.resolve_legacy_model_run(model_run.id)
    assert resolved_model.id == model_run.id and resolved_run.id == baseline.id
    decision = service.promote(
        baseline_run_id=resolved_run.id, target_stage="STAGING", actor_user_id="actor-1",
        reason="canonical evidence reviewed", registry_name="legacy-name",
        legacy_model_run_id=resolved_model.id,
    )
    projection = governance_db.query(ModelRegistryORM).filter_by(
        governance_record_id=decision["governance_record_id"]
    ).one()
    assert projection.run_id == model_run.id
    assert projection.simulation_run_id == baseline.id
    assert projection.evidence_level == "CANONICAL"
    assert decision["evidence_hash"] != "client-spoof"


def test_unlinked_legacy_model_run_and_editable_metadata_cannot_bypass(governance_db) -> None:  # noqa: ANN001
    seed_baseline(governance_db)
    model_run = _legacy_model_run(governance_db, None)
    with pytest.raises(GovernanceError) as raised:
        StrategyGovernanceService(governance_db).resolve_legacy_model_run(model_run.id)
    assert raised.value.code == "CANONICAL_EVIDENCE_REQUIRED"


def test_existing_registry_rows_are_readable_as_legacy(governance_db) -> None:  # noqa: ANN001
    row = ModelRegistryORM(name="old", stage="prod", metadata_json={"legacy": True})
    governance_db.add(row)
    governance_db.commit()
    assert governance_db.get(ModelRegistryORM, row.id).evidence_level == "LEGACY"
