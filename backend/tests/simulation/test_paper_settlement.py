from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal

from backend.models import SimulationEventORM, SimulationLedgerEntryORM, SimulationSettlementObligationORM
from backend.simulation.services.paper_simulation_service import PaperSimulationService
from backend.tests.simulation.paper_test_helpers import NOW, create_portfolio, submit, tick


def test_t1_obligation_survives_service_restart_and_settles(db_session) -> None:  # noqa: ANN001
    portfolio = create_portfolio(db_session, cash="10000", settlement_days=1)
    submit(db_session, portfolio, quantity="10", cached_tick=tick("NSE:ABC", "10"))
    submit(db_session, portfolio, side="sell", quantity="10", cached_tick=tick("NSE:ABC", "12", at=NOW + timedelta(seconds=1)), submitted_at=NOW + timedelta(seconds=1))
    obligation = db_session.query(SimulationSettlementObligationORM).one()
    assert obligation.status == "PENDING"
    restarted = PaperSimulationService(db_session)
    before = asyncio.run(restarted.current_account(portfolio, at=NOW + timedelta(hours=1)))
    assert before.base_cash.unsettled_receivable == Decimal("120")
    after = asyncio.run(restarted.current_account(portfolio, at=NOW + timedelta(days=1, seconds=2)))
    db_session.refresh(obligation)
    assert obligation.status == "SETTLED"
    assert after.base_cash.unsettled_receivable == 0
    assert after.base_cash.settled == Decimal("10019.89")
    assert db_session.query(SimulationLedgerEntryORM).filter_by(entry_type="SETTLEMENT").count() == 1


def test_event_sequence_continues_monotonically_after_restart(db_session) -> None:  # noqa: ANN001
    portfolio = create_portfolio(db_session)
    first = submit(db_session, portfolio, order_type="limit", quantity="1", limit="10")
    before = [row.sequence for row in db_session.query(SimulationEventORM).filter_by(run_id=portfolio.simulation_run_id)]
    asyncio.run(PaperSimulationService(db_session).cancel_order(portfolio, first, at=NOW + timedelta(seconds=1)))
    after = [row.sequence for row in db_session.query(SimulationEventORM).filter_by(run_id=portfolio.simulation_run_id).order_by(SimulationEventORM.sequence)]
    assert after == sorted(set(after))
    assert max(after) > max(before)
