"""Record budget-owner decisions for receivables pilot evaluation.

Revision ID: 0007_receivables_pilot_decisions
Revises: 0006_receivables_assurance
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_receivables_pilot_decisions"
down_revision = "0006_receivables_assurance"
branch_labels = None
depends_on = None


def upgrade():
    uuid_type = sa.Uuid()
    op.create_table(
        "receivables_pilot_decisions",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("organization_id", uuid_type, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", uuid_type, nullable=False),
        sa.Column("recorded_by", uuid_type, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("budget_owner_name", sa.String(180), nullable=False),
        sa.Column("budget_owner_title", sa.String(120), nullable=False, server_default=""),
        sa.Column("budget_owner_organization", sa.String(180), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("decision_source", sa.String(32), nullable=False),
        sa.Column("price_amount", sa.Numeric(16, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="KES"),
        sa.Column("price_unit", sa.String(120), nullable=False, server_default=""),
        sa.Column("decision_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("next_step", sa.String(500), nullable=False, server_default=""),
        sa.Column("evidence_artifact_id", uuid_type, nullable=True),
        sa.Column("decided_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["case_id", "organization_id"], ["receivable_cases.id", "receivable_cases.organization_id"], name="fk_receivables_pilot_decision_case_org"),
        sa.ForeignKeyConstraint(["evidence_artifact_id", "organization_id"], ["evidence_artifacts.id", "evidence_artifacts.organization_id"], name="fk_receivables_pilot_decision_artifact_org"),
        sa.CheckConstraint("decision IN ('approved_paid_repeat', 'conditional_paid_repeat', 'declined', 'not_decided')", name="ck_receivables_pilot_decision_status"),
        sa.CheckConstraint("decision_source IN ('direct_statement', 'email', 'meeting_notes', 'other')", name="ck_receivables_pilot_decision_source"),
        sa.CheckConstraint("price_amount IS NULL OR price_amount >= 0", name="ck_receivables_pilot_decision_price_nonnegative"),
        sa.CheckConstraint("decision <> 'approved_paid_repeat' OR (price_amount IS NOT NULL AND price_unit <> '' AND evidence_artifact_id IS NOT NULL)", name="ck_receivables_pilot_decision_approved_requires_price_evidence"),
    )
    op.create_index("ix_receivables_pilot_decisions_organization_id", "receivables_pilot_decisions", ["organization_id"])
    op.create_index("ix_receivables_pilot_decisions_case_time", "receivables_pilot_decisions", ["case_id", "created_at"])


def downgrade():
    op.drop_index("ix_receivables_pilot_decisions_case_time", table_name="receivables_pilot_decisions")
    op.drop_index("ix_receivables_pilot_decisions_organization_id", table_name="receivables_pilot_decisions")
    op.drop_table("receivables_pilot_decisions")
