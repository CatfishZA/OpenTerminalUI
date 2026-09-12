from decimal import Decimal
from backend.simulation.domain.enums import OrderSide,OrderType,TimeInForce
from backend.tests.simulation.engine_fixtures import bar,simulate
from backend.tests.simulation.fixtures import instrument

def test_sale_proceeds_are_unsettled_then_settle_t_plus_one():
    req=[(1,instrument(),OrderSide.BUY,"100",OrderType.MARKET,TimeInForce.DAY,None),(2,instrument(),OrderSide.SELL,"100",OrderType.MARKET,TimeInForce.DAY,None)]
    r=simulate([bar(1),bar(2,open="10",high="12",low="9",close="11"),bar(3,open="12",high="13",low="11",close="12"),bar(4,open="12",high="13",low="11",close="12")],req,settlement_days=1)
    assert r.portfolio_snapshots[2].cash_unsettled==Decimal("1200")
    assert r.portfolio_snapshots[3].cash_unsettled==0
