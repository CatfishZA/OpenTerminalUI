"""add historical replay control state

Revision ID: 0016_historical_replay
Revises: 0015_backtest_paper_reconciliation
Create Date: 2026-09-14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0016_historical_replay"
down_revision = "0015_backtest_paper_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "simulation_replay_sessions",
        sa.Column("run_id", sa.String(64), primary_key=True),
        sa.Column("control_status", sa.String(16), nullable=False),
        sa.Column("start_session", sa.Date(), nullable=False),
        sa.Column("end_session", sa.Date(), nullable=False),
        sa.Column("current_session", sa.Date(), nullable=True),
        sa.Column("next_session", sa.Date(), nullable=True),
        sa.Column("completed_sessions", sa.Integer(), nullable=False),
        sa.Column("total_sessions", sa.Integer(), nullable=False),
        sa.Column("last_event_sequence", sa.BigInteger(), nullable=False),
        sa.Column("strategy_state_json", sa.JSON(), nullable=False),
        sa.Column("initialized", sa.Boolean(), nullable=False),
        sa.Column("finish_called", sa.Boolean(), nullable=False),
        sa.Column("checkpoint_hash", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sim_replay_control_status", "simulation_replay_sessions", ["control_status"])
    op.create_index("ix_sim_replay_updated_at", "simulation_replay_sessions", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_sim_replay_updated_at", table_name="simulation_replay_sessions")
    op.drop_index("ix_sim_replay_control_status", table_name="simulation_replay_sessions")
    op.drop_table("simulation_replay_sessions")
