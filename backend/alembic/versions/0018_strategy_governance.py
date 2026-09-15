"""add canonical strategy governance

Revision ID: 0018_strategy_governance
Revises: 0017_corporate_actions_data_integrity
Create Date: 2026-09-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0018_strategy_governance"
down_revision = "0017_corporate_actions_data_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_governance_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("strategy_key", sa.String(160), nullable=False),
        sa.Column("strategy_hash", sa.String(128), nullable=False),
        sa.Column("current_stage", sa.String(16), nullable=False),
        sa.Column("baseline_run_id", sa.String(64), nullable=True),
        sa.Column("latest_paper_run_id", sa.String(64), nullable=True),
        sa.Column("latest_reconciliation_id", sa.String(64), nullable=True),
        sa.Column("latest_evidence_hash", sa.String(128), nullable=True),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["baseline_run_id"], ["simulation_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["latest_paper_run_id"], ["simulation_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["latest_reconciliation_id"], ["simulation_reconciliations.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("strategy_key", "strategy_hash", name="uq_strategy_governance_identity"),
    )
    op.create_index("ix_strategy_governance_records_strategy_key", "strategy_governance_records", ["strategy_key"])
    op.create_index("ix_strategy_governance_records_current_stage", "strategy_governance_records", ["current_stage"])
    op.create_index("ix_strategy_governance_records_baseline_run_id", "strategy_governance_records", ["baseline_run_id"])
    op.create_index("ix_strategy_governance_stage_key", "strategy_governance_records", ["current_stage", "strategy_key"])

    op.create_table(
        "strategy_governance_decisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("governance_record_id", sa.String(64), nullable=False),
        sa.Column("decision_type", sa.String(16), nullable=False),
        sa.Column("from_stage", sa.String(16), nullable=False),
        sa.Column("to_stage", sa.String(16), nullable=False),
        sa.Column("baseline_run_id", sa.String(64), nullable=True),
        sa.Column("paper_run_id", sa.String(64), nullable=True),
        sa.Column("reconciliation_id", sa.String(64), nullable=True),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("policy_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("evidence_hash", sa.String(128), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("checks_json", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("request_hash", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["governance_record_id"], ["strategy_governance_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["baseline_run_id"], ["simulation_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["paper_run_id"], ["simulation_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reconciliation_id"], ["simulation_reconciliations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("request_hash", name="uq_strategy_governance_request_hash"),
    )
    op.create_index("ix_strategy_governance_decisions_governance_record_id", "strategy_governance_decisions", ["governance_record_id"])
    op.create_index("ix_strategy_governance_decisions_evidence_hash", "strategy_governance_decisions", ["evidence_hash"])
    op.create_index("ix_strategy_governance_decisions_actor_user_id", "strategy_governance_decisions", ["actor_user_id"])
    op.create_index("ix_strategy_governance_decisions_request_hash", "strategy_governance_decisions", ["request_hash"])

    with op.batch_alter_table("model_registry") as batch:
        batch.add_column(sa.Column("simulation_run_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("governance_record_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("governance_decision_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("evidence_hash", sa.String(128), nullable=True))
        batch.add_column(sa.Column("evidence_level", sa.String(16), nullable=True))
        batch.create_foreign_key("fk_model_registry_simulation_run", "simulation_runs", ["simulation_run_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_model_registry_governance_record", "strategy_governance_records", ["governance_record_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_model_registry_governance_decision", "strategy_governance_decisions", ["governance_decision_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_model_registry_simulation_run_id", ["simulation_run_id"])
        batch.create_index("ix_model_registry_governance_record_id", ["governance_record_id"])
        batch.create_index("ix_model_registry_governance_decision_id", ["governance_decision_id"])
        batch.create_index("ix_model_registry_evidence_hash", ["evidence_hash"])
        batch.create_index("ix_model_registry_evidence_level", ["evidence_level"])
    op.execute("UPDATE model_registry SET evidence_level = 'LEGACY' WHERE evidence_level IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("model_registry") as batch:
        batch.drop_index("ix_model_registry_evidence_level")
        batch.drop_index("ix_model_registry_evidence_hash")
        batch.drop_index("ix_model_registry_governance_decision_id")
        batch.drop_index("ix_model_registry_governance_record_id")
        batch.drop_index("ix_model_registry_simulation_run_id")
        batch.drop_constraint("fk_model_registry_governance_decision", type_="foreignkey")
        batch.drop_constraint("fk_model_registry_governance_record", type_="foreignkey")
        batch.drop_constraint("fk_model_registry_simulation_run", type_="foreignkey")
        batch.drop_column("evidence_level")
        batch.drop_column("evidence_hash")
        batch.drop_column("governance_decision_id")
        batch.drop_column("governance_record_id")
        batch.drop_column("simulation_run_id")
    op.drop_table("strategy_governance_decisions")
    op.drop_table("strategy_governance_records")
