from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal

from backend.models import (
    SimulationEventORM,
    SimulationFillORM,
    SimulationLedgerEntryORM,
    SimulationOrderORM,
    VirtualPosition,
    VirtualTrade,
)
from backend.paper_trading.service import PaperTradingEngine
from backend.simulation.domain.enums import OrderStatus
from backend.simulation.services.paper_simulation_service import PaperSimulationService
from backend.tests.simulation.paper_test_helpers import NOW, create_portfolio, submit, tick


def test_market_fill_is_canonical_and_full_exit_pnl_is_correct(db_session, monkeypatch) -> None:  # noqa: ANN001
    portfolio = create_portfolio(db_session, cash="10000", settlement_days=0)
    monkeypatch.setattr(PaperTradingEngine, "_fill_order", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy fill called")))
    buy = submit(db_session, portfolio, quantity="100", cached_tick=tick("NSE:ABC", "10"))
    sell = submit(db_session, portfolio, side="sell", quantity="100", cached_tick=tick("NSE:ABC", "12", at=NOW + timedelta(seconds=1)), submitted_at=NOW + timedelta(seconds=1))
    position = db_session.query(VirtualPosition).filter_by(portfolio_id=portfolio.id, symbol="NSE:ABC").one()
    trades = db_session.query(VirtualTrade).filter_by(portfolio_id=portfolio.id).order_by(VirtualTrade.timestamp).all()
    assert buy.status == "filled" and sell.status == "filled"
    assert position.quantity == 0
    assert position.avg_entry_price == 0
    assert trades[-1].pnl_realized == 200
    assert db_session.query(SimulationFillORM).filter_by(run_id=portfolio.simulation_run_id).count() == 2
    assert all(row.simulation_fill_id for row in trades)


def test_limit_stop_partial_fill_and_event_lifecycle(db_session) -> None:  # noqa: ANN001
    portfolio = create_portfolio(db_session, cash="10000", settlement_days=0)
    limit = submit(db_session, portfolio, order_type="limit", quantity="10", limit="100")
    service = PaperSimulationService(db_session)
    assert asyncio.run(service.consume_market_tick(tick("NSE:ABC", "101", at=NOW + timedelta(seconds=1)))) == 0
    assert asyncio.run(service.consume_market_tick(tick("NSE:ABC", "100", size="4", at=NOW + timedelta(seconds=2)))) == 1
    canonical = db_session.get(SimulationOrderORM, limit.simulation_order_id)
    assert canonical.status == OrderStatus.PARTIALLY_FILLED.value
    assert Decimal(canonical.remaining_quantity) == Decimal("6")
    assert asyncio.run(service.consume_market_tick(tick("NSE:ABC", "99", size="10", at=NOW + timedelta(seconds=3)))) == 1

    sell_limit = submit(db_session, portfolio, side="sell", order_type="limit", quantity="4", limit="101", submitted_at=NOW + timedelta(seconds=4))
    assert asyncio.run(service.consume_market_tick(tick("NSE:ABC", "100", at=NOW + timedelta(seconds=5)))) == 0
    assert asyncio.run(service.consume_market_tick(tick("NSE:ABC", "101", at=NOW + timedelta(seconds=6)))) == 1
    assert sell_limit.status == "filled"

    stop = submit(db_session, portfolio, side="sell", order_type="sl", quantity="6", stop="95", submitted_at=NOW + timedelta(seconds=7))
    assert asyncio.run(service.consume_market_tick(tick("NSE:ABC", "96", at=NOW + timedelta(seconds=8)))) == 0
    assert asyncio.run(service.consume_market_tick(tick("NSE:ABC", "95", at=NOW + timedelta(seconds=9)))) == 1
    event_types = [row.event_type for row in db_session.query(SimulationEventORM).filter_by(run_id=portfolio.simulation_run_id).order_by(SimulationEventORM.sequence)]
    assert "ORDER_PARTIAL_FILL" in event_types
    assert "ORDER_TRIGGERED" in event_types
    assert event_types.index("ORDER_TRIGGERED") < event_types.index("ORDER_FILL", event_types.index("ORDER_TRIGGERED"))
    assert stop.status == "filled"


def test_shared_cash_reservation_and_cancel_release(db_session) -> None:  # noqa: ANN001
    portfolio = create_portfolio(db_session, cash="100000")
    first = submit(db_session, portfolio, order_type="limit", quantity="700", limit="100")
    second = submit(db_session, portfolio, symbol="NSE:XYZ", order_type="limit", quantity="700", limit="100")
    assert first.status == "pending"
    assert second.status == "rejected"
    service = PaperSimulationService(db_session)
    asyncio.run(service.cancel_order(portfolio, first, at=NOW + timedelta(seconds=1)))
    account = asyncio.run(service.current_account(portfolio, at=NOW + timedelta(seconds=2)))
    assert account.base_cash.reserved == 0
    assert account.buying_power == Decimal("100000")
    assert db_session.query(SimulationFillORM).count() == 0
    assert db_session.query(SimulationLedgerEntryORM).filter(SimulationLedgerEntryORM.entry_type != "CASH_DEPOSIT").count() == 0


def test_oversell_and_cross_currency_are_rejected(db_session) -> None:  # noqa: ANN001
    portfolio = create_portfolio(db_session, cash="10000", currency="INR")
    oversell = submit(db_session, portfolio, side="sell", quantity="1")
    foreign = submit(db_session, portfolio, symbol="NASDAQ:AAPL", quantity="1", order_type="limit", limit="100")
    assert oversell.status == "rejected"
    assert foreign.status == "rejected"
    assert db_session.query(SimulationFillORM).count() == 0


def test_multiple_open_sells_cannot_commit_the_same_position_twice(db_session) -> None:  # noqa: ANN001
    portfolio = create_portfolio(db_session, cash="1000", settlement_days=0)
    submit(db_session, portfolio, quantity="10", cached_tick=tick("NSE:ABC", "10"))
    first = submit(db_session, portfolio, side="sell", order_type="limit", quantity="6", limit="20", submitted_at=NOW + timedelta(seconds=1))
    second = submit(db_session, portfolio, side="sell", order_type="limit", quantity="5", limit="20", submitted_at=NOW + timedelta(seconds=2))
    assert first.status == "pending"
    assert second.status == "rejected"


def test_fill_ledger_and_compatibility_projection_reconcile(db_session) -> None:  # noqa: ANN001
    portfolio = create_portfolio(db_session, cash="1000", settlement_days=0)
    submit(
        db_session,
        portfolio,
        quantity="10",
        cached_tick=tick("NSE:ABC", "10"),
        slippage="5",
        commission="2",
    )
    ledger = db_session.query(SimulationLedgerEntryORM).filter_by(run_id=portfolio.simulation_run_id).all()
    reconstructed = sum((Decimal(row.amount) for row in ledger), Decimal("0"))
    position = db_session.query(VirtualPosition).filter_by(portfolio_id=portfolio.id).one()
    fill = db_session.query(SimulationFillORM).filter_by(run_id=portfolio.simulation_run_id).one()
    assert reconstructed.quantize(Decimal("0.000001")) == Decimal(str(portfolio.current_cash)).quantize(Decimal("0.000001"))
    assert Decimal(str(position.quantity)) == Decimal(fill.quantity)
    assert Decimal(str(position.avg_entry_price)).quantize(Decimal("0.000001")) == Decimal(fill.price).quantize(Decimal("0.000001"))


def test_one_session_failure_does_not_block_another(db_session, monkeypatch) -> None:  # noqa: ANN001
    first = create_portfolio(db_session, cash="1000", settlement_days=0)
    second = create_portfolio(db_session, cash="1000", settlement_days=0)
    submit(db_session, first, order_type="limit", quantity="1", limit="10")
    submit(db_session, second, order_type="limit", quantity="1", limit="10")
    service = PaperSimulationService(db_session)
    original = service._apply_tick_to_order

    def flaky(portfolio, *args, **kwargs):  # noqa: ANN001
        if portfolio.id == first.id:
            raise RuntimeError("forced isolated failure")
        return original(portfolio, *args, **kwargs)

    monkeypatch.setattr(service, "_apply_tick_to_order", flaky)
    processed = asyncio.run(service.consume_market_tick(tick("NSE:ABC", "10", at=NOW + timedelta(seconds=1))))
    assert processed == 1
    assert db_session.query(SimulationFillORM).filter_by(run_id=first.simulation_run_id).count() == 0
    assert db_session.query(SimulationFillORM).filter_by(run_id=second.simulation_run_id).count() == 1
