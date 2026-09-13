from __future__ import annotations

import asyncio
from decimal import Decimal

from backend.simulation.services.paper_simulation_service import PaperSimulationService
from backend.tests.simulation.paper_test_helpers import create_portfolio, submit, tick


def test_recovery_restores_positions_open_orders_and_reservations(db_session) -> None:  # noqa: ANN001
    portfolio = create_portfolio(db_session, cash="10000", settlement_days=0)
    submit(db_session, portfolio, quantity="10", cached_tick=tick("NSE:ABC", "10"))
    submit(db_session, portfolio, symbol="NSE:XYZ", order_type="limit", quantity="5", limit="50")
    recovered = asyncio.run(PaperSimulationService(db_session).current_account(portfolio))
    assert next(position.quantity for position in recovered.positions.values()) == Decimal("10")
    assert len(recovered.open_orders) == 1
    assert recovered.base_cash.reserved == Decimal("250.125")
    assert recovered.buying_power == Decimal("9649.825")
