from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal

from backend.simulation.domain.enums import EventType, OrderSide, OrderType, TimeInForce
from backend.simulation.domain.market import MarketBar, MarketDataManifest
from backend.simulation.domain.strategy import StrategyIntent
from backend.simulation.engine.daily_simulator import DailySimulator, DailySimulatorDependencies
from backend.simulation.execution.commissions import BpsCommissionModel
from backend.simulation.execution.fixed_bps import FixedBpsExecutionModel
from backend.tests.simulation.fixtures import instrument, run_spec


def bar(day: int, *, inst=None, open="100", high="105", low="95", close="100", volume="100000"):
    session=date(2024,1,day); inst=inst or instrument()
    return MarketBar(inst,datetime.combine(session,time(14,30),timezone.utc),datetime.combine(session,time(21),timezone.utc),
        Decimal(open),Decimal(high),Decimal(low),Decimal(close),Decimal(volume),"v1")


class Data:
    def __init__(self,bars): self.bars=list(bars)
    def manifest(self):
        return MarketDataManifest("v1","dataset",tuple(sorted({x.instrument for x in self.bars},key=lambda x:x.key)),
            min(x.ts_open.date() for x in self.bars),max(x.ts_open.date() for x in self.bars),"fixture",False,"fixture-calendar")
    def iter_daily_events(self,instruments,start,end): return iter(self.bars)  # noqa: ANN001


class Store:
    def __init__(self): self.items=[]
    def append(self,item): self.items.append(item)  # noqa: ANN001
    def iter_run(self,run_id): return (x for x in self.items if x.run_id==run_id)  # noqa: ANN001


class Strategy:
    def __init__(self, requests): self.requests=list(requests); self.sent=set()
    def on_start(self,ctx): pass  # noqa: ANN001
    def on_finish(self,ctx): pass  # noqa: ANN001
    def on_event(self,ctx,event):  # noqa: ANN001
        found=[]
        for index,(day,inst,side,qty,kind,tif,price) in enumerate(self.requests):
            if index not in self.sent and event.event_type is EventType.STRATEGY_CLOSE_CALLBACK and ctx.now.date()==date(2024,1,day) and event.instrument==inst:
                self.sent.add(index)
                found.append(StrategyIntent(inst,side,Decimal(qty),ctx.now,kind,tif,
                    limit_price=Decimal(price) if kind is OrderType.LIMIT else None,
                    stop_price=Decimal(price) if kind is OrderType.STOP else None))
        return found


def simulate(bars,requests,*,cash="100000",participation="1",bps="0",minimum="0",settlement_days=1,run_id="sim_test"):
    events,ledger=Store(),Store()
    deps=DailySimulatorDependencies(Data(bars),None,Strategy(requests),FixedBpsExecutionModel(Decimal(bps),Decimal(participation)),
        BpsCommissionModel(Decimal(bps),Decimal(minimum)),events,ledger)
    spec=run_spec(universe=tuple(sorted({x.instrument for x in bars},key=lambda x:x.key)),start=min(x.ts_open.date() for x in bars),
        end=max(x.ts_open.date() for x in bars),initial_cash=Decimal(cash),data_version_id="v1",
        settlement_profile={"settlement_days":settlement_days},execution_profile={"model":"fixed_bps","daily_bar_path_policy":"WORST_CASE"})
    return DailySimulator(deps).run(spec,run_id=run_id)
