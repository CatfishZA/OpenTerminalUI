from decimal import Decimal
from backend.simulation.domain.enums import OrderSide,OrderStatus,OrderType,TimeInForce
from backend.tests.simulation.engine_fixtures import bar,simulate
from backend.tests.simulation.fixtures import instrument

def test_gtc_partial_fill_carries():
    r=simulate([bar(1),bar(2,volume="20000"),bar(3,volume="20000")],[(1,instrument(),OrderSide.BUY,"10000",OrderType.MARKET,TimeInForce.GTC,None)],cash="2000000",participation="0.1")
    assert r.fills[0].quantity==Decimal("2000") and r.orders[0].remaining_quantity==Decimal("6000")
    assert r.orders[0].status is OrderStatus.PARTIALLY_FILLED

def test_day_partial_fill_expires():
    r=simulate([bar(1),bar(2,volume="20000")],[(1,instrument(),OrderSide.BUY,"10000",OrderType.MARKET,TimeInForce.DAY,None)],cash="2000000",participation="0.1")
    assert r.fills[0].quantity==Decimal("2000") and r.orders[0].status is OrderStatus.EXPIRED
