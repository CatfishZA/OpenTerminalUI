from __future__ import annotations

from dataclasses import replace

import pytest

from backend.services.backtest_jobs import BacktestJobRequest
from backend.simulation.adapters.backtest_request_adapter import (
    BacktestRequestAdapter,
    should_use_simulation_engine,
)


def verified_request(**changes) -> BacktestJobRequest:  # noqa: ANN003
    request = BacktestJobRequest(
        symbol="AAPL", market="NASDAQ", start="2024-01-01", end="2024-01-04",
        strategy="example:sma_crossover", context={"short_window": 1, "long_window": 2, "quantity": 10},
        config={"initial_cash": 100000, "fee_bps": 1, "slippage_bps": 2, "allow_short": False},
        verification_level="VERIFIED", data_version_id="version-1", currency="USD",
    )
    return replace(request, **changes)


def test_default_request_remains_legacy() -> None:
    assert not should_use_simulation_engine(BacktestJobRequest(symbol="AAPL"))


def test_verified_request_maps_fees_slippage_and_identity() -> None:
    spec = BacktestRequestAdapter().to_spec(verified_request())
    assert spec.universe[0].key == "NASDAQ:EQUITY:AAPL:USD"
    assert spec.execution_profile["slippage_bps"] == "2"
    assert spec.commission_profile["bps"] == "1"
    assert spec.strategy_context["quantity"] == "10"


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"data_version_id": None}, "DATA_VERSION_REQUIRED"),
        ({"timeframe": "5m"}, "UNSUPPORTED_VERIFIED_TIMEFRAME"),
        ({"market": "UNKNOWN"}, "UNSUPPORTED_VERIFIED_VENUE"),
        ({"config": {"position_fraction": 0.5}}, "UNSUPPORTED_VERIFIED_CONFIG"),
        ({"config": {"allow_short": True}}, "UNSUPPORTED_VERIFIED_CONFIG"),
    ],
)
def test_unsupported_verified_requests_fail(changes, code) -> None:  # noqa: ANN001
    with pytest.raises(ValueError, match=code):
        BacktestRequestAdapter().to_spec(verified_request(**changes))
