from __future__ import annotations

from backend.models import VirtualOrder, VirtualOrderStatus, VirtualPortfolio, VirtualPosition, VirtualTrade
from backend.simulation.domain.account import AccountState
from backend.simulation.domain.enums import OrderStatus
from backend.simulation.domain.fills import Fill
from backend.simulation.domain.orders import Order


def legacy_order_status(status: OrderStatus) -> str:
    if status is OrderStatus.FILLED:
        return VirtualOrderStatus.FILLED.value
    if status is OrderStatus.CANCELLED:
        return VirtualOrderStatus.CANCELLED.value
    if status is OrderStatus.REJECTED:
        return VirtualOrderStatus.REJECTED.value
    return VirtualOrderStatus.PENDING.value


class PaperLegacyProjection:
    """One-way compatibility projection; canonical state remains authoritative."""

    def project_account(self, db, portfolio: VirtualPortfolio, account: AccountState) -> None:  # noqa: ANN001
        portfolio.current_cash = float(account.base_cash.available)
        canonical_symbols: set[str] = set()
        for instrument, position in account.positions.items():
            symbol = f"{instrument.venue}:{instrument.symbol}"
            canonical_symbols.add(symbol)
            row = (
                db.query(VirtualPosition)
                .filter_by(portfolio_id=portfolio.id, symbol=symbol)
                .first()
            )
            if row is None:
                row = VirtualPosition(portfolio_id=portfolio.id, symbol=symbol, side="long")
                db.add(row)
            row.quantity = float(position.quantity)
            row.avg_entry_price = float(position.average_cost)

    @staticmethod
    def project_order(row: VirtualOrder, order: Order, *, fill: Fill | None = None) -> None:
        row.status = legacy_order_status(order.status)
        row.simulation_order_id = order.id
        metadata = dict(row.signal_metadata or {})
        metadata.update(
            {
                "canonical_status": order.status.value,
                "remaining_quantity": str(order.remaining_quantity),
            }
        )
        row.signal_metadata = metadata
        if fill is not None:
            row.fill_price = float(fill.price)
            row.fill_time = fill.executed_at
            row.commission = float(fill.commission)

    @staticmethod
    def project_fill(
        db,  # noqa: ANN001
        *,
        portfolio: VirtualPortfolio,
        order_row: VirtualOrder,
        fill: Fill,
        realized_pnl,
    ) -> VirtualTrade:
        row = VirtualTrade(
            order_id=order_row.id,
            portfolio_id=portfolio.id,
            symbol=order_row.symbol,
            side=order_row.side,
            quantity=float(fill.quantity),
            price=float(fill.price),
            timestamp=fill.executed_at,
            pnl_realized=float(realized_pnl) if order_row.side == "sell" else None,
            simulation_fill_id=fill.id,
        )
        db.add(row)
        return row
