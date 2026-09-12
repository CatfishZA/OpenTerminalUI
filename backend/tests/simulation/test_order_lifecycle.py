from decimal import Decimal

from backend.simulation.domain.enums import OrderSide,OrderStatus,OrderType,TimeInForce
from backend.tests.simulation.engine_fixtures import bar,simulate
from backend.tests.simulation.fixtures import instrument


def test_limit_buy_touched_intraday():
    r=simulate([bar(1),bar(2,open="105",high="106",low="98",close="101")],
        [(1,instrument(),OrderSide.BUY,"10",OrderType.LIMIT,TimeInForce.DAY,"100")])
    assert r.fills[0].price==Decimal("100")


def test_limit_sell_touched_intraday():
    req=[(1,instrument(),OrderSide.BUY,"10",OrderType.MARKET,TimeInForce.DAY,None),
         (2,instrument(),OrderSide.SELL,"10",OrderType.LIMIT,TimeInForce.DAY,"110")]
    r=simulate([bar(1),bar(2),bar(3,open="105",high="112",low="102",close="108")],req)
    assert r.fills[-1].price==Decimal("110")


def test_sell_stop_triggers_without_favorable_price():
    req=[(1,instrument(),OrderSide.BUY,"10",OrderType.MARKET,TimeInForce.DAY,None),
         (2,instrument(),OrderSide.SELL,"10",OrderType.STOP,TimeInForce.GTC,"90")]
    r=simulate([bar(1),bar(2),bar(3,open="95",high="100",low="85",close="88")],req)
    assert r.fills[-1].price==Decimal("90")
    assert r.orders[-1].status is OrderStatus.FILLED


def test_eod_portfolio_uses_official_close_mark():
    r=simulate([bar(1),bar(2,open="100",high="130",low="90",close="125")],
        [(1,instrument(),OrderSide.BUY,"10",OrderType.MARKET,TimeInForce.DAY,None)])
    assert r.portfolio_snapshots[-1].market_value==Decimal("1250")
    assert r.position_snapshots[-1].mark_price==Decimal("125")
