from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.simulation.domain.cash import CashBalance
from backend.simulation.domain.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
    VerificationLevel,
)
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.orders import Order
from backend.tests.simulation.fixtures import run_spec


def test_instrument_identity_is_canonical_hashable_and_venue_specific() -> None:
    first = InstrumentId("aapl", "nasdaq", "equity", "usd")
    same = InstrumentId("AAPL", "NASDAQ", "EQUITY", "USD")
    other_venue = InstrumentId("AAPL", "NYSE", "EQUITY", "USD")
    assert first == same
    assert hash(first) == hash(same)
    assert first != other_venue
    assert first.key == "NASDAQ:EQUITY:AAPL:USD"


def test_accounting_fields_are_decimal() -> None:
    balance = CashBalance("usd", settled="100.10", unsettled_receivable=2)
    assert isinstance(balance.settled, Decimal)
    assert isinstance(balance.unsettled_receivable, Decimal)
    assert balance.total == Decimal("102.10")


def test_order_validation_requires_type_specific_price() -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="limit_price"):
        Order(
            id="ord_1",
            run_id="sim_1",
            account_id="acct_1",
            instrument=InstrumentId("AAPL", "NASDAQ", "EQUITY", "USD"),
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("10"),
            remaining_quantity=Decimal("10"),
            tif=TimeInForce.DAY,
            submitted_at=now,
            status=OrderStatus.CREATED,
        )


def test_order_validation_rejects_naive_timestamp_and_bad_quantity() -> None:
    kwargs = dict(
        id="ord_1",
        run_id="sim_1",
        account_id="acct_1",
        instrument=InstrumentId("AAPL", "NASDAQ", "EQUITY", "USD"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("10"),
        remaining_quantity=Decimal("11"),
        tif=TimeInForce.DAY,
        submitted_at=datetime.now(timezone.utc),
    )
    with pytest.raises(ValueError, match="quantity"):
        Order(**kwargs)
    kwargs["remaining_quantity"] = Decimal("10")
    kwargs["submitted_at"] = datetime.now()
    with pytest.raises(ValueError, match="timezone-aware"):
        Order(**kwargs)


def test_run_spec_rejects_invalid_range() -> None:
    with pytest.raises(ValueError, match="end date"):
        run_spec(start=run_spec().end, end=run_spec().start)


def test_verified_run_requires_data_version() -> None:
    with pytest.raises(ValueError, match="DATA_VERSION_REQUIRED"):
        run_spec(verification_level=VerificationLevel.VERIFIED)


def test_run_spec_rejects_unsupported_asset_class() -> None:
    with pytest.raises(ValueError, match="UNSUPPORTED_ASSET_CLASS"):
        run_spec(universe=(InstrumentId("ES", "CME", "FUTURE", "USD"),))
