"""add canonical simulation core tables

Revision ID: 0012_simulation_core
Revises: 0011_saved_views
Create Date: 2026-09-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0012_simulation_core"
down_revision = "0011_saved_views"
branch_labels = None
depends_on = None

AMOUNT = sa.Numeric(38, 18)


def upgrade() -> None:
    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("legacy_backtest_run_id", sa.String(64), nullable=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("verification_level", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("strategy_key", sa.String(160), nullable=False),
        sa.Column("strategy_hash", sa.String(128), nullable=False),
        sa.Column("code_hash", sa.String(128), nullable=True),
        sa.Column("data_version_id", sa.String(36), nullable=True),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["data_version_id"], ["data_versions.id"], ondelete="SET NULL"),
    )
    for name, columns in (
        ("ix_simulation_runs_legacy_backtest_run_id", ["legacy_backtest_run_id"]),
        ("ix_simulation_runs_status", ["status"]),
        ("ix_simulation_runs_strategy_key", ["strategy_key"]),
        ("ix_simulation_runs_data_version_id", ["data_version_id"]),
        ("ix_simulation_runs_created_at", ["created_at"]),
    ):
        op.create_index(name, "simulation_runs", columns)

    op.create_table(
        "simulation_events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processing_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("instrument_key", sa.String(160), nullable=True),
        sa.Column("order_id", sa.String(64), nullable=True),
        sa.Column("fill_id", sa.String(64), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_simulation_events_run_sequence"),
    )
    op.create_index("ix_simulation_events_run_id", "simulation_events", ["run_id"])
    op.create_index("ix_simulation_events_run_time", "simulation_events", ["run_id", "event_time"])
    op.create_index("ix_simulation_events_run_type", "simulation_events", ["run_id", "event_type"])

    op.create_table(
        "simulation_orders",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("instrument_key", sa.String(160), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("order_type", sa.String(16), nullable=False),
        sa.Column("quantity", AMOUNT, nullable=False),
        sa.Column("remaining_quantity", AMOUNT, nullable=False),
        sa.Column("tif", sa.String(8), nullable=False),
        sa.Column("limit_price", AMOUNT, nullable=True),
        sa.Column("stop_price", AMOUNT, nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("strategy_order_id", sa.String(64), nullable=True),
        sa.Column("parent_order_id", sa.String(64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_simulation_orders_run_id", "simulation_orders", ["run_id"])
    op.create_index("ix_simulation_orders_instrument_key", "simulation_orders", ["instrument_key"])

    op.create_table(
        "simulation_fills",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("order_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("instrument_key", sa.String(160), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", AMOUNT, nullable=False),
        sa.Column("price", AMOUNT, nullable=False),
        sa.Column("commission", AMOUNT, nullable=False),
        sa.Column("fees", AMOUNT, nullable=False),
        sa.Column("slippage_bps", AMOUNT, nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("execution_model", sa.String(64), nullable=False),
        sa.Column("liquidity_flag", sa.String(32), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["simulation_orders.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_simulation_fills_run_id", "simulation_fills", ["run_id"])
    op.create_index("ix_simulation_fills_order_id", "simulation_fills", ["order_id"])

    op.create_table(
        "simulation_ledger_entries",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_type", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("amount", AMOUNT, nullable=False),
        sa.Column("instrument_key", sa.String(160), nullable=True),
        sa.Column("order_id", sa.String(64), nullable=True),
        sa.Column("fill_id", sa.String(64), nullable=True),
        sa.Column("corporate_action_id", sa.String(64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_simulation_ledger_entries_run_id", "simulation_ledger_entries", ["run_id"])

    op.create_table(
        "simulation_position_snapshots",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("instrument_key", sa.String(160), nullable=False),
        sa.Column("quantity", AMOUNT, nullable=False),
        sa.Column("average_cost", AMOUNT, nullable=False),
        sa.Column("mark_price", AMOUNT, nullable=False),
        sa.Column("market_value", AMOUNT, nullable=False),
        sa.Column("realized_pnl", AMOUNT, nullable=False),
        sa.Column("unrealized_pnl", AMOUNT, nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "snapshot_time", "instrument_key", name="uq_sim_position_snapshot"),
    )
    op.create_index("ix_simulation_position_snapshots_run_id", "simulation_position_snapshots", ["run_id"])

    op.create_table(
        "simulation_portfolio_snapshots",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cash_settled", AMOUNT, nullable=False),
        sa.Column("cash_unsettled", AMOUNT, nullable=False),
        sa.Column("cash_reserved", AMOUNT, nullable=False),
        sa.Column("gross_exposure", AMOUNT, nullable=False),
        sa.Column("net_exposure", AMOUNT, nullable=False),
        sa.Column("market_value", AMOUNT, nullable=False),
        sa.Column("realized_pnl", AMOUNT, nullable=False),
        sa.Column("unrealized_pnl", AMOUNT, nullable=False),
        sa.Column("fees", AMOUNT, nullable=False),
        sa.Column("equity", AMOUNT, nullable=False),
        sa.Column("buying_power", AMOUNT, nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "snapshot_time", name="uq_sim_portfolio_snapshot"),
    )
    op.create_index("ix_simulation_portfolio_snapshots_run_id", "simulation_portfolio_snapshots", ["run_id"])

    op.create_table(
        "simulation_applied_corporate_actions",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("corporate_action_source_id", sa.String(64), nullable=False),
        sa.Column("instrument_key", sa.String(160), nullable=False),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("effective_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "corporate_action_source_id", name="uq_sim_applied_corporate_action"),
    )
    op.create_index("ix_simulation_applied_corporate_actions_run_id", "simulation_applied_corporate_actions", ["run_id"])


def downgrade() -> None:
    for table_name in (
        "simulation_applied_corporate_actions",
        "simulation_portfolio_snapshots",
        "simulation_position_snapshots",
        "simulation_ledger_entries",
        "simulation_fills",
        "simulation_orders",
        "simulation_events",
        "simulation_runs",
    ):
        op.drop_table(table_name)
