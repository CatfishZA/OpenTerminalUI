from backend.simulation.domain.enums import OrderSide,OrderType,TimeInForce
from backend.tests.simulation.engine_fixtures import bar,simulate
from backend.tests.simulation.fixtures import instrument

def test_cash_positions_and_equity_reconcile():
    r=simulate([bar(1),bar(2)],[(1,instrument(),OrderSide.BUY,"10",OrderType.MARKET,TimeInForce.DAY,None)])
    assert r.reconciliation=={"cash":True,"positions":True,"equity":True}
