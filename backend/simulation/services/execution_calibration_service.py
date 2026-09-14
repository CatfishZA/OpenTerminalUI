from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable


def _d(value: object | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _out(value: Decimal | None) -> str | None:
    if value is None:
        return None
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


class ExecutionCalibrationService:
    """Pure evidence calculations; never mutates execution configuration."""

    @staticmethod
    def aggregate_fills(order: dict[str, Any], fills: Iterable[dict[str, Any]]) -> dict[str, Any]:
        rows = list(fills)
        original = _d(order["quantity"]) or Decimal("0")
        filled = sum((_d(row["quantity"]) or Decimal("0") for row in rows), Decimal("0"))
        notional = sum(
            (
                (_d(row["quantity"]) or Decimal("0")) * (_d(row["price"]) or Decimal("0"))
                for row in rows
            ),
            Decimal("0"),
        )
        commission = sum((_d(row.get("commission")) or Decimal("0") for row in rows), Decimal("0"))
        fees = sum((_d(row.get("fees")) or Decimal("0") for row in rows), Decimal("0"))
        weighted_slippage = sum(
            (
                (_d(row.get("slippage_bps")) or Decimal("0")) * (_d(row["quantity"]) or Decimal("0"))
                for row in rows
            ),
            Decimal("0"),
        )
        times = sorted(row["executed_at"] for row in rows)
        submitted_at = order.get("submitted_at")
        accepted_at = order.get("accepted_at")
        completed_at = order.get("completed_at")

        def elapsed(end: object | None) -> str | None:
            if submitted_at is None or end is None:
                return None
            return _out(Decimal(str((end - submitted_at).total_seconds())))

        return {
            "fill_count": len(rows),
            "filled_quantity": _out(filled),
            "fill_ratio": _out(filled / original) if original else None,
            "vwap": _out(notional / filled) if filled else None,
            "total_notional": _out(notional),
            "total_commission": _out(commission),
            "total_fees": _out(fees),
            "effective_commission_bps": _out(commission / notional * Decimal("10000")) if notional else None,
            "effective_fee_bps": _out(fees / notional * Decimal("10000")) if notional else None,
            "simulated_slippage_bps": _out(weighted_slippage / filled) if filled else None,
            "first_fill_time": times[0].isoformat() if times else None,
            "last_fill_time": times[-1].isoformat() if times else None,
            "submitted_to_accepted_seconds": elapsed(accepted_at),
            "submitted_to_first_fill_seconds": elapsed(times[0] if times else None),
            "submitted_to_completion_seconds": elapsed(completed_at),
            "partial_fill": bool(rows and (len(rows) > 1 or filled < original)),
        }

    @staticmethod
    def statistics(values: Iterable[Decimal]) -> dict[str, Any]:
        ordered = sorted(values)
        if not ordered:
            return {key: None for key in ("count", "mean", "median", "p90", "p95", "min", "max")}

        def percentile(percent: int) -> Decimal:
            index = max(0, (len(ordered) * percent + 99) // 100 - 1)
            return ordered[index]

        middle = len(ordered) // 2
        median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
        return {
            "count": len(ordered),
            "mean": _out(sum(ordered, Decimal("0")) / len(ordered)),
            "median": _out(median),
            "p90": _out(percentile(90)),
            "p95": _out(percentile(95)),
            "min": _out(ordered[0]),
            "max": _out(ordered[-1]),
        }

    def build(
        self,
        *,
        baseline_request: dict[str, Any],
        paper_request: dict[str, Any],
        baseline_aggregates: list[dict[str, Any]],
        paper_aggregates: list[dict[str, Any]],
        observations: list[dict[str, Any]],
        paper_orders: list[dict[str, Any]],
    ) -> dict[str, Any]:
        baseline_execution = dict(baseline_request.get("execution_profile") or {})
        paper_execution = dict(paper_request.get("execution_profile") or {})
        baseline_commission = dict(baseline_request.get("commission_profile") or {})
        paper_commission = dict(paper_request.get("commission_profile") or {})
        baseline_settlement = dict(baseline_request.get("settlement_profile") or {})
        paper_settlement = dict(paper_request.get("settlement_profile") or {})
        drift: list[dict[str, str]] = []

        def add_if_different(code: str, left: object, right: object, severity: str = "WARNING") -> None:
            if left != right:
                drift.append({"code": code, "severity": severity})

        add_if_different("SLIPPAGE_PROFILE_DIFFERENT", baseline_execution.get("slippage_bps", baseline_execution.get("base_slippage_bps")), paper_execution.get("slippage_bps", paper_execution.get("base_slippage_bps")))
        add_if_different("MAX_PARTICIPATION_DIFFERENT", baseline_execution.get("max_participation"), paper_execution.get("max_participation"))
        add_if_different("COMMISSION_PROFILE_DIFFERENT", baseline_commission, paper_commission)
        add_if_different("SETTLEMENT_DAYS_DIFFERENT", baseline_settlement.get("settlement_days"), paper_settlement.get("settlement_days"))
        drift.append({"code": "DAILY_PATH_NOT_APPLICABLE_TO_PAPER", "severity": "INFO"})
        drift.append({"code": "SETTLEMENT_CALENDAR_NOT_EQUIVALENT", "severity": "WARNING"})

        spreads: list[Decimal] = []
        participation: list[Decimal] = []
        for observation in observations:
            bid, ask = _d(observation.get("bid")), _d(observation.get("ask"))
            if bid is not None and ask is not None and bid + ask > 0:
                spreads.append((ask - bid) / ((ask + bid) / 2) * Decimal("10000"))
            size, fill_quantity = _d(observation.get("tick_size")), _d(observation.get("fill_quantity"))
            if size is not None and size > 0 and fill_quantity is not None:
                participation.append(fill_quantity / size)
        if observations and len(spreads) < len(observations):
            drift.append({"code": "PAPER_SPREAD_DATA_PARTIAL", "severity": "INFO"})
        if observations and len(participation) < len(observations):
            drift.append({"code": "PAPER_LIQUIDITY_DATA_PARTIAL", "severity": "INFO"})
        if paper_aggregates and not observations:
            drift.append({"code": "PAPER_EXECUTION_OBSERVATION_MISSING", "severity": "INFO"})

        def metric(name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
            return self.statistics(_d(row.get(name)) for row in rows if _d(row.get(name)) is not None)

        terminal = len(paper_orders) or 1
        return {
            "paper_execution_description": "simulated execution against observed live tick inputs",
            "configured": {
                "baseline_execution": baseline_execution,
                "paper_execution": paper_execution,
                "baseline_commission": baseline_commission,
                "paper_commission": paper_commission,
                "baseline_settlement": baseline_settlement,
                "paper_settlement": paper_settlement,
            },
            "paper_evidence": {
                "spread_bps": self.statistics(spreads),
                "fill_participation": self.statistics(participation),
                "simulated_slippage_bps": metric("simulated_slippage_bps", paper_aggregates),
                "effective_commission_bps": metric("effective_commission_bps", paper_aggregates),
                "time_to_first_fill_seconds": metric("submitted_to_first_fill_seconds", paper_aggregates),
                "partial_fill_rate": _out(Decimal(sum(bool(row.get("partial_fill")) for row in paper_aggregates)) / terminal),
                "cancellation_rate": _out(Decimal(sum(row.get("status") == "CANCELLED" for row in paper_orders)) / terminal),
                "rejection_rate": _out(Decimal(sum(row.get("status") == "REJECTED" for row in paper_orders)) / terminal),
            },
            "drift": drift,
            "automatic_tuning": False,
        }
