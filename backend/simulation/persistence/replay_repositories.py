from __future__ import annotations

from backend.simulation.domain.events import LedgerEntry, SimulationEvent
from backend.simulation.domain.fills import Fill
from backend.simulation.domain.orders import Order
from backend.simulation.domain.results import PortfolioSnapshot, PositionSnapshot
from backend.simulation.persistence.models import (
    SimulationEventORM,
    SimulationFillORM,
    SimulationLedgerEntryORM,
    SimulationOrderORM,
    SimulationPortfolioSnapshotORM,
    SimulationPositionSnapshotORM,
)
from backend.simulation.persistence.serializers import to_primitive


class ReplayEventStore:
    """Transaction-aware event sink; the replay service owns commit/rollback."""

    def __init__(self, db):  # noqa: ANN001
        self.db = db

    def append(self, event: SimulationEvent) -> None:
        self.db.add(SimulationEventORM(
            run_id=event.run_id, sequence=event.sequence, event_id=event.event_id,
            event_type=event.event_type.value, event_time=event.event_time,
            processing_time=event.processing_time,
            instrument_key=event.instrument.key if event.instrument else None,
            order_id=event.order_id, fill_id=event.fill_id,
            payload_json=to_primitive(event.payload),
        ))


class ReplayLedgerRepository:
    def __init__(self, db):  # noqa: ANN001
        self.db = db

    def append(self, entry: LedgerEntry) -> None:
        # DailySessionKernel also sends every generated fill ledger entry to the
        # canonical record sink. Keeping this side-effect free avoids duplicate
        # pending INSERTs while preserving the batch engine's dual-port contract.
        return None


class ReplayRecordRepository:
    """Canonical record sink with no per-artifact commits."""

    def __init__(self, db):  # noqa: ANN001
        self.db = db

    def save_order(self, order: Order) -> None:
        row = self.db.get(SimulationOrderORM, order.id) or SimulationOrderORM(id=order.id, run_id=order.run_id)
        row.account_id = order.account_id
        row.instrument_key = order.instrument.key
        row.side = order.side.value
        row.order_type = order.order_type.value
        row.quantity = order.quantity
        row.remaining_quantity = order.remaining_quantity
        row.tif = order.tif.value
        row.limit_price = order.limit_price
        row.stop_price = order.stop_price
        row.status = order.status.value
        row.submitted_at = order.submitted_at
        row.accepted_at = order.accepted_at
        row.completed_at = order.completed_at
        row.strategy_order_id = order.strategy_order_id
        row.parent_order_id = order.parent_order_id
        row.metadata_json = to_primitive({**order.metadata, "eligible_at": order.eligible_at})
        self.db.add(row)

    def save_fill(self, fill: Fill) -> None:
        if self.db.get(SimulationFillORM, fill.id) is None:
            self.db.add(SimulationFillORM(
                id=fill.id, run_id=fill.run_id, order_id=fill.order_id,
                account_id=fill.account_id, instrument_key=fill.instrument.key,
                side=fill.side.value, quantity=fill.quantity, price=fill.price,
                commission=fill.commission, fees=fill.fees,
                slippage_bps=fill.slippage_bps, executed_at=fill.executed_at,
                execution_model=fill.execution_model, liquidity_flag=fill.liquidity_flag,
                metadata_json={},
            ))

    def save_ledger(self, entry: LedgerEntry) -> None:
        if self.db.get(SimulationLedgerEntryORM, entry.id) is None:
            self.db.add(_ledger_row(entry))

    def save_portfolio_snapshot(self, item: PortfolioSnapshot) -> None:
        self.db.add(SimulationPortfolioSnapshotORM(
            run_id=item.run_id, account_id=item.account_id, snapshot_time=item.snapshot_time,
            cash_settled=item.cash_settled, cash_unsettled=item.cash_unsettled,
            cash_reserved=item.cash_reserved, gross_exposure=item.gross_exposure,
            net_exposure=item.net_exposure, market_value=item.market_value,
            realized_pnl=item.realized_pnl, unrealized_pnl=item.unrealized_pnl,
            fees=item.fees, equity=item.equity, buying_power=item.buying_power,
        ))

    def save_position_snapshot(self, item: PositionSnapshot) -> None:
        self.db.add(SimulationPositionSnapshotORM(
            run_id=item.run_id, account_id=item.account_id, snapshot_time=item.snapshot_time,
            instrument_key=item.instrument.key, quantity=item.quantity,
            average_cost=item.average_cost, mark_price=item.mark_price,
            market_value=item.market_value, realized_pnl=item.realized_pnl,
            unrealized_pnl=item.unrealized_pnl,
        ))


def _ledger_row(entry: LedgerEntry) -> SimulationLedgerEntryORM:
    return SimulationLedgerEntryORM(
        id=entry.id, run_id=entry.run_id, account_id=entry.account_id,
        event_time=entry.ts, entry_type=entry.entry_type.value,
        currency=entry.currency, amount=entry.amount,
        instrument_key=entry.instrument.key if entry.instrument else None,
        order_id=entry.order_id, fill_id=entry.fill_id,
        corporate_action_id=entry.corporate_action_id,
        metadata_json=to_primitive(entry.metadata),
    )
