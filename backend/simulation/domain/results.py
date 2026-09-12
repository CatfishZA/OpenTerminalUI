from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.simulation.domain.events import LedgerEntry
from backend.simulation.domain.events import SimulationEvent
from backend.simulation.domain.fills import Fill
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.market import as_decimal, require_aware
from backend.simulation.domain.orders import Order
from backend.simulation.domain.run import RunManifest


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    run_id: str
    account_id: str
    snapshot_time: datetime
    instrument: InstrumentId
    quantity: Decimal
    average_cost: Decimal
    mark_price: Decimal
    market_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal

    def __post_init__(self) -> None:
        require_aware(self.snapshot_time, "snapshot_time")
        for name in ("quantity", "average_cost", "mark_price", "market_value", "realized_pnl", "unrealized_pnl"):
            object.__setattr__(self, name, as_decimal(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    run_id: str
    account_id: str
    snapshot_time: datetime
    cash_settled: Decimal
    cash_unsettled: Decimal
    cash_reserved: Decimal
    gross_exposure: Decimal
    net_exposure: Decimal
    market_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees: Decimal
    equity: Decimal
    buying_power: Decimal

    def __post_init__(self) -> None:
        require_aware(self.snapshot_time, "snapshot_time")
        for name in (
            "cash_settled", "cash_unsettled", "cash_reserved", "gross_exposure", "net_exposure",
            "market_value", "realized_pnl", "unrealized_pnl", "fees", "equity", "buying_power",
        ):
            object.__setattr__(self, name, as_decimal(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class SimulationResult:
    run_id: str
    manifest: RunManifest
    summary: dict[str, Any]
    orders: tuple[Order, ...] = ()
    fills: tuple[Fill, ...] = ()
    ledger: tuple[LedgerEntry, ...] = ()
    portfolio_snapshots: tuple[PortfolioSnapshot, ...] = ()
    position_snapshots: tuple[PositionSnapshot, ...] = ()
    equity_curve: tuple[dict[str, Any], ...] = ()
    daily_returns: tuple[Decimal, ...] = ()
    drawdown: tuple[Decimal, ...] = ()
    data_quality: dict[str, Any] = field(default_factory=dict)
    events: tuple[SimulationEvent, ...] = ()
    reconciliation: dict[str, Any] = field(default_factory=dict)
    result_hash: str = ""
