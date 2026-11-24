"""Add conservative, policy-reviewed evidence retention metadata.

Revision ID: 0017_evidence_retention_controls
Revises: 0016_counterparty_line_reconciliation
"""
from alembic import op
import sqlalchemy as sa


revision = "0017_evidence_retention_controls"
down_revision = "0016_counterparty_line_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("evidence_artifacts") as batch_op:
            batch_op.add_column(sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.true()))
            batch_op.add_column(sa.Column("retention_basis", sa.String(length=32), nullable=False, server_default="unreviewed"))
            batch_op.add_column(sa.Column("retention_reviewed_at", sa.DateTime(timezone=True), nullable=True))
            batch_op.create_check_constraint(
                "ck_evidence_artifact_retention_basis",
                "retention_basis IN ('unreviewed', 'contract', 'legal', 'tax', 'consent', 'operational')",
            )
    else:
        op.add_column("evidence_artifacts", sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.true()))
        op.add_column("evidence_artifacts", sa.Column("retention_basis", sa.String(length=32), nullable=False, server_default="unreviewed"))
        op.add_column("evidence_artifacts", sa.Column("retention_reviewed_at", sa.DateTime(timezone=True), nullable=True))
        op.create_check_constraint(
            "ck_evidence_artifact_retention_basis", "evidence_artifacts",
            "retention_basis IN ('unreviewed', 'contract', 'legal', 'tax', 'consent', 'operational')",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("evidence_artifacts") as batch_op:
            batch_op.drop_constraint("ck_evidence_artifact_retention_basis", type_="check")
            batch_op.drop_column("retention_reviewed_at")
            batch_op.drop_column("retention_basis")
            batch_op.drop_column("legal_hold")
    else:
        op.drop_constraint("ck_evidence_artifact_retention_basis", "evidence_artifacts", type_="check")
        op.drop_column("evidence_artifacts", "retention_reviewed_at")
        op.drop_column("evidence_artifacts", "retention_basis")
        op.drop_column("evidence_artifacts", "legal_hold")
