"""Cooperative intake reconciliation and review loop.

Revision ID: 0002_cooperative_reconciliation
Revises: 0001_initial
"""
from alembic import op
from app.models import ReconciliationItem, ReconciliationRun

revision = "0002_cooperative_reconciliation"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # checkfirst supports databases that already created current metadata before
    # Alembic was introduced, while fresh installs apply these after revision 0001.
    ReconciliationRun.__table__.create(bind=bind, checkfirst=True)
    ReconciliationItem.__table__.create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    ReconciliationItem.__table__.drop(bind=bind, checkfirst=True)
    ReconciliationRun.__table__.drop(bind=bind, checkfirst=True)
