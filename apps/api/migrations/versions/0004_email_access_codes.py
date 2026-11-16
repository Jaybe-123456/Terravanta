"""Track email OTP type and verification attempts.

Revision ID: 0004_email_access_codes
Revises: 0003_temporary_access_codes
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_email_access_codes"
down_revision = "0003_temporary_access_codes"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("access_codes")}
    if "code_type" not in columns:
        op.add_column("access_codes", sa.Column("code_type", sa.String(length=20), nullable=False, server_default="invite"))
    if "attempt_count" not in columns:
        op.add_column("access_codes", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    indexes = {index["name"] for index in inspector.get_indexes("access_codes")}
    if "ix_access_codes_code_type" not in indexes:
        op.create_index("ix_access_codes_code_type", "access_codes", ["code_type"])


def downgrade():
    op.drop_index("ix_access_codes_code_type", table_name="access_codes")
    op.drop_column("access_codes", "attempt_count")
    op.drop_column("access_codes", "code_type")
