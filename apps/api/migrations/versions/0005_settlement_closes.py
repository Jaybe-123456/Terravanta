"""Create audit-friendly cooperative settlement close tables.

Revision ID: 0005_settlement_closes
Revises: 0004_email_access_codes
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_settlement_closes"
down_revision = "0004_email_access_codes"
branch_labels = None
depends_on = None


def upgrade():
    uuid_type = sa.Uuid()
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
    op.create_table(
        "settlement_closes",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("organization_id", uuid_type, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", uuid_type, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", uuid_type, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("collection_filename", sa.String(255), nullable=False),
        sa.Column("processor_filename", sa.String(255), nullable=False),
        sa.Column("payout_filename", sa.String(255), nullable=False),
        sa.Column("collection_sha256", sa.String(64), nullable=False),
        sa.Column("processor_sha256", sa.String(64), nullable=False),
        sa.Column("payout_sha256", sa.String(64), nullable=False),
        sa.Column("collection_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processor_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payout_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="review_required"),
        sa.Column("approval_note", sa.String(500), nullable=False, server_default=""),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "source_fingerprint", name="uq_settlement_org_fingerprint"),
    )
    op.create_index("ix_settlement_closes_organization_id", "settlement_closes", ["organization_id"])
    op.create_index("ix_settlement_closes_status", "settlement_closes", ["status"])
    op.create_table(
        "settlement_close_items",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("close_id", uuid_type, sa.ForeignKey("settlement_closes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_code", sa.String(80), nullable=False),
        sa.Column("collection_liters", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("processor_liters", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("volume_variance_liters", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("gross_amount_kes", sa.Numeric(16, 2), nullable=False, server_default="0"),
        sa.Column("deductions_kes", sa.Numeric(16, 2), nullable=False, server_default="0"),
        sa.Column("net_amount_kes", sa.Numeric(16, 2), nullable=False, server_default="0"),
        sa.Column("payout_amount_kes", sa.Numeric(16, 2), nullable=False, server_default="0"),
        sa.Column("processor_arithmetic_variance_kes", sa.Numeric(16, 2), nullable=False, server_default="0"),
        sa.Column("payout_variance_kes", sa.Numeric(16, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("issues", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("source_rows", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("source_references", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("review_status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("reviewer_id", uuid_type, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("close_id", "member_code", name="uq_settlement_member_per_close"),
    )
    op.create_index("ix_settlement_close_items_close_id", "settlement_close_items", ["close_id"])
    op.create_index("ix_settlement_close_items_member_code", "settlement_close_items", ["member_code"])
    op.create_index("ix_settlement_close_items_status", "settlement_close_items", ["status"])
    op.create_index("ix_settlement_close_items_review_status", "settlement_close_items", ["review_status"])


def downgrade():
    op.drop_index("ix_settlement_close_items_review_status", table_name="settlement_close_items")
    op.drop_index("ix_settlement_close_items_status", table_name="settlement_close_items")
    op.drop_index("ix_settlement_close_items_member_code", table_name="settlement_close_items")
    op.drop_index("ix_settlement_close_items_close_id", table_name="settlement_close_items")
    op.drop_table("settlement_close_items")
    op.drop_index("ix_settlement_closes_status", table_name="settlement_closes")
    op.drop_index("ix_settlement_closes_organization_id", table_name="settlement_closes")
    op.drop_table("settlement_closes")
