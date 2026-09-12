from backend.simulation.adapters.legacy_result_adapter import LegacyResultAdapter
from backend.tests.simulation.engine_fixtures import bar, simulate


def test_legacy_adapter_exposes_required_contract_and_provenance() -> None:
    bars = [bar(1), bar(2)]
    result = simulate(bars, [])
    adapted = LegacyResultAdapter().adapt(result, symbol="AAPL", asset="AAPL", bars=bars)
    required = {
        "symbol", "asset", "bars", "initial_cash", "final_equity", "pnl_amount",
        "ending_cash", "total_return", "daily_returns", "drawdown_series", "trades",
        "equity_curve", "orders", "fills", "manifest", "data_quality",
        "verification_level", "simulation_run_id", "data_version_id", "engine_version",
        "manifest_hash", "result_hash", "daily_bar_path_policy",
    }
    assert required <= adapted.keys()
    assert all({"date", "open", "high", "low", "equity", "cash", "position", "close", "signal"} <= point.keys() for point in adapted["equity_curve"])
