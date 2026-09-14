from __future__ import annotations

import asyncio

import pytest

from backend.simulation.domain.reconciliation import BacktestPaperReconciliationSpec
from backend.simulation.services.backtest_paper_reconciliation_service import (
    BacktestPaperReconciliationError,
    BacktestPaperReconciliationService,
)
from backend.tests.simulation.reconciliation_test_helpers import canonical_pair, run
from backend.simulation.persistence.models import SimulationOrderORM


def test_verified_pair_persists_cutoff_and_is_idempotent_and_source_immutable(db_session) -> None:  # noqa: ANN001
    baseline, paper, cutoff = canonical_pair(db_session)
    before = {
        "baseline_manifest": dict(baseline.manifest_json), "baseline_result": baseline.result_hash,
        "paper_manifest": dict(paper.manifest_json), "paper_status": paper.status,
    }
    service = BacktestPaperReconciliationService(db_session)
    spec = BacktestPaperReconciliationSpec(baseline.id, paper.id)
    first = asyncio.run(service.create(spec))
    second = asyncio.run(service.create(spec))
    assert first["reconciliation_id"] == second["reconciliation_id"]
    assert first["paper_cutoff_sequence"] == cutoff
    assert first["report_hash"] == second["report_hash"]
    assert first["compatibility"]["performance_comparable"] is False
    db_session.refresh(baseline); db_session.refresh(paper)
    assert before == {
        "baseline_manifest": baseline.manifest_json, "baseline_result": baseline.result_hash,
        "paper_manifest": paper.manifest_json, "paper_status": paper.status,
    }


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("baseline_mode", "BASELINE_MODE_INVALID"),
        ("paper_mode", "PAPER_MODE_INVALID"),
        ("baseline_status", "BASELINE_NOT_DONE"),
        ("paper_status", "PAPER_MODE_INVALID"),
        ("currency", "CURRENCY_MISMATCH"),
    ],
)
def test_pair_validation_errors_are_stable(db_session, mutation: str, code: str) -> None:  # noqa: ANN001
    baseline, paper, _ = canonical_pair(db_session)
    if mutation == "baseline_mode": baseline.mode = "PAPER"
    elif mutation == "paper_mode": paper.mode = "BACKTEST"
    elif mutation == "baseline_status": baseline.status = "RUNNING"
    elif mutation == "paper_status": paper.status = "QUEUED"
    else: paper.request_json = {**paper.request_json, "base_currency": "USD"}
    db_session.commit()
    with pytest.raises(BacktestPaperReconciliationError) as exc:
        asyncio.run(BacktestPaperReconciliationService(db_session).create(BacktestPaperReconciliationSpec(baseline.id, paper.id)))
    assert exc.value.code == code


def test_research_baseline_requires_opt_in_and_warns_when_allowed(db_session) -> None:  # noqa: ANN001
    baseline, paper, _ = canonical_pair(db_session, baseline_verification="RESEARCH")
    service = BacktestPaperReconciliationService(db_session)
    with pytest.raises(BacktestPaperReconciliationError) as exc:
        asyncio.run(service.create(BacktestPaperReconciliationSpec(baseline.id, paper.id)))
    assert exc.value.code == "VERIFIED_BASELINE_REQUIRED"
    report = asyncio.run(service.create(BacktestPaperReconciliationSpec(baseline.id, paper.id, allow_research_baseline=True)))
    assert "RESEARCH_BASELINE" in report["compatibility"]["warnings"]
    assert baseline.verification_level == "RESEARCH"


def test_synthetic_baseline_cannot_be_opted_in(db_session) -> None:  # noqa: ANN001
    baseline, paper, _ = canonical_pair(db_session, baseline_verification="SYNTHETIC")
    with pytest.raises(BacktestPaperReconciliationError) as exc:
        asyncio.run(
            BacktestPaperReconciliationService(db_session).create(
                BacktestPaperReconciliationSpec(baseline.id, paper.id, allow_research_baseline=True)
            )
        )
    assert exc.value.code == "VERIFIED_BASELINE_REQUIRED"


def test_missing_cutoff_is_rejected(db_session) -> None:  # noqa: ANN001
    baseline, paper, _ = canonical_pair(db_session)
    service = BacktestPaperReconciliationService(db_session)
    with pytest.raises(BacktestPaperReconciliationError) as exc:
        asyncio.run(service.create(BacktestPaperReconciliationSpec(baseline.id, paper.id, paper_cutoff_sequence=999)))
    assert exc.value.code == "PAPER_CUTOFF_NOT_FOUND"


def test_no_instrument_overlap_is_rejected(db_session) -> None:  # noqa: ANN001
    baseline, paper, _ = canonical_pair(db_session)
    db_session.get(SimulationOrderORM, "ord_paper").instrument_key = "NSE:EQUITY:OTHER:INR"
    db_session.commit()
    with pytest.raises(BacktestPaperReconciliationError) as exc:
        asyncio.run(BacktestPaperReconciliationService(db_session).create(BacktestPaperReconciliationSpec(baseline.id, paper.id)))
    assert exc.value.code == "NO_INSTRUMENT_OVERLAP"


def test_wrong_source_ids_report_not_found(db_session) -> None:  # noqa: ANN001
    run(db_session, "sim_only", mode="BACKTEST")
    db_session.commit()
    with pytest.raises(BacktestPaperReconciliationError) as exc:
        asyncio.run(BacktestPaperReconciliationService(db_session).create(BacktestPaperReconciliationSpec("missing", "paper")))
    assert exc.value.code == "BASELINE_RUN_NOT_FOUND"
