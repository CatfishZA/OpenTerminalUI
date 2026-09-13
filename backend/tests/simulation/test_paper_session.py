from __future__ import annotations

from decimal import Decimal

from backend.models import SimulationLedgerEntryORM, SimulationPortfolioSnapshotORM, SimulationRunORM
from backend.simulation.domain.enums import LedgerEntryType, SimulationMode, SimulationRunStatus
from backend.tests.simulation.paper_test_helpers import create_portfolio


def test_new_portfolio_creates_exact_canonical_paper_session(db_session) -> None:  # noqa: ANN001
    portfolio = create_portfolio(db_session, cash="100000.25")
    run = db_session.get(SimulationRunORM, portfolio.simulation_run_id)
    assert run.mode == SimulationMode.PAPER.value
    assert run.status == SimulationRunStatus.RUNNING.value
    assert run.verification_level == "RESEARCH"
    assert run.engine_version == "sim-paper-v2a"
    assert run.data_version_id is None
    ledger = db_session.query(SimulationLedgerEntryORM).filter_by(run_id=run.id).one()
    snapshot = db_session.query(SimulationPortfolioSnapshotORM).filter_by(run_id=run.id).one()
    assert ledger.entry_type == LedgerEntryType.CASH_DEPOSIT.value
    assert Decimal(ledger.amount) == Decimal("100000.25")
    assert Decimal(snapshot.cash_settled) == Decimal("100000.25")
    assert Decimal(snapshot.equity) == Decimal("100000.25")
    assert portfolio.current_cash == 100000.25


def test_legacy_portfolio_remains_unlinked(db_session) -> None:  # noqa: ANN001
    from backend.models import VirtualPortfolio

    legacy = VirtualPortfolio(
        user_id="legacy-user", name="Legacy", initial_capital=1000, current_cash=1000, is_active=True
    )
    db_session.add(legacy)
    db_session.commit()
    assert legacy.simulation_run_id is None
    assert db_session.query(SimulationRunORM).count() == 0

