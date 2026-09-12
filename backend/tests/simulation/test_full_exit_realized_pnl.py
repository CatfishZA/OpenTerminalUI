from decimal import Decimal
from backend.simulation.domain.enums import OrderSide,OrderType,TimeInForce
from backend.tests.simulation.engine_fixtures import bar,simulate
from backend.tests.simulation.fixtures import instrument

def test_full_exit_uses_pre_exit_cost_basis():
    req=[(1,instrument(),OrderSide.BUY,"100",OrderType.MARKET,TimeInForce.DAY,None),(2,instrument(),OrderSide.SELL,"100",OrderType.MARKET,TimeInForce.DAY,None)]
    r=simulate([bar(1),bar(2,open="10",high="12",low="9",close="11"),bar(3,open="12",high="13",low="11",close="12")],req,settlement_days=0)
    final=[x for x in r.position_snapshots if x.instrument==instrument()][-1]
    assert r.summary["realized_pnl"]==Decimal("200") and final.quantity==0 and final.average_cost==0
