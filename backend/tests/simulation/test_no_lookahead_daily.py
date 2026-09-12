from decimal import Decimal
from backend.simulation.domain.enums import OrderSide,OrderType,TimeInForce
from backend.tests.simulation.engine_fixtures import bar,simulate
from backend.tests.simulation.fixtures import instrument

def test_close_signal_fills_next_open():
    result=simulate([bar(1,close="100"),bar(2,open="120",high="125",low="115",close="121")],[(1,instrument(),OrderSide.BUY,"10",OrderType.MARKET,TimeInForce.DAY,None)])
    assert result.fills[0].executed_at==bar(2).ts_open
    assert result.fills[0].price==Decimal("120")
    assert result.orders[0].submitted_at==bar(1).ts_close
