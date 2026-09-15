from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from backend.models import PaperStrategyDeploymentORM, SimulationOrderORM
from backend.paper_trading.deployment_domain import RiskDecision
from backend.paper_trading.deployment_policy import DeploymentRiskPolicy
from backend.simulation.domain.account import AccountState
from backend.simulation.domain.enums import OrderSide, OrderStatus
from backend.simulation.domain.strategy import StrategyIntent


class StrategyRiskService:
    """Deterministic PAPER safety checks over canonical account state."""

    def __init__(self, db: Session):
        self.db = db

    def evaluate_daily_loss(
        self,
        deployment: PaperStrategyDeploymentORM,
        account: AccountState,
        *,
        risk_day: str,
        policy: DeploymentRiskPolicy,
    ) -> RiskDecision:
        if deployment.risk_day != risk_day or deployment.day_start_equity is None:
            deployment.risk_day = risk_day
            deployment.day_start_equity = account.equity
        anchor = Decimal(str(deployment.day_start_equity))
        if anchor <= 0:
            return RiskDecision(False, "RISK_DAILY_LOSS_EXCEEDED")
        loss = max(Decimal("0"), (anchor - account.equity) / anchor)
        return RiskDecision(loss < policy.max_daily_loss_pct, None if loss < policy.max_daily_loss_pct else "RISK_DAILY_LOSS_EXCEEDED")

    def evaluate_intent(
        self,
        deployment: PaperStrategyDeploymentORM,
        account: AccountState,
        intent: StrategyIntent,
        *,
        price: Decimal | None,
        policy: DeploymentRiskPolicy,
    ) -> RiskDecision:
        if intent.instrument.key not in set(deployment.symbols_json or []):
            return RiskDecision(False, "RISK_SYMBOL_NOT_ALLOWED")
        if price is None or price <= 0:
            return RiskDecision(False, "RISK_PRICE_UNAVAILABLE")
        notional = intent.quantity * price
        if notional > policy.max_order_notional:
            return RiskDecision(False, "RISK_ORDER_NOTIONAL_EXCEEDED")
        open_owned = 0
        rows = self.db.query(SimulationOrderORM).filter(
            SimulationOrderORM.run_id == deployment.simulation_run_id,
            SimulationOrderORM.status.in_([OrderStatus.ACCEPTED.value, OrderStatus.PARTIALLY_FILLED.value]),
        ).all()
        for row in rows:
            if dict(row.metadata_json or {}).get("deployment_id") == deployment.id:
                open_owned += 1
        if open_owned >= policy.max_open_strategy_orders:
            return RiskDecision(False, "RISK_OPEN_ORDER_LIMIT_EXCEEDED")
        position = account.positions.get(intent.instrument)
        held = position.quantity if position else Decimal("0")
        if intent.side is OrderSide.SELL:
            if held < intent.quantity:
                return RiskDecision(False, "RISK_SHORT_POSITION")
            return RiskDecision(True)
        projected = (held + intent.quantity) * price
        if account.equity <= 0 or projected / account.equity > policy.max_position_pct_of_equity:
            return RiskDecision(False, "RISK_POSITION_LIMIT_EXCEEDED")
        return RiskDecision(True)
