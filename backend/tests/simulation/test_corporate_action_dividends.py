from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.models import CorpActionORM, DataVersionORM
from backend.simulation.adapters.corporate_actions_adapter import CorporateActionsAdapter
from backend.simulation.domain.account import AccountState
from backend.simulation.domain.cash import CashBalance
from backend.simulation.domain.corporate_actions import CorporateAction
from backend.simulation.domain.enums import CorporateActionType, LedgerEntryType, VerificationLevel
from backend.simulation.domain.positions import Position
from backend.simulation.engine.corporate_action_engine import CorporateActionEngine
from backend.tests.simulation.fixtures import instrument


def test_dividend_captures_entitlement_then_pays_once_after_sale() -> None:
    inst = instrument()
    account = AccountState(
        "acct", "USD", cash={"USD": CashBalance("USD", settled=Decimal("1000"))},
        positions={inst: Position(inst, Decimal("100"), Decimal("20"))},
        equity=Decimal("3000"), buying_power=Decimal("1000"),
    )
    action = CorporateAction(
        "div-1", inst, CorporateActionType.CASH_DIVIDEND, date(2024, 1, 3), None,
        date(2024, 1, 5), None, Decimal("5"), "USD", "v1",
    )
    engine = CorporateActionEngine()
    entitlements = []
    applied = set()
    established = engine.apply_session_actions(account, [action], date(2024, 1, 3), run_id="sim_x", at=datetime(2024, 1, 3, tzinfo=timezone.utc), open_orders=account.open_orders, applied_action_ids=applied, entitlements=entitlements)
    assert established.entitlements_created[0].eligible_quantity == 100
    assert established.entitlements_created[0].total_amount == 500
    account.positions[inst] = Position(inst, Decimal("0"), Decimal("0"))
    paid = engine.apply_session_actions(account, [action], date(2024, 1, 5), run_id="sim_x", at=datetime(2024, 1, 5, tzinfo=timezone.utc), open_orders=account.open_orders, applied_action_ids=applied, entitlements=entitlements)
    assert account.base_cash.settled == 1500
    assert account.realized_pnl == 0
    assert paid.ledger_entries[0].entry_type is LedgerEntryType.DIVIDEND
    assert paid.ledger_entries[0].amount == 500
    again = engine.apply_session_actions(account, [action], date(2024, 1, 6), run_id="sim_x", at=datetime(2024, 1, 6, tzinfo=timezone.utc), open_orders=account.open_orders, applied_action_ids=applied, entitlements=entitlements)
    assert not again.ledger_entries and account.base_cash.settled == 1500


def test_corporate_action_adapter_enforces_verified_dates_versions_and_types(db_session) -> None:  # noqa: ANN001
    db_session.add(DataVersionORM(id="v1", name="v1", source="internal", is_active=True, metadata_json={}))
    db_session.add_all([
        CorpActionORM(
            id="incomplete", symbol="AAPL", action_date="2024-01-03", action_type="DIVIDEND",
            amount=Decimal("1"), currency="USD", data_version_id="v1",
        ),
        CorpActionORM(
            id="unversioned", symbol="AAPL", action_date="2024-01-04", ex_date="2024-01-04",
            pay_date="2024-01-05", action_type="DIVIDEND", amount=Decimal("1"), currency="USD",
            data_version_id=None,
        ),
        CorpActionORM(
            id="unsupported", symbol="AAPL", action_date="2024-01-05", action_type="MERGER",
            factor=Decimal("1"), data_version_id="v1",
        ),
    ])
    db_session.commit()
    adapter = CorporateActionsAdapter(db_session)
    with pytest.raises(ValueError, match="CORPORATE_ACTION_DATE_INCOMPLETE"):
        list(adapter.events([instrument()], date(2024, 1, 1), date(2024, 1, 6), "v1", verification_level=VerificationLevel.VERIFIED))
    db_session.delete(db_session.get(CorpActionORM, "incomplete"))
    db_session.commit()
    with pytest.raises(ValueError, match="CORPORATE_ACTION_VERSION_MISMATCH"):
        list(adapter.events([instrument()], date(2024, 1, 1), date(2024, 1, 6), "v1", verification_level=VerificationLevel.VERIFIED))
    db_session.delete(db_session.get(CorpActionORM, "unversioned"))
    db_session.commit()
    with pytest.raises(ValueError, match="CORPORATE_ACTION_UNSUPPORTED"):
        list(adapter.events([instrument()], date(2024, 1, 1), date(2024, 1, 6), "v1", verification_level=VerificationLevel.VERIFIED))


def test_research_legacy_dividend_dates_are_explicitly_warned(db_session) -> None:  # noqa: ANN001
    db_session.add(CorpActionORM(
        id="legacy", symbol="AAPL", action_date="2024-01-03", action_type="DIVIDEND",
        amount=Decimal("2"), factor=Decimal("1"), data_version_id=None,
    ))
    db_session.commit()
    action = next(iter(CorporateActionsAdapter(db_session).events(
        [instrument()], date(2024, 1, 1), date(2024, 1, 6), "v1",
        verification_level=VerificationLevel.RESEARCH,
    )))
    assert action.ex_date == action.pay_date == date(2024, 1, 3)
    assert action.data_version_id is None
    assert action.warnings == (
        "LEGACY_DIVIDEND_DATE_ASSUMPTION",
        "LEGACY_UNVERSIONED_CORPORATE_ACTION",
    )


def test_post_entitlement_buyer_receives_no_prior_dividend() -> None:
    inst = instrument()
    account = AccountState(
        "acct", "USD", cash={"USD": CashBalance("USD", settled=Decimal("1000"))},
        equity=Decimal("1000"), buying_power=Decimal("1000"),
    )
    action = CorporateAction(
        "div-zero", inst, CorporateActionType.CASH_DIVIDEND, date(2024, 1, 3), None,
        date(2024, 1, 5), None, Decimal("5"), "USD", "v1",
    )
    entitlements = []
    applied: set[str] = set()
    engine = CorporateActionEngine()
    engine.apply_session_actions(
        account, [action], date(2024, 1, 3), run_id="sim_x",
        at=datetime(2024, 1, 3, tzinfo=timezone.utc),
        open_orders=account.open_orders, applied_action_ids=applied, entitlements=entitlements,
    )
    account.positions[inst] = Position(inst, Decimal("100"), Decimal("20"))
    paid = engine.apply_session_actions(
        account, [action], date(2024, 1, 5), run_id="sim_x",
        at=datetime(2024, 1, 5, tzinfo=timezone.utc), open_orders=account.open_orders,
        applied_action_ids=applied, entitlements=entitlements,
    )
    assert entitlements[0].eligible_quantity == 0
    assert entitlements[0].status == "PAID"
    assert not paid.ledger_entries
    assert account.base_cash.settled == 1000
