from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from backend.paper_trading.deployment_domain import DeploymentError


@dataclass(frozen=True, slots=True)
class DeploymentRiskPolicy:
    max_order_notional: Decimal
    max_position_pct_of_equity: Decimal
    max_open_strategy_orders: int
    max_daily_loss_pct: Decimal

    @classmethod
    def from_request(cls, raw: dict[str, Any] | None) -> "DeploymentRiskPolicy":
        values = dict(raw or {})
        try:
            policy = cls(
                Decimal(str(values.get("max_order_notional", "10000"))),
                Decimal(str(values.get("max_position_pct_of_equity", "0.25"))),
                int(values.get("max_open_strategy_orders", 5)),
                Decimal(str(values.get("max_daily_loss_pct", "0.05"))),
            )
        except Exception as exc:
            raise DeploymentError("RISK_POLICY_INVALID") from exc
        if (
            policy.max_order_notional <= 0
            or not Decimal("0") < policy.max_position_pct_of_equity <= Decimal("1")
            or policy.max_open_strategy_orders < 1
            or not Decimal("0") < policy.max_daily_loss_pct <= Decimal("1")
        ):
            raise DeploymentError("RISK_POLICY_INVALID")
        return policy

    def snapshot(self) -> dict[str, Any]:
        return {
            "max_order_notional": str(self.max_order_notional),
            "max_position_pct_of_equity": str(self.max_position_pct_of_equity),
            "max_open_strategy_orders": self.max_open_strategy_orders,
            "max_daily_loss_pct": str(self.max_daily_loss_pct),
        }
