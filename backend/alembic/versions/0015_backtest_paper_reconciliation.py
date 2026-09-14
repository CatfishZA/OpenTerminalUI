"""add immutable backtest paper reconciliation

Revision ID: 0015_backtest_paper_reconciliation
Revises: 0014_paper_simulation_link
Create Date: 2026-09-14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0015_backtest_paper_reconciliation"
down_revision = "0014_paper_simulation_link"
branch_labels = None
depends_on = None

AMOUNT = sa.Numeric(38, 18)


def upgrade() -> None:
    op.create_table(
        "simulation_reconciliations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("baseline_run_id", sa.String(64), nullable=False),
        sa.Column("paper_run_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("alignment_policy", sa.String(32), nullable=False),
        sa.Column("allow_research_baseline", sa.Boolean(), nullable=False),
        sa.Column("include_low_confidence", sa.Boolean(), nullable=False),
        sa.Column("paper_cutoff_sequence", sa.BigInteger(), nullable=False),
        sa.Column("paper_cutoff_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("baseline_manifest_hash", sa.String(128), nullable=True),
        sa.Column("baseline_result_hash", sa.String(128), nullable=True),
        sa.Column("paper_manifest_hash", sa.String(128), nullable=True),
        sa.Column("request_hash", sa.String(128), nullable=False),
        sa.Column("report_hash", sa.String(128), nullable=True),
        sa.Column("compatibility_json", sa.JSON(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("calibration_json", sa.JSON(), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["baseline_run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["paper_run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("request_hash", name="uq_sim_reconciliation_request_hash"),
    )
    op.create_index("ix_simulation_reconciliations_baseline_run_id", "simulation_reconciliations", ["baseline_run_id"])
    op.create_index("ix_simulation_reconciliations_paper_run_id", "simulation_reconciliations", ["paper_run_id"])
    op.create_index("ix_simulation_reconciliations_created_at", "simulation_reconciliations", ["created_at"])
    op.create_index("ix_simulation_reconciliations_request_hash", "simulation_reconciliations", ["request_hash"])

    op.create_table(
        "simulation_reconciliation_items",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("reconciliation_id", sa.String(64), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("item_type", sa.String(16), nullable=False),
        sa.Column("instrument_key", sa.String(160), nullable=True),
        sa.Column("baseline_order_id", sa.String(64), nullable=True),
        sa.Column("paper_order_id", sa.String(64), nullable=True),
        sa.Column("match_status", sa.String(24), nullable=False),
        sa.Column("match_basis", sa.String(32), nullable=False),
        sa.Column("match_confidence", sa.String(16), nullable=False),
        sa.Column("divergence_codes_json", sa.JSON(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["reconciliation_id"], ["simulation_reconciliations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("reconciliation_id", "sequence", name="uq_sim_reconciliation_item_sequence"),
    )
    op.create_index("ix_simulation_reconciliation_items_reconciliation_id", "simulation_reconciliation_items", ["reconciliation_id"])
    op.create_index("ix_sim_reconciliation_item_type", "simulation_reconciliation_items", ["reconciliation_id", "item_type"])
    op.create_index("ix_sim_reconciliation_instrument", "simulation_reconciliation_items", ["reconciliation_id", "instrument_key"])
    op.create_index("ix_simulation_reconciliation_items_match_status", "simulation_reconciliation_items", ["match_status"])

    op.create_table(
        "simulation_execution_observations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("order_id", sa.String(64), nullable=False),
        sa.Column("fill_id", sa.String(64), nullable=False),
        sa.Column("instrument_key", sa.String(160), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tick_price", AMOUNT, nullable=False),
        sa.Column("bid", AMOUNT, nullable=True),
        sa.Column("ask", AMOUNT, nullable=True),
        sa.Column("tick_size", AMOUNT, nullable=True),
        sa.Column("tick_source", sa.String(128), nullable=True),
        sa.Column("liquidity_assumption", sa.String(64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["simulation_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fill_id"], ["simulation_fills.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("fill_id", name="uq_sim_execution_observation_fill_id"),
    )
    op.create_index("ix_simulation_execution_observations_run_id", "simulation_execution_observations", ["run_id"])
    op.create_index("ix_simulation_execution_observations_order_id", "simulation_execution_observations", ["order_id"])


def downgrade() -> None:
    op.drop_table("simulation_execution_observations")
    op.drop_table("simulation_reconciliation_items")
    op.drop_table("simulation_reconciliations")
