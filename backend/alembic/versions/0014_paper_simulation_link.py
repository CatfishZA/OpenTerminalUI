"""link paper trading to canonical simulation

Revision ID: 0014_paper_simulation_link
Revises: 0013_backtest_simulation_link
Create Date: 2026-09-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0014_paper_simulation_link"
down_revision = "0013_backtest_simulation_link"
branch_labels = None
depends_on = None

AMOUNT = sa.Numeric(38, 18)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("virtual_portfolios"):
        op.create_table(
            "virtual_portfolios",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("initial_capital", sa.Float(), nullable=False),
            sa.Column("current_cash", sa.Float(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_virtual_portfolios_user_id", "virtual_portfolios", ["user_id"])
        op.create_index("ix_virtual_portfolios_is_active", "virtual_portfolios", ["is_active"])
    if not inspector.has_table("virtual_positions"):
        op.create_table(
            "virtual_positions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("portfolio_id", sa.String(36), nullable=False),
            sa.Column("symbol", sa.String(64), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("avg_entry_price", sa.Float(), nullable=False),
            sa.Column("side", sa.String(8), nullable=False),
            sa.ForeignKeyConstraint(["portfolio_id"], ["virtual_portfolios.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("portfolio_id", "symbol", name="uq_virtual_position_portfolio_symbol"),
        )
        op.create_index("ix_virtual_positions_portfolio_id", "virtual_positions", ["portfolio_id"])
        op.create_index("ix_virtual_positions_symbol", "virtual_positions", ["symbol"])
    if not inspector.has_table("virtual_orders"):
        op.create_table(
            "virtual_orders",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("portfolio_id", sa.String(36), nullable=False),
            sa.Column("symbol", sa.String(64), nullable=False),
            sa.Column("side", sa.String(8), nullable=False),
            sa.Column("order_type", sa.String(16), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("limit_price", sa.Float(), nullable=True),
            sa.Column("sl_price", sa.Float(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("fill_price", sa.Float(), nullable=True),
            sa.Column("fill_time", sa.DateTime(), nullable=True),
            sa.Column("slippage_bps", sa.Float(), nullable=False),
            sa.Column("commission", sa.Float(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("signal_metadata", sa.JSON(), nullable=False),
            sa.ForeignKeyConstraint(["portfolio_id"], ["virtual_portfolios.id"], ondelete="CASCADE"),
        )
        for name, columns in (
            ("ix_virtual_orders_portfolio_id", ["portfolio_id"]),
            ("ix_virtual_orders_symbol", ["symbol"]),
            ("ix_virtual_orders_side", ["side"]),
            ("ix_virtual_orders_order_type", ["order_type"]),
            ("ix_virtual_orders_status", ["status"]),
        ):
            op.create_index(name, "virtual_orders", columns)
    if not inspector.has_table("virtual_trades"):
        op.create_table(
            "virtual_trades",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("order_id", sa.String(36), nullable=False),
            sa.Column("portfolio_id", sa.String(36), nullable=False),
            sa.Column("symbol", sa.String(64), nullable=False),
            sa.Column("side", sa.String(8), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("price", sa.Float(), nullable=False),
            sa.Column("timestamp", sa.DateTime(), nullable=False),
            sa.Column("pnl_realized", sa.Float(), nullable=True),
            sa.ForeignKeyConstraint(["order_id"], ["virtual_orders.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["portfolio_id"], ["virtual_portfolios.id"], ondelete="CASCADE"),
        )
        for name, columns in (
            ("ix_virtual_trades_order_id", ["order_id"]),
            ("ix_virtual_trades_portfolio_id", ["portfolio_id"]),
            ("ix_virtual_trades_symbol", ["symbol"]),
            ("ix_virtual_trades_side", ["side"]),
            ("ix_virtual_trades_timestamp", ["timestamp"]),
        ):
            op.create_index(name, "virtual_trades", columns)

    with op.batch_alter_table("virtual_portfolios") as batch:
        batch.add_column(sa.Column("simulation_run_id", sa.String(64), nullable=True))
        batch.create_foreign_key(
            "fk_virtual_portfolios_simulation_run_id", "simulation_runs",
            ["simulation_run_id"], ["id"], ondelete="SET NULL",
        )
        batch.create_index("ix_virtual_portfolios_simulation_run_id", ["simulation_run_id"])
    with op.batch_alter_table("virtual_orders") as batch:
        batch.add_column(sa.Column("simulation_order_id", sa.String(64), nullable=True))
        batch.create_foreign_key(
            "fk_virtual_orders_simulation_order_id", "simulation_orders",
            ["simulation_order_id"], ["id"], ondelete="SET NULL",
        )
        batch.create_index("ix_virtual_orders_simulation_order_id", ["simulation_order_id"])
    with op.batch_alter_table("virtual_trades") as batch:
        batch.add_column(sa.Column("simulation_fill_id", sa.String(64), nullable=True))
        batch.create_foreign_key(
            "fk_virtual_trades_simulation_fill_id", "simulation_fills",
            ["simulation_fill_id"], ["id"], ondelete="SET NULL",
        )
        batch.create_index("ix_virtual_trades_simulation_fill_id", ["simulation_fill_id"])

    op.create_table(
        "simulation_settlement_obligations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("fill_id", sa.String(64), nullable=False, unique=True),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("amount", AMOUNT, nullable=False),
        sa.Column("settlement_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fill_id"], ["simulation_fills.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_simulation_settlement_obligations_run_id", "simulation_settlement_obligations", ["run_id"])
    op.create_index("ix_sim_settlement_run_date", "simulation_settlement_obligations", ["run_id", "settlement_date"])
    op.create_index("ix_sim_settlement_run_status", "simulation_settlement_obligations", ["run_id", "status"])


def downgrade() -> None:
    op.drop_table("simulation_settlement_obligations")
    with op.batch_alter_table("virtual_trades") as batch:
        batch.drop_index("ix_virtual_trades_simulation_fill_id")
        batch.drop_constraint("fk_virtual_trades_simulation_fill_id", type_="foreignkey")
        batch.drop_column("simulation_fill_id")
    with op.batch_alter_table("virtual_orders") as batch:
        batch.drop_index("ix_virtual_orders_simulation_order_id")
        batch.drop_constraint("fk_virtual_orders_simulation_order_id", type_="foreignkey")
        batch.drop_column("simulation_order_id")
    with op.batch_alter_table("virtual_portfolios") as batch:
        batch.drop_index("ix_virtual_portfolios_simulation_run_id")
        batch.drop_constraint("fk_virtual_portfolios_simulation_run_id", type_="foreignkey")
        batch.drop_column("simulation_run_id")
