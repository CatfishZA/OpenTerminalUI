"""add corporate-action dates and simulation entitlements

Revision ID: 0017_corporate_actions_data_integrity
Revises: 0016_historical_replay
Create Date: 2026-09-14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0017_corporate_actions_data_integrity"
down_revision = "0016_historical_replay"
branch_labels = None
depends_on = None

AMOUNT = sa.Numeric(38, 18)


def upgrade() -> None:
    with op.batch_alter_table("corp_actions") as batch:
        batch.add_column(sa.Column("ex_date", sa.String(16), nullable=True))
        batch.add_column(sa.Column("record_date", sa.String(16), nullable=True))
        batch.add_column(sa.Column("pay_date", sa.String(16), nullable=True))
        batch.add_column(sa.Column("currency", sa.String(8), nullable=True))
        batch.add_column(sa.Column("source", sa.String(64), nullable=True))
        batch.add_column(sa.Column("metadata_json", sa.JSON(), nullable=True))
        batch.create_index("ix_corp_actions_ex_date", ["ex_date"])
        batch.create_index("ix_corp_actions_pay_date", ["pay_date"])

    op.create_table(
        "simulation_corporate_action_entitlements",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("corporate_action_source_id", sa.String(64), nullable=False),
        sa.Column("instrument_key", sa.String(160), nullable=False),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("entitlement_date", sa.Date(), nullable=False),
        sa.Column("pay_date", sa.Date(), nullable=False),
        sa.Column("eligible_quantity", AMOUNT, nullable=False),
        sa.Column("cash_amount_per_share", AMOUNT, nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("total_amount", AMOUNT, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "corporate_action_source_id", name="uq_sim_ca_entitlement_run_source"),
    )
    op.create_index("ix_simulation_corporate_action_entitlements_run_id", "simulation_corporate_action_entitlements", ["run_id"])
    op.create_index("ix_sim_ca_entitlement_run_status", "simulation_corporate_action_entitlements", ["run_id", "status"])
    op.create_index("ix_sim_ca_entitlement_run_pay_date", "simulation_corporate_action_entitlements", ["run_id", "pay_date"])


def downgrade() -> None:
    op.drop_table("simulation_corporate_action_entitlements")
    with op.batch_alter_table("corp_actions") as batch:
        batch.drop_index("ix_corp_actions_pay_date")
        batch.drop_index("ix_corp_actions_ex_date")
        batch.drop_column("metadata_json")
        batch.drop_column("source")
        batch.drop_column("currency")
        batch.drop_column("pay_date")
        batch.drop_column("record_date")
        batch.drop_column("ex_date")
