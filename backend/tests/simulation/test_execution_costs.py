from decimal import Decimal
from backend.simulation.domain.enums import OrderSide,OrderType,TimeInForce
from backend.tests.simulation.engine_fixtures import bar,simulate
from backend.tests.simulation.fixtures import instrument

def test_commission_and_cash_identity():
    req=[(1,instrument(),OrderSide.BUY,"100",OrderType.MARKET,TimeInForce.DAY,None),(2,instrument(),OrderSide.SELL,"100",OrderType.MARKET,TimeInForce.DAY,None)]
    r=simulate([bar(1,open="10",high="11",low="9",close="10"),bar(2,open="10",high="12",low="9",close="11"),bar(3,open="12",high="13",low="11",close="12")],req,cash="10000",bps="1",settlement_days=0)
    buy,sell=r.fills
    expected=Decimal("10000")-buy.quantity*buy.price-buy.commission+sell.quantity*sell.price-sell.commission
    assert r.summary["ending_cash"]==expected

def test_minimum_commission_per_fill():
    r=simulate([bar(1),bar(2)],[(1,instrument(),OrderSide.BUY,"1",OrderType.MARKET,TimeInForce.DAY,None)],minimum="5")
    assert r.fills[0].commission==Decimal("5")
