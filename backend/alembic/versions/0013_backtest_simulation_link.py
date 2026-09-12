"""link legacy backtests to durable canonical simulations

Revision ID: 0013_backtest_simulation_link
Revises: 0012_simulation_core
Create Date: 2026-09-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0013_backtest_simulation_link"
down_revision = "0012_simulation_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("simulation_runs") as batch:
        batch.add_column(sa.Column("result_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("result_hash", sa.String(128), nullable=True))
    with op.batch_alter_table("backtest_runs") as batch:
        batch.add_column(sa.Column("simulation_run_id", sa.String(64), nullable=True))
        batch.create_foreign_key(
            "fk_backtest_runs_simulation_run_id",
            "simulation_runs",
            ["simulation_run_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_backtest_runs_simulation_run_id", ["simulation_run_id"])


def downgrade() -> None:
    with op.batch_alter_table("backtest_runs") as batch:
        batch.drop_index("ix_backtest_runs_simulation_run_id")
        batch.drop_constraint("fk_backtest_runs_simulation_run_id", type_="foreignkey")
        batch.drop_column("simulation_run_id")
    with op.batch_alter_table("simulation_runs") as batch:
        batch.drop_column("result_hash")
        batch.drop_column("result_json")
