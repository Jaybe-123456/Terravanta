"""Initial normalized Terravanta schema.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
from sqlalchemy import inspect
from app.db import Base
from app import models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    # Keep this first revision stable as a historical schema baseline. New
    # tables belong in follow-on revisions rather than being backfilled here.
    initial_tables = [
        table for table in Base.metadata.sorted_tables
        if table.name not in {"reconciliation_runs", "reconciliation_items", "settlement_closes", "settlement_close_items"}
    ]
    Base.metadata.create_all(bind=bind, tables=initial_tables)
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE farms ADD COLUMN IF NOT EXISTS location geometry(Point, 4326)")
        op.execute("UPDATE farms SET location = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) WHERE latitude IS NOT NULL AND longitude IS NOT NULL")
        op.execute("CREATE INDEX IF NOT EXISTS ix_farms_location_gist ON farms USING GIST (location)")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and "farms" in inspect(bind).get_table_names():
        op.execute("DROP INDEX IF EXISTS ix_farms_location_gist")
        op.execute("ALTER TABLE farms DROP COLUMN IF EXISTS location")
    Base.metadata.drop_all(bind=bind)
