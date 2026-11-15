"""Store individually issued, hashed pilot access codes.

Revision ID: 0003_temporary_access_codes
Revises: 0002_cooperative_reconciliation
"""
from alembic import op
from app.models import AccessCode

revision = "0003_temporary_access_codes"
down_revision = "0002_cooperative_reconciliation"
branch_labels = None
depends_on = None


def upgrade():
    AccessCode.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    AccessCode.__table__.drop(bind=op.get_bind(), checkfirst=True)
