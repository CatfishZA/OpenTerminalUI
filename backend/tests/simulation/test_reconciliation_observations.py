from __future__ import annotations

import asyncio
from decimal import Decimal

from backend.simulation.adapters.live_tick_adapter import instrument_from_legacy_symbol
from backend.simulation.domain.ticks import MarketTick
from backend.simulation.persistence.models import SimulationExecutionObservationORM, SimulationFillORM
from backend.simulation.services.paper_simulation_service import PaperSimulationService
from backend.tests.simulation.paper_test_helpers import NOW, create_portfolio


def test_fill_causing_tick_creates_one_observation_without_execution_side_effects(db_session) -> None:  # noqa: ANN001
    portfolio = create_portfolio(db_session, cash="1000", settlement_days=0)
    tick = MarketTick(
        instrument=instrument_from_legacy_symbol("NSE:ABC"),
        ts=NOW,
        price=Decimal("10"),
        size=Decimal("100"),
        bid=Decimal("9.9"),
        ask=Decimal("10.1"),
        source="controlled-test",
    )
    order = asyncio.run(
        PaperSimulationService(db_session).submit_order(
            portfolio=portfolio,
            symbol="NSE:ABC",
            side="buy",
            order_type="market",
            quantity=Decimal("10"),
            limit_price=None,
            stop_price=None,
            slippage_bps=Decimal("0"),
            commission=Decimal("1"),
            cached_tick=tick,
            submitted_at=NOW,
            reconciliation_key="controlled-intent",
            strategy_order_id="strategy-order-controlled",
        )
    )
    fill = db_session.query(SimulationFillORM).one()
    observation = db_session.query(SimulationExecutionObservationORM).one()
    assert order.status == "filled"
    assert Decimal(fill.quantity) == Decimal("10")
    assert Decimal(fill.price) == Decimal("10")
    assert Decimal(fill.commission) == Decimal("1")
    assert observation.fill_id == fill.id
    assert Decimal(observation.tick_price) == Decimal("10")
    assert Decimal(observation.bid).quantize(Decimal("0.1")) == Decimal("9.9")
    assert Decimal(observation.ask).quantize(Decimal("0.1")) == Decimal("10.1")
    assert Decimal(observation.tick_size) == Decimal("100")
    assert observation.tick_source == "controlled-test"
    assert observation.metadata_json["paper_execution"] == "simulated"


def test_non_fill_tick_creates_no_observation(db_session) -> None:  # noqa: ANN001
    portfolio = create_portfolio(db_session)
    asyncio.run(
        PaperSimulationService(db_session).submit_order(
            portfolio=portfolio,
            symbol="NSE:ABC",
            side="buy",
            order_type="limit",
            quantity=Decimal("1"),
            limit_price=Decimal("5"),
            stop_price=None,
            slippage_bps=Decimal("0"),
            commission=Decimal("0"),
            cached_tick=None,
            submitted_at=NOW,
        )
    )
    assert db_session.query(SimulationExecutionObservationORM).count() == 0
