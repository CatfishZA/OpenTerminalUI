from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal

from backend.simulation.domain.reconciliation import AlignmentPolicy, BacktestPaperReconciliationSpec
from backend.simulation.persistence.models import SimulationOrderORM
from backend.simulation.services.backtest_paper_reconciliation_service import BacktestPaperReconciliationService
from backend.simulation.services.execution_calibration_service import ExecutionCalibrationService
from backend.tests.simulation.reconciliation_test_helpers import NOW, canonical_pair, fill, order, paper_events


def _report(db_session, *, key="intent-1"):  # noqa: ANN001
    baseline, paper, _ = canonical_pair(db_session, key=key)
    return asyncio.run(BacktestPaperReconciliationService(db_session).create(BacktestPaperReconciliationSpec(baseline.id, paper.id)))


def test_reconciliation_key_is_exact(db_session) -> None:  # noqa: ANN001
    item = _report(db_session)["items"][0]
    assert (item["match_status"], item["match_basis"], item["match_confidence"]) == ("MATCHED", "RECONCILIATION_KEY", "EXACT")
    assert item["metrics"]["fill_ratio_delta"] == "0"
    assert item["metrics"]["direct_price_delta_valid"] is False


def test_strategy_id_and_signature_fallback_confidence(db_session) -> None:  # noqa: ANN001
    baseline, paper, _ = canonical_pair(db_session, key=None)
    db_session.get(SimulationOrderORM, "ord_baseline").strategy_order_id = "strategy-order-1"
    db_session.get(SimulationOrderORM, "ord_paper").strategy_order_id = "strategy-order-1"
    db_session.commit()
    report = asyncio.run(BacktestPaperReconciliationService(db_session).create(BacktestPaperReconciliationSpec(baseline.id, paper.id)))
    assert report["items"][0]["match_basis"] == "STRATEGY_ORDER_ID"
    assert report["items"][0]["match_confidence"] == "HIGH"


def test_unique_signature_is_medium_and_ordinal_is_optional_low(db_session) -> None:  # noqa: ANN001
    report = _report(db_session, key=None)
    assert report["items"][0]["match_basis"] == "UNIQUE_SIGNATURE"
    assert report["items"][0]["match_confidence"] == "MEDIUM"


def test_keys_only_does_not_apply_signature_fallback(db_session) -> None:  # noqa: ANN001
    baseline, paper, _ = canonical_pair(db_session, key=None)
    report = asyncio.run(
        BacktestPaperReconciliationService(db_session).create(
            BacktestPaperReconciliationSpec(baseline.id, paper.id, alignment_policy=AlignmentPolicy.KEYS_ONLY)
        )
    )
    assert {item["match_status"] for item in report["items"]} == {"BASELINE_ONLY", "PAPER_ONLY"}


def test_duplicate_explicit_keys_are_ambiguous_not_guessed(db_session) -> None:  # noqa: ANN001
    baseline, paper, cutoff = canonical_pair(db_session)
    order(db_session, baseline.id, "ord_baseline_2", key="intent-1", submitted_at=NOW + timedelta(seconds=10))
    order(db_session, paper.id, "ord_paper_2", key="intent-1", submitted_at=NOW + timedelta(seconds=10))
    cutoff = paper_events(db_session, paper.id, "ord_paper_2", [], start_sequence=cutoff + 1)
    db_session.commit()
    report = asyncio.run(BacktestPaperReconciliationService(db_session).create(BacktestPaperReconciliationSpec(baseline.id, paper.id, paper_cutoff_sequence=cutoff)))
    ambiguous = [item for item in report["items"] if item["match_status"] == "AMBIGUOUS"]
    assert len(ambiguous) == 2
    assert all(item["paper_order_id"] is None and item["match_confidence"] == "NONE" for item in ambiguous)


def test_unmatched_orders_are_reported(db_session) -> None:  # noqa: ANN001
    baseline, paper, cutoff = canonical_pair(db_session)
    order(db_session, baseline.id, "ord_baseline_only", instrument="NSE:EQUITY:ONLYB:INR", submitted_at=NOW + timedelta(seconds=10))
    order(db_session, paper.id, "ord_paper_only", instrument="NSE:EQUITY:ONLYP:INR", submitted_at=NOW + timedelta(seconds=10))
    cutoff = paper_events(db_session, paper.id, "ord_paper_only", [], start_sequence=cutoff + 1)
    db_session.commit()
    report = asyncio.run(BacktestPaperReconciliationService(db_session).create(BacktestPaperReconciliationSpec(baseline.id, paper.id, paper_cutoff_sequence=cutoff)))
    assert {item["match_status"] for item in report["items"]} >= {"MATCHED", "BASELINE_ONLY", "PAPER_ONLY"}


def test_partial_fill_aggregation_uses_exact_decimal_math() -> None:
    engine = ExecutionCalibrationService()
    aggregate = engine.aggregate_fills(
        {"quantity": Decimal("0.3")},
        [
            {"quantity": Decimal("0.1"), "price": Decimal("0.1"), "commission": Decimal("0.001"), "fees": Decimal("0"), "slippage_bps": Decimal("1"), "executed_at": NOW},
            {"quantity": Decimal("0.2"), "price": Decimal("0.2"), "commission": Decimal("0.002"), "fees": Decimal("0"), "slippage_bps": Decimal("2"), "executed_at": NOW + timedelta(seconds=1)},
        ],
    )
    assert aggregate["filled_quantity"] == "0.3"
    assert aggregate["fill_ratio"] == "1"
    assert aggregate["vwap"] == str((Decimal("0.05") / Decimal("0.3")).normalize())
    assert aggregate["total_commission"] == "0.003"
    assert aggregate["fill_count"] == 2
    assert aggregate["partial_fill"] is True
