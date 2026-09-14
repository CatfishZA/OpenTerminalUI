from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from backend.simulation.domain.account import AccountState
from backend.simulation.domain.cash import CashBalance
from backend.simulation.domain.corporate_actions import CorporateAction
from backend.simulation.domain.enums import CorporateActionType, OrderSide, OrderStatus, OrderType, TimeInForce
from backend.simulation.domain.orders import Order
from backend.simulation.domain.positions import Position
from backend.simulation.engine.corporate_action_engine import CorporateActionEngine
from backend.tests.simulation.fixtures import instrument


NOW = datetime(2024, 1, 3, 14, 30, tzinfo=timezone.utc)


def _split(factor: str) -> CorporateAction:
    return CorporateAction(
        "split-1", instrument(), CorporateActionType.SPLIT, date(2024, 1, 3),
        None, None, Decimal(factor), None, None, "v1",
    )


def _account(quantity: str = "100", cost: str = "200") -> AccountState:
    inst = instrument()
    return AccountState(
        "acct", "USD", cash={"USD": CashBalance("USD", settled=Decimal("10000"))},
        positions={inst: Position(inst, Decimal(quantity), Decimal(cost), last_mark=Decimal(cost), market_value=Decimal(quantity) * Decimal(cost))},
        equity=Decimal("30000"), buying_power=Decimal("10000"),
    )


def test_split_and_reverse_split_preserve_decimal_cost_basis_and_no_pnl() -> None:
    engine = CorporateActionEngine()
    account = _account()
    engine.apply_session_actions(account, [_split("2")], date(2024, 1, 3), run_id="sim_x", at=NOW, open_orders=account.open_orders, applied_action_ids=set(), entitlements=[])
    position = account.positions[instrument()]
    assert position.quantity == 200 and position.average_cost == 100
    assert position.quantity * position.average_cost == Decimal("20000")
    assert account.realized_pnl == 0

    reverse = _account("3", "100")
    engine.apply_session_actions(reverse, [_split("0.5")], date(2024, 1, 3), run_id="sim_y", at=NOW, open_orders=reverse.open_orders, applied_action_ids=set(), entitlements=[])
    assert reverse.positions[instrument()].quantity == Decimal("1.5")
    assert reverse.positions[instrument()].average_cost == Decimal("200")


def test_split_adjusts_limit_stop_sell_and_buy_reservation_once() -> None:
    inst = instrument()
    account = _account()
    account.cash["USD"] = CashBalance("USD", settled=Decimal("10000"), reserved=Decimal("24000"))
    orders = {
        "sell": Order("sell", "sim_x", "acct", inst, OrderSide.SELL, OrderType.LIMIT, Decimal("100"), Decimal("80"), TimeInForce.GTC, NOW, NOW, NOW, limit_price=Decimal("240"), status=OrderStatus.ACCEPTED),
        "stop": Order("stop", "sim_x", "acct", inst, OrderSide.SELL, OrderType.STOP, Decimal("10"), Decimal("10"), TimeInForce.GTC, NOW, NOW, NOW, stop_price=Decimal("180"), status=OrderStatus.ACCEPTED),
        "buy": Order("buy", "sim_x", "acct", inst, OrderSide.BUY, OrderType.LIMIT, Decimal("100"), Decimal("100"), TimeInForce.GTC, NOW, NOW, NOW, limit_price=Decimal("240"), status=OrderStatus.ACCEPTED, metadata={"reserved": "24000"}),
    }
    account.open_orders = dict(orders)
    applied: set[str] = set()
    engine = CorporateActionEngine()
    first = engine.apply_session_actions(account, [_split("2")], date(2024, 1, 3), run_id="sim_x", at=NOW, open_orders=account.open_orders, applied_action_ids=applied, entitlements=[])
    assert account.open_orders["sell"].quantity == 200 and account.open_orders["sell"].remaining_quantity == 160
    assert account.open_orders["sell"].limit_price == 120
    assert account.open_orders["stop"].stop_price == 90
    assert account.open_orders["buy"].metadata["reserved"] == "24000"
    assert account.base_cash.reserved == 24000
    assert {order.id for order in first.adjusted_orders} == {"sell", "stop", "buy"}
    second = engine.apply_session_actions(account, [_split("2")], date(2024, 1, 3), run_id="sim_x", at=NOW, open_orders=account.open_orders, applied_action_ids=applied, entitlements=[])
    assert not second.applied and account.positions[inst].quantity == 200
