from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.governance.service import StrategyGovernanceService
from backend.models import PriceEodORM
from backend.paper_trading.deployment_domain import CompletedBarObservation
from backend.paper_trading.strategy_deployment_service import StrategyDeploymentService
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.services.manifest_service import sha256_value
from backend.tests.governance_test_helpers import seed_actor, seed_baseline

INSTRUMENT = InstrumentId("ABC", "NSE", "EQUITY", "INR")


def governed_deployment(db, *, stage="STAGING", risk_policy=None, context=None, price_rows=None):  # noqa: ANN001
    actor = seed_actor(db)
    context = context or {"short_window": 1, "long_window": 2, "quantity": "2", "history_limit": 20}
    strategy = "example:sma_crossover"
    baseline = seed_baseline(db, strategy_hash=sha256_value({"key": strategy, "context": context}))
    baseline.strategy_key = strategy
    baseline.request_json = {
        "mode": "BACKTEST", "verification_level": "VERIFIED",
        "strategy": strategy, "strategy_context": context,
        "universe": [INSTRUMENT.key], "start": "2026-09-01", "end": "2026-09-11",
        "initial_cash": "10000", "base_currency": "INR", "data_version_id": "version-a",
        "execution_profile": {"model": "fixed_bps", "slippage_bps": "0", "max_participation": "1", "daily_bar_path_policy": "WORST_CASE"},
        "commission_profile": {"model": "bps", "bps": "0", "minimum": "0"},
        "settlement_profile": {"settlement_days": 1}, "seed": 42,
    }
    for day, close in (price_rows or (("2026-09-10", 10), ("2026-09-11", 9))):
        db.add(PriceEodORM(
            symbol="ABC", trade_date=day, open=close, high=close + 1, low=close - 1,
            close=close, volume=1000, data_version_id="version-a",
        ))
    db.flush()
    promoted = StrategyGovernanceService(db).promote(
        baseline_run_id=baseline.id, target_stage="STAGING", actor_user_id=actor.id, reason="paper validation",
    )
    if stage == "PROD":
        record = StrategyGovernanceService(db).repository.get(promoted["governance_record_id"])
        record.current_stage = "PROD"
        decision = StrategyGovernanceService(db).repository.history(record.id)[-1]
        decision.to_stage = "PROD"
        db.commit()
    result = StrategyDeploymentService(db).create(
        governance_record_id=promoted["governance_record_id"], user_id=actor.id,
        name="SMA paper validation", risk_policy=risk_policy,
    )
    return actor, baseline, result


def bar(*, source_event_id="bar-1", close="12", complete=True, end=None):  # noqa: ANN001
    end = end or datetime(2026, 9, 12, 21, 0, tzinfo=timezone.utc)
    return CompletedBarObservation(
        source_event_id=source_event_id, instrument=INSTRUMENT, interval="1d",
        start_time=end.replace(hour=14, minute=30), end_time=end,
        open=Decimal("10"), high=Decimal("13"), low=Decimal("9"),
        close=Decimal(close), volume=Decimal("1000"), source="fixture", complete=complete,
    )
