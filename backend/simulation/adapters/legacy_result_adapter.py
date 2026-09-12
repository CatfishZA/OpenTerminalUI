from __future__ import annotations

from decimal import Decimal
from math import sqrt
from statistics import mean, pstdev
from typing import Any, Iterable

from backend.simulation.domain.enums import OrderSide
from backend.simulation.domain.market import MarketBar
from backend.simulation.domain.results import SimulationResult
from backend.simulation.persistence.serializers import to_primitive


class LegacyResultAdapter:
    """Build the legacy view from canonical fills, snapshots, and versioned bars."""

    def adapt(
        self,
        result: SimulationResult,
        *,
        symbol: str | None = None,
        asset: str | None = None,
        bars: Iterable[MarketBar] = (),
    ) -> dict[str, Any]:
        bars = tuple(sorted(bars, key=lambda item: (item.ts_close, item.instrument.key)))
        display_symbol = symbol or (bars[0].instrument.symbol if bars else "")
        initial_cash = Decimal(str(result.summary["initial_cash"]))
        cash, position = initial_cash, Decimal("0")
        opened_at = None
        trades: list[dict[str, Any]] = []
        for fill in result.fills:
            notional = fill.quantity * fill.price
            if fill.side is OrderSide.BUY:
                cash -= notional + fill.commission + fill.fees
                position += fill.quantity
                opened_at = opened_at or fill.executed_at
            else:
                cash += notional - fill.commission - fill.fees
                position -= fill.quantity
            hold_minutes = 0.0
            if fill.side is OrderSide.SELL and opened_at is not None:
                hold_minutes = (fill.executed_at - opened_at).total_seconds() / 60
                if position == 0:
                    opened_at = None
            trades.append({
                "date": fill.executed_at.isoformat(), "action": fill.side.value,
                "quantity": float(fill.quantity), "price": float(fill.price),
                "cash_after": float(cash), "position_after": float(position),
                "hold_time_minutes": hold_minutes,
            })

        bar_by_day = {bar.ts_close.date(): bar for bar in bars}
        position_by_day = {
            snapshot.snapshot_time.date(): snapshot.quantity
            for snapshot in result.position_snapshots
            if not display_symbol or snapshot.instrument.symbol == display_symbol
        }
        equity_curve = []
        for snapshot in result.portfolio_snapshots:
            bar = bar_by_day.get(snapshot.snapshot_time.date())
            if bar is None:
                continue
            equity_curve.append({
                "date": snapshot.snapshot_time.isoformat(),
                "open": float(bar.open), "high": float(bar.high), "low": float(bar.low),
                "equity": float(snapshot.equity),
                "cash": float(snapshot.cash_settled + snapshot.cash_unsettled),
                "position": float(position_by_day.get(snapshot.snapshot_time.date(), Decimal("0"))),
                "close": float(bar.close), "signal": 0,
            })
        equities = [point["equity"] for point in equity_curve]
        returns = [equities[index] / equities[index - 1] - 1 for index in range(1, len(equities)) if equities[index - 1]]
        peak = None
        drawdowns = []
        for value in equities:
            peak = value if peak is None else max(peak, value)
            drawdowns.append(value / peak - 1 if peak else 0.0)
        deviation = pstdev(returns) if len(returns) > 1 else 0.0
        sharpe = mean(returns) / deviation * sqrt(252) if deviation else 0.0
        summary = dict(result.summary)
        final_equity = Decimal(str(summary["final_equity"]))
        return {
            "symbol": display_symbol, "asset": asset or display_symbol, "bars": len(equity_curve),
            "initial_cash": float(initial_cash), "final_equity": float(final_equity),
            "pnl_amount": float(final_equity - initial_cash),
            "ending_cash": float(Decimal(str(summary["ending_cash"]))),
            "total_return": float(Decimal(str(summary["total_return"]))),
            "max_drawdown": min(drawdowns, default=0.0), "sharpe": sharpe,
            "daily_returns": returns, "drawdown_series": drawdowns,
            "trades": trades, "equity_curve": equity_curve,
            "orders": to_primitive(result.orders), "fills": to_primitive(result.fills),
            "manifest": to_primitive(result.manifest), "data_quality": to_primitive(result.data_quality),
            "verification_level": "VERIFIED", "simulation_run_id": result.run_id,
            "data_version_id": result.manifest.data_version_id,
            "engine_version": result.manifest.engine_version,
            "manifest_hash": result.manifest.manifest_hash, "result_hash": result.result_hash,
            "daily_bar_path_policy": result.manifest.daily_bar_path_policy,
            "sortino": 0.0, "calmar": 0.0, "omega": 0.0, "profit_factor": 0.0,
            "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
        }
