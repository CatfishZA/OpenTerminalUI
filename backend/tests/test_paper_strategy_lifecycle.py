from __future__ import annotations

import asyncio

import pytest

from backend.models import PaperStrategyDeploymentORM, SimulationOrderORM, VirtualPortfolio
from backend.paper_trading.deployment_domain import DeploymentError
from backend.paper_trading.strategy_deployment_service import StrategyDeploymentService
from backend.simulation.services.paper_simulation_service import PaperSimulationService
from backend.tests.paper_deployment_test_helpers import governed_deployment
from backend.tests.paper_deployment_test_helpers import bar


def test_lifecycle_and_terminal_resume(governance_db) -> None:  # noqa: ANN001
    actor, _baseline, result = governed_deployment(governance_db)
    service = StrategyDeploymentService(governance_db)
    assert asyncio.run(service.start(result["id"], user_id=actor.id))["status"] == "RUNNING"
    assert asyncio.run(service.pause(result["id"], user_id=actor.id))["status"] == "PAUSED"
    assert asyncio.run(service.resume(result["id"], user_id=actor.id))["status"] == "RUNNING"
    assert asyncio.run(service.stop(result["id"], user_id=actor.id, reason="done"))["status"] == "STOPPED"
    with pytest.raises(DeploymentError, match="DEPLOYMENT_TERMINAL"):
        asyncio.run(service.resume(result["id"], user_id=actor.id))


def test_halt_requires_reason_and_cancels_only_owned_orders(governance_db) -> None:  # noqa: ANN001
    actor, _baseline, result = governed_deployment(governance_db)
    service = StrategyDeploymentService(governance_db)
    asyncio.run(service.start(result["id"], user_id=actor.id))
    deployment = governance_db.get(PaperStrategyDeploymentORM, result["id"])
    portfolio = governance_db.get(VirtualPortfolio, deployment.portfolio_id)
    paper = PaperSimulationService(governance_db)
    owned = asyncio.run(paper.submit_order(
        portfolio=portfolio, symbol="NSE:ABC", side="buy", order_type="limit", quantity=1,
        limit_price=1, stop_price=None, slippage_bps=0, commission=0,
        strategy_order_id="owned", order_metadata={"deployment_id": deployment.id},
    ))
    manual = asyncio.run(paper.submit_order(
        portfolio=portfolio, symbol="NSE:ABC", side="buy", order_type="limit", quantity=1,
        limit_price=1, stop_price=None, slippage_bps=0, commission=0,
    ))
    with pytest.raises(DeploymentError, match="KILL_SWITCH_REASON_REQUIRED"):
        asyncio.run(service.halt(result["id"], user_id=actor.id, reason=""))
    assert asyncio.run(service.halt(result["id"], user_id=actor.id, reason="operator stop"))["status"] == "HALTED"
    assert governance_db.get(SimulationOrderORM, owned.simulation_order_id).status == "CANCELLED"
    assert governance_db.get(SimulationOrderORM, manual.simulation_order_id).status == "ACCEPTED"


def test_governance_drift_halts_before_another_decision(governance_db) -> None:  # noqa: ANN001
    actor, baseline, result = governed_deployment(governance_db)
    service = StrategyDeploymentService(governance_db)
    asyncio.run(service.start(result["id"], user_id=actor.id))
    baseline.result_hash = "changed-after-approval"
    governance_db.commit()
    outcome = asyncio.run(service.process_completed_bar(result["id"], bar()))
    assert outcome == {"status": "HALTED", "reason": "GOVERNANCE_EVIDENCE_STALE"}
    assert governance_db.get(PaperStrategyDeploymentORM, result["id"]).status == "HALTED"
