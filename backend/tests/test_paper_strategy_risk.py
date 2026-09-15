from __future__ import annotations

import asyncio
from decimal import Decimal

from backend.models import PaperStrategyDeploymentORM, PaperStrategyIntentORM, SimulationOrderORM
from backend.paper_trading.deployment_policy import DeploymentRiskPolicy
from backend.paper_trading.strategy_deployment_service import StrategyDeploymentService
from backend.paper_trading.strategy_risk_service import StrategyRiskService
from backend.simulation.domain.account import AccountState
from backend.simulation.domain.cash import CashBalance
from backend.tests.paper_deployment_test_helpers import bar, governed_deployment


def test_order_notional_rejection_is_persisted_without_resizing(governance_db) -> None:  # noqa: ANN001
    actor, _baseline, result = governed_deployment(governance_db, risk_policy={"max_order_notional": "10"})
    service = StrategyDeploymentService(governance_db)
    asyncio.run(service.start(result["id"], user_id=actor.id))
    processed = asyncio.run(service.process_completed_bar(result["id"], bar()))
    intent = governance_db.query(PaperStrategyIntentORM).filter_by(deployment_id=result["id"]).one()
    assert processed["rejected_count"] == 1
    assert intent.risk_decision == "REJECTED" and intent.risk_reason == "RISK_ORDER_NOTIONAL_EXCEEDED"
    assert str(intent.quantity).rstrip("0").rstrip(".") == "2"
    assert governance_db.query(SimulationOrderORM).filter_by(run_id=result["simulation_run_id"]).count() == 0


def test_position_limit_and_open_order_controls_fail_closed(governance_db) -> None:  # noqa: ANN001
    actor, _baseline, result = governed_deployment(governance_db, risk_policy={"max_position_pct_of_equity": "0.001"})
    service = StrategyDeploymentService(governance_db)
    asyncio.run(service.start(result["id"], user_id=actor.id))
    asyncio.run(service.process_completed_bar(result["id"], bar()))
    intent = governance_db.query(PaperStrategyIntentORM).filter_by(deployment_id=result["id"]).one()
    assert intent.risk_reason == "RISK_POSITION_LIMIT_EXCEEDED" and intent.canonical_order_id is None


def test_daily_loss_anchor_survives_service_restart_and_breach_is_deterministic(governance_db) -> None:  # noqa: ANN001
    _actor, _baseline, result = governed_deployment(governance_db, risk_policy={"max_daily_loss_pct": "0.05"})
    deployment = governance_db.get(PaperStrategyDeploymentORM, result["id"])
    policy = DeploymentRiskPolicy.from_request(deployment.risk_policy_json)
    risk = StrategyRiskService(governance_db)
    account = AccountState("acct", "INR", cash={"INR": CashBalance("INR", settled=Decimal("10000"))}, equity=Decimal("10000"), buying_power=Decimal("10000"))
    assert risk.evaluate_daily_loss(deployment, account, risk_day="2026-09-12", policy=policy).accepted
    governance_db.commit()
    anchor = governance_db.get(PaperStrategyDeploymentORM, result["id"]).day_start_equity
    restarted = StrategyRiskService(governance_db)
    account.equity = Decimal("9400")
    decision = restarted.evaluate_daily_loss(deployment, account, risk_day="2026-09-12", policy=policy)
    assert Decimal(str(anchor)) == Decimal("10000")
    assert not decision.accepted and decision.reason == "RISK_DAILY_LOSS_EXCEEDED"


def test_daily_loss_breach_halts_deployment_before_decision(governance_db) -> None:  # noqa: ANN001
    actor, _baseline, result = governed_deployment(governance_db, risk_policy={"max_daily_loss_pct": "0.05"})
    service = StrategyDeploymentService(governance_db)
    asyncio.run(service.start(result["id"], user_id=actor.id))
    deployment = governance_db.get(PaperStrategyDeploymentORM, result["id"])
    deployment.risk_day = "2026-09-13"
    deployment.day_start_equity = Decimal("11000")
    governance_db.commit()
    outcome = asyncio.run(service.process_completed_bar(result["id"], bar()))
    assert outcome == {"status": "HALTED", "reason": "RISK_DAILY_LOSS_EXCEEDED"}
    assert governance_db.get(PaperStrategyDeploymentORM, result["id"]).status == "HALTED"
