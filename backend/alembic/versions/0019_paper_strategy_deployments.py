"""add governed paper strategy deployments

Revision ID: 0019_paper_strategy_deployments
Revises: 0018_strategy_governance
Create Date: 2026-09-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0019_paper_strategy_deployments"
down_revision = "0018_strategy_governance"
branch_labels = None
depends_on = None

AMOUNT = sa.Numeric(38, 18)


def upgrade() -> None:
    op.create_table(
        "paper_strategy_deployments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("governance_record_id", sa.String(64), nullable=False),
        sa.Column("governance_decision_id", sa.String(64), nullable=False),
        sa.Column("baseline_run_id", sa.String(64), nullable=False),
        sa.Column("portfolio_id", sa.String(36), nullable=False),
        sa.Column("simulation_run_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("strategy_key", sa.String(160), nullable=False),
        sa.Column("strategy_hash", sa.String(128), nullable=False),
        sa.Column("code_hash", sa.String(128), nullable=True),
        sa.Column("approved_evidence_hash", sa.String(128), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("symbols_json", sa.JSON(), nullable=False),
        sa.Column("strategy_config_json", sa.JSON(), nullable=False),
        sa.Column("strategy_config_hash", sa.String(128), nullable=False),
        sa.Column("risk_policy_json", sa.JSON(), nullable=False),
        sa.Column("strategy_state_json", sa.JSON(), nullable=False),
        sa.Column("checkpoint_hash", sa.String(128), nullable=True),
        sa.Column("last_input_event_id", sa.String(160), nullable=True),
        sa.Column("last_input_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_decision_sequence", sa.BigInteger(), nullable=False),
        sa.Column("risk_day", sa.String(16), nullable=True),
        sa.Column("day_start_equity", AMOUNT, nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("halted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["governance_record_id"], ["strategy_governance_records.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["governance_decision_id"], ["strategy_governance_decisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["baseline_run_id"], ["simulation_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["portfolio_id"], ["virtual_portfolios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["simulation_run_id"], ["simulation_runs.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("simulation_run_id", name="uq_paper_strategy_deployment_run"),
    )
    op.create_index("ix_paper_strategy_deployments_user_id", "paper_strategy_deployments", ["user_id"])
    op.create_index("ix_paper_strategy_deployments_governance_record_id", "paper_strategy_deployments", ["governance_record_id"])
    op.create_index("ix_paper_strategy_deployments_portfolio_id", "paper_strategy_deployments", ["portfolio_id"])
    op.create_index("ix_paper_strategy_deployments_simulation_run_id", "paper_strategy_deployments", ["simulation_run_id"])
    op.create_index("ix_paper_strategy_deployment_status", "paper_strategy_deployments", ["status"])
    op.create_index("ix_paper_strategy_deployment_user_status", "paper_strategy_deployments", ["user_id", "status"])

    op.create_table(
        "paper_strategy_inputs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("deployment_id", sa.String(64), nullable=False),
        sa.Column("source_event_id", sa.String(160), nullable=False),
        sa.Column("instrument_key", sa.String(160), nullable=False),
        sa.Column("input_type", sa.String(32), nullable=False),
        sa.Column("input_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(128), nullable=False),
        sa.Column("accepted_sequence", sa.BigInteger(), nullable=False),
        sa.Column("processed_status", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["deployment_id"], ["paper_strategy_deployments.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("deployment_id", "source_event_id", name="uq_paper_strategy_input_source"),
        sa.UniqueConstraint("deployment_id", "accepted_sequence", name="uq_paper_strategy_input_sequence"),
    )
    op.create_index("ix_paper_strategy_inputs_deployment_id", "paper_strategy_inputs", ["deployment_id"])

    op.create_table(
        "paper_strategy_intents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("intent_id", sa.String(64), nullable=False),
        sa.Column("deployment_id", sa.String(64), nullable=False),
        sa.Column("input_id", sa.String(64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("instrument_key", sa.String(160), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", AMOUNT, nullable=False),
        sa.Column("order_type", sa.String(16), nullable=False),
        sa.Column("tif", sa.String(8), nullable=False),
        sa.Column("limit_price", AMOUNT, nullable=True),
        sa.Column("stop_price", AMOUNT, nullable=True),
        sa.Column("intent_fingerprint", sa.String(128), nullable=False),
        sa.Column("risk_decision", sa.String(16), nullable=False),
        sa.Column("risk_reason", sa.String(64), nullable=True),
        sa.Column("canonical_order_id", sa.String(64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["deployment_id"], ["paper_strategy_deployments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["input_id"], ["paper_strategy_inputs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["canonical_order_id"], ["simulation_orders.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("deployment_id", "input_id", "ordinal", name="uq_paper_strategy_intent_ordinal"),
        sa.UniqueConstraint("deployment_id", "intent_id", name="uq_paper_strategy_intent_id"),
    )
    op.create_index("ix_paper_strategy_intents_deployment_id", "paper_strategy_intents", ["deployment_id"])
    op.create_index("ix_paper_strategy_intents_canonical_order_id", "paper_strategy_intents", ["canonical_order_id"])

    op.create_table(
        "paper_strategy_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("deployment_id", sa.String(64), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["deployment_id"], ["paper_strategy_deployments.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("deployment_id", "sequence", name="uq_paper_strategy_event_sequence"),
    )
    op.create_index("ix_paper_strategy_events_deployment_id", "paper_strategy_events", ["deployment_id"])
    op.create_index("ix_paper_strategy_events_event_type", "paper_strategy_events", ["event_type"])


def downgrade() -> None:
    op.drop_table("paper_strategy_events")
    op.drop_table("paper_strategy_intents")
    op.drop_table("paper_strategy_inputs")
    op.drop_table("paper_strategy_deployments")
