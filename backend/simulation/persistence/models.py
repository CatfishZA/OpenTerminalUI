from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared.db import Base

AMOUNT = Numeric(38, 18)
BIGINT_PK = BigInteger().with_variant(Integer(), "sqlite")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SimulationRunORM(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    legacy_backtest_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    verification_level: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="QUEUED", index=True)
    strategy_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    strategy_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    code_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("data_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    request_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    manifest_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SimulationEventORM(Base):
    __tablename__ = "simulation_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_simulation_events_run_sequence"),
        Index("ix_simulation_events_run_time", "run_id", "event_time"),
        Index("ix_simulation_events_run_type", "run_id", "event_type"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processing_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    instrument_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fill_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class SimulationOrderORM(Base):
    __tablename__ = "simulation_orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    remaining_quantity: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    tif: Mapped[str] = mapped_column(String(8), nullable=False)
    limit_price: Mapped[object | None] = mapped_column(AMOUNT, nullable=True)
    stop_price: Mapped[object | None] = mapped_column(AMOUNT, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    strategy_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class SimulationFillORM(Base):
    __tablename__ = "simulation_fills"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("simulation_orders.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument_key: Mapped[str] = mapped_column(String(160), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    price: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    commission: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    fees: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    slippage_bps: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    execution_model: Mapped[str] = mapped_column(String(64), nullable=False)
    liquidity_flag: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class SimulationLedgerEntryORM(Base):
    __tablename__ = "simulation_ledger_entries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    amount: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    instrument_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fill_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    corporate_action_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class SimulationPositionSnapshotORM(Base):
    __tablename__ = "simulation_position_snapshots"
    __table_args__ = (
        UniqueConstraint("run_id", "snapshot_time", "instrument_key", name="uq_sim_position_snapshot"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    instrument_key: Mapped[str] = mapped_column(String(160), nullable=False)
    quantity: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    average_cost: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    mark_price: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    market_value: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    realized_pnl: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    unrealized_pnl: Mapped[object] = mapped_column(AMOUNT, nullable=False)


class SimulationPortfolioSnapshotORM(Base):
    __tablename__ = "simulation_portfolio_snapshots"
    __table_args__ = (UniqueConstraint("run_id", "snapshot_time", name="uq_sim_portfolio_snapshot"),)

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cash_settled: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    cash_unsettled: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    cash_reserved: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    gross_exposure: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    net_exposure: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    market_value: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    realized_pnl: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    unrealized_pnl: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    fees: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    equity: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    buying_power: Mapped[object] = mapped_column(AMOUNT, nullable=False)


class SimulationAppliedCorporateActionORM(Base):
    __tablename__ = "simulation_applied_corporate_actions"
    __table_args__ = (
        UniqueConstraint("run_id", "corporate_action_source_id", name="uq_sim_applied_corporate_action"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    corporate_action_source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument_key: Mapped[str] = mapped_column(String(160), nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class SimulationSettlementObligationORM(Base):
    __tablename__ = "simulation_settlement_obligations"
    __table_args__ = (
        Index("ix_sim_settlement_run_date", "run_id", "settlement_date"),
        Index("ix_sim_settlement_run_status", "run_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    fill_id: Mapped[str] = mapped_column(String(64), ForeignKey("simulation_fills.id", ondelete="CASCADE"), unique=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    amount: Mapped[object] = mapped_column(AMOUNT, nullable=False)
    settlement_date: Mapped[object] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
