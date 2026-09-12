from backend.simulation.domain.enums import EventType,OrderSide,OrderType,TimeInForce
from backend.simulation.engine.event_clock import EVENT_PRIORITY
from backend.tests.simulation.engine_fixtures import bar,simulate
from backend.tests.simulation.fixtures import instrument

def test_event_sequence_and_equal_time_priority():
    r=simulate([bar(1),bar(2)],[(1,instrument(),OrderSide.BUY,"10",OrderType.MARKET,TimeInForce.DAY,None)])
    assert [x.sequence for x in r.events]==list(range(1,len(r.events)+1))
    for before,after in zip(r.events,r.events[1:]):
        if before.event_time==after.event_time: assert EVENT_PRIORITY.get(before.event_type,75)<=EVENT_PRIORITY.get(after.event_type,75)
    close=next(x for x in r.events if x.event_type is EventType.BAR_CLOSE)
    callback=next(x for x in r.events if x.event_type is EventType.STRATEGY_CLOSE_CALLBACK)
    assert close.sequence<callback.sequence<next(x.sequence for x in r.events if x.event_type is EventType.ORDER_SUBMITTED)
