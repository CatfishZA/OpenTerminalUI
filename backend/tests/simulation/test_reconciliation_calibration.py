from __future__ import annotations

from decimal import Decimal

from backend.simulation.services.execution_calibration_service import ExecutionCalibrationService


def test_spread_liquidity_cost_and_settlement_drift_are_evidence_only() -> None:
    service = ExecutionCalibrationService()
    baseline_request = {
        "execution_profile": {"model": "fixed_bps", "slippage_bps": "1", "max_participation": "1"},
        "commission_profile": {"model": "bps", "bps": "1"},
        "settlement_profile": {"settlement_days": 1},
    }
    paper_request = {
        "execution_profile": {"model": "fixed_bps", "slippage_bps": "2", "max_participation": "0.5"},
        "commission_profile": {"model": "bps", "bps": "2"},
        "settlement_profile": {"settlement_days": 2},
    }
    result = service.build(
        baseline_request=baseline_request,
        paper_request=paper_request,
        baseline_aggregates=[],
        paper_aggregates=[{"simulated_slippage_bps": "2", "effective_commission_bps": "2", "partial_fill": True}],
        observations=[{"bid": Decimal("99"), "ask": Decimal("101"), "tick_size": Decimal("20"), "fill_quantity": Decimal("5")}],
        paper_orders=[{"status": "PARTIALLY_FILLED"}],
    )
    assert result["paper_evidence"]["spread_bps"]["mean"] == "200"
    assert result["paper_evidence"]["fill_participation"]["mean"] == "0.25"
    assert {item["code"] for item in result["drift"]} >= {
        "SLIPPAGE_PROFILE_DIFFERENT", "COMMISSION_PROFILE_DIFFERENT",
        "MAX_PARTICIPATION_DIFFERENT", "SETTLEMENT_DAYS_DIFFERENT",
        "SETTLEMENT_CALENDAR_NOT_EQUIVALENT",
    }
    assert result["automatic_tuning"] is False


def test_missing_observation_values_remain_null() -> None:
    result = ExecutionCalibrationService().build(
        baseline_request={}, paper_request={}, baseline_aggregates=[],
        paper_aggregates=[{"simulated_slippage_bps": "0", "effective_commission_bps": "0", "partial_fill": False}],
        observations=[{"bid": None, "ask": None, "tick_size": None, "fill_quantity": Decimal("1")}],
        paper_orders=[{"status": "FILLED"}],
    )
    assert result["paper_evidence"]["spread_bps"]["mean"] is None
    assert result["paper_evidence"]["fill_participation"]["mean"] is None
    assert "simulated" in result["paper_execution_description"]
