from backend.simulation.domain.enums import OrderSide,OrderStatus,OrderType,TimeInForce
from backend.simulation.domain.identifiers import InstrumentId
from backend.tests.simulation.engine_fixtures import bar,simulate

def test_assets_share_cash_and_second_order_is_rejected():
    a=InstrumentId("AAPL","NASDAQ","EQUITY","USD"); m=InstrumentId("MSFT","NASDAQ","EQUITY","USD")
    bars=[bar(1,inst=a),bar(1,inst=m),bar(2,inst=a),bar(2,inst=m)]
    req=[(1,a,OrderSide.BUY,"700",OrderType.MARKET,TimeInForce.DAY,None),(1,m,OrderSide.BUY,"700",OrderType.MARKET,TimeInForce.DAY,None)]
    result=simulate(bars,req)
    assert [x.status for x in result.orders].count(OrderStatus.REJECTED)==1
    assert sum(x.quantity*x.price for x in result.fills)<=100000
