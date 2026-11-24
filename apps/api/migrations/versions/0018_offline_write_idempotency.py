"""Persist idempotent create responses for offline write replay.

Revision ID: 0018_offline_write_idempotency
Revises: 0017_evidence_retention_controls
"""
from alembic import op
import sqlalchemy as sa


revision = "0018_offline_write_idempotency"
down_revision = "0017_evidence_retention_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_write_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("actor_user_id", "idempotency_key", name="uq_client_write_receipt_user_key"),
        sa.CheckConstraint("length(request_hash) = 64", name="ck_client_write_receipt_hash_length"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("REVOKE ALL ON TABLE public.client_write_receipts FROM PUBLIC")
        op.execute("GRANT SELECT, INSERT ON TABLE public.client_write_receipts TO terravanta_app")
        op.execute("ALTER TABLE public.client_write_receipts ENABLE ROW LEVEL SECURITY")
        op.execute("""
            CREATE POLICY terravanta_client_write_receipts_select
                ON public.client_write_receipts FOR SELECT TO terravanta_app
                USING (actor_user_id = terravanta_private.current_user_id());
            CREATE POLICY terravanta_client_write_receipts_insert
                ON public.client_write_receipts FOR INSERT TO terravanta_app
                WITH CHECK (actor_user_id = terravanta_private.current_user_id());
        """)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS terravanta_client_write_receipts_insert ON public.client_write_receipts")
        op.execute("DROP POLICY IF EXISTS terravanta_client_write_receipts_select ON public.client_write_receipts")
        op.execute("REVOKE ALL ON TABLE public.client_write_receipts FROM terravanta_app")
    op.drop_table("client_write_receipts")
