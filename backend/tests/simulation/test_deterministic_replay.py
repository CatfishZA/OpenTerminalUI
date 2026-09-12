from backend.simulation.domain.enums import OrderSide,OrderType,TimeInForce
from backend.tests.simulation.engine_fixtures import bar,simulate
from backend.tests.simulation.fixtures import instrument

def test_replay_is_value_for_value_deterministic():
    args=([bar(1),bar(2)],[(1,instrument(),OrderSide.BUY,"10",OrderType.MARKET,TimeInForce.DAY,None)])
    first=simulate(*args); second=simulate(*args)
    assert first.result_hash==second.result_hash
    assert first.events==second.events and first.fills==second.fills and first.ledger==second.ledger
    assert first.portfolio_snapshots==second.portfolio_snapshots
