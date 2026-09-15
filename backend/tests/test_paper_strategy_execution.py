from __future__ import annotations

import asyncio
from datetime import timedelta

from backend.models import PaperStrategyDeploymentORM, PaperStrategyInputORM, PaperStrategyIntentORM, PriceEodORM, SimulationFillORM, SimulationOrderORM
from backend.paper_trading.deployment_domain import DeploymentError
from backend.paper_trading.strategy_market_read_model import DeploymentMarketReadModel
from backend.paper_trading.strategy_deployment_service import StrategyDeploymentService
from backend.simulation.domain.ticks import MarketTick
from backend.simulation.services.paper_simulation_service import PaperSimulationService
from backend.tests.paper_deployment_test_helpers import INSTRUMENT, bar, governed_deployment


def test_completed_bar_creates_canonical_order_then_later_tick_fills(governance_db) -> None:  # noqa: ANN001
    actor, _baseline, result = governed_deployment(governance_db)
    service = StrategyDeploymentService(governance_db)
    asyncio.run(service.start(result["id"], user_id=actor.id))
    observation = bar()
    processed = asyncio.run(service.process_completed_bar(result["id"], observation))
    assert processed["intent_count"] == 1 and processed["accepted_count"] == 1
    intent = governance_db.query(PaperStrategyIntentORM).one()
    order = governance_db.get(SimulationOrderORM, intent.canonical_order_id)
    assert order.status == "ACCEPTED" and order.strategy_order_id == intent.intent_id
    assert order.metadata_json["deployment_id"] == result["id"]
    assert governance_db.query(SimulationFillORM).count() == 1  # baseline fill only
    tick = MarketTick(INSTRUMENT, observation.end_time + timedelta(seconds=1), observation.close, source="fixture")
    asyncio.run(PaperSimulationService(governance_db).consume_market_tick(tick))
    assert governance_db.get(SimulationOrderORM, order.id).status == "FILLED"


def test_duplicate_input_does_not_repeat_decision_or_order(governance_db) -> None:  # noqa: ANN001
    actor, _baseline, result = governed_deployment(governance_db)
    service = StrategyDeploymentService(governance_db)
    asyncio.run(service.start(result["id"], user_id=actor.id))
    first = asyncio.run(service.process_completed_bar(result["id"], bar()))
    second = asyncio.run(service.process_completed_bar(result["id"], bar()))
    assert first["status"] == "PROCESSED" and second["status"] == "DUPLICATE"
    assert governance_db.query(PaperStrategyInputORM).filter_by(deployment_id=result["id"]).count() == 1
    assert governance_db.query(PaperStrategyIntentORM).filter_by(deployment_id=result["id"]).count() == 1
    deployment = governance_db.get(PaperStrategyDeploymentORM, result["id"])
    assert deployment.last_decision_sequence == 1 and deployment.strategy_state_json["last_signal"]


def test_incomplete_bar_does_not_evaluate(governance_db) -> None:  # noqa: ANN001
    actor, _baseline, result = governed_deployment(governance_db)
    service = StrategyDeploymentService(governance_db)
    asyncio.run(service.start(result["id"], user_id=actor.id))
    assert asyncio.run(service.process_completed_bar(result["id"], bar(complete=False)))["status"] == "IGNORED"
    assert governance_db.query(PaperStrategyInputORM).filter_by(deployment_id=result["id"]).count() == 0


def test_restart_restores_signal_state_and_new_input_does_not_duplicate_order(governance_db) -> None:  # noqa: ANN001
    actor, _baseline, result = governed_deployment(governance_db)
    asyncio.run(StrategyDeploymentService(governance_db).start(result["id"], user_id=actor.id))
    asyncio.run(StrategyDeploymentService(governance_db).process_completed_bar(result["id"], bar()))
    later = bar(source_event_id="bar-2", end=bar().end_time + timedelta(days=1))
    processed = asyncio.run(StrategyDeploymentService(governance_db).process_completed_bar(result["id"], later))
    assert processed["intent_count"] == 0
    assert governance_db.query(PaperStrategyIntentORM).filter_by(deployment_id=result["id"]).count() == 1
    assert governance_db.get(PaperStrategyDeploymentORM, result["id"]).last_decision_sequence == 2


def test_retry_recovers_durable_order_without_duplicate(governance_db) -> None:  # noqa: ANN001
    actor, _baseline, result = governed_deployment(governance_db)
    service = StrategyDeploymentService(governance_db)
    asyncio.run(service.start(result["id"], user_id=actor.id))
    asyncio.run(service.process_completed_bar(result["id"], bar()))
    deployment = governance_db.get(PaperStrategyDeploymentORM, result["id"])
    input_row = governance_db.query(PaperStrategyInputORM).filter_by(deployment_id=result["id"]).one()
    intent = governance_db.query(PaperStrategyIntentORM).filter_by(deployment_id=result["id"]).one()
    canonical_id = intent.canonical_order_id
    input_row.processed_status = "PROCESSING"
    intent.canonical_order_id = None
    deployment.strategy_state_json = {}
    deployment.last_decision_sequence = 0
    deployment.checkpoint_hash = None
    governance_db.commit()
    recovered = asyncio.run(StrategyDeploymentService(governance_db).recover(result["id"], user_id=actor.id))
    assert recovered["recovered_inputs"] == 1
    assert governance_db.query(SimulationOrderORM).filter_by(run_id=result["simulation_run_id"]).count() == 1
    assert governance_db.get(PaperStrategyIntentORM, intent.id).canonical_order_id == canonical_id
    assert governance_db.get(PaperStrategyDeploymentORM, result["id"]).checkpoint_hash


def test_concurrent_duplicate_input_is_serialized(governance_db) -> None:  # noqa: ANN001
    actor, _baseline, result = governed_deployment(governance_db)
    service = StrategyDeploymentService(governance_db)
    asyncio.run(service.start(result["id"], user_id=actor.id))

    async def run_both():
        return await asyncio.gather(
            service.process_completed_bar(result["id"], bar()),
            service.process_completed_bar(result["id"], bar()),
        )

    outcomes = asyncio.run(run_both())
    assert {item["status"] for item in outcomes} == {"PROCESSED", "DUPLICATE"}
    assert governance_db.query(PaperStrategyInputORM).filter_by(deployment_id=result["id"]).count() == 1


def test_insufficient_warmup_persists_blocked_input_without_order(governance_db) -> None:  # noqa: ANN001
    context = {"short_window": 1, "long_window": 5, "quantity": "2", "history_limit": 20}
    actor, _baseline, result = governed_deployment(governance_db, context=context, price_rows=(("2026-09-11", 9),))
    service = StrategyDeploymentService(governance_db)
    asyncio.run(service.start(result["id"], user_id=actor.id))
    outcome = asyncio.run(service.process_completed_bar(result["id"], bar()))
    input_row = governance_db.query(PaperStrategyInputORM).filter_by(deployment_id=result["id"]).one()
    assert outcome["status"] == "BLOCKED" and outcome["reason"] == "WARMUP_DATA_INSUFFICIENT"
    assert input_row.processed_status == "BLOCKED" and input_row.error_code == "WARMUP_DATA_INSUFFICIENT"
    assert governance_db.query(SimulationOrderORM).filter_by(run_id=result["simulation_run_id"]).count() == 0


def test_strategy_exception_fails_closed(governance_db, monkeypatch) -> None:  # noqa: ANN001
    actor, _baseline, result = governed_deployment(governance_db)
    service = StrategyDeploymentService(governance_db)
    asyncio.run(service.start(result["id"], user_id=actor.id))
    monkeypatch.setattr(service, "_evaluate", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("secret")))
    try:
        asyncio.run(service.process_completed_bar(result["id"], bar()))
        assert False, "expected fail-closed error"
    except DeploymentError as exc:
        assert exc.code == "STRATEGY_EVALUATION_FAILED"
    deployment = governance_db.get(PaperStrategyDeploymentORM, result["id"])
    assert deployment.status == "FAILED" and deployment.last_error == "STRATEGY_EVALUATION_FAILED: RuntimeError"


def test_market_read_model_never_exposes_future_persisted_bar(governance_db) -> None:  # noqa: ANN001
    _actor, _baseline, result = governed_deployment(governance_db)
    governance_db.add(PriceEodORM(
        symbol="ABC", trade_date="2026-09-20", open=100, high=101, low=99,
        close=100, volume=1000, data_version_id="version-a",
    ))
    governance_db.commit()
    observation = bar()
    market = DeploymentMarketReadModel(
        governance_db, deployment_id=result["id"], data_version_id="version-a",
        instruments=(INSTRUMENT,), decision_time=observation.end_time,
    )
    history = market.history(INSTRUMENT, limit=100)
    assert history and all(item.ts_close <= observation.end_time for item in history)
    assert all(item.ts_close.date().isoformat() != "2026-09-20" for item in history)
