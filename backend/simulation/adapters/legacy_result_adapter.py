from __future__ import annotations

from typing import Any

from backend.simulation.domain.results import SimulationResult
from backend.simulation.persistence.serializers import to_primitive


class LegacyResultAdapter:
    """Maps completed canonical output only; it never fabricates missing metrics."""

    def adapt(self, result: SimulationResult) -> dict[str, Any]:
        summary = dict(result.summary)
        return {
            **summary,
            "run_id": result.run_id,
            "manifest": to_primitive(result.manifest),
            "orders": to_primitive(result.orders),
            "fills": to_primitive(result.fills),
            "equity_curve": to_primitive(result.equity_curve),
            "daily_returns": to_primitive(result.daily_returns),
            "drawdown_series": to_primitive(result.drawdown),
            "data_quality": to_primitive(result.data_quality),
        }
