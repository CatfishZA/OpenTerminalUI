from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from backend.simulation.adapters.live_tick_adapter import instrument_from_legacy_symbol
from backend.simulation.domain.ticks import MarketTick
from backend.simulation.services.paper_simulation_service import PaperSimulationService


NOW = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)


def create_portfolio(db, *, cash="100000", currency="INR", settlement_days=1):  # noqa: ANN001
    return PaperSimulationService(db).create_portfolio(
        user_id="paper-test-user",
        name="Canonical Paper",
        initial_cash=Decimal(cash),
        base_currency=currency,
        settlement_profile={"settlement_days": settlement_days},
    )


def tick(symbol: str, price: str, *, size: str | None = None, at=NOW) -> MarketTick:  # noqa: ANN001
    return MarketTick(
        instrument=instrument_from_legacy_symbol(symbol),
        ts=at,
        price=Decimal(price),
        size=Decimal(size) if size is not None else None,
        source="test",
    )


def submit(db, portfolio, *, symbol="NSE:ABC", side="buy", order_type="market", quantity="1", limit=None, stop=None, slippage="0", commission="0", cached_tick=None, submitted_at=NOW):  # noqa: ANN001
    return asyncio.run(
        PaperSimulationService(db).submit_order(
            portfolio=portfolio,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=Decimal(quantity),
            limit_price=Decimal(limit) if limit is not None else None,
            stop_price=Decimal(stop) if stop is not None else None,
            slippage_bps=Decimal(slippage),
            commission=Decimal(commission),
            cached_tick=cached_tick,
            submitted_at=submitted_at,
        )
    )

