"""Add immutable, tenant-scoped messaging to veterinarian contact requests.

Revision ID: 0012_veterinary_contact_messages
Revises: 0011_veterinary_contact_requests
"""
from alembic import op
import sqlalchemy as sa


revision = "0012_veterinary_contact_messages"
down_revision = "0011_veterinary_contact_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    op.create_table(
        "veterinary_contact_messages",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("request_id", sa.Uuid(), sa.ForeignKey("veterinary_contact_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("farm_id", sa.Uuid(), sa.ForeignKey("farms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("farm_domain_events.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sender_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source_channel", sa.String(20), nullable=False, server_default="in_app"),
        sa.Column("external_message_id", sa.String(180), nullable=True, unique=True),
        sa.Column("idempotency_key", sa.String(180), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(body)) BETWEEN 1 AND 4000", name="ck_vet_contact_message_body"),
        sa.CheckConstraint("source_channel IN ('in_app', 'whatsapp')", name="ck_vet_contact_message_channel"),
    )
    op.create_index("ix_veterinary_contact_messages_request_id", "veterinary_contact_messages", ["request_id"])
    op.create_index("ix_veterinary_contact_messages_farm_id", "veterinary_contact_messages", ["farm_id"])
    op.create_index("ix_veterinary_contact_messages_sender_user_id", "veterinary_contact_messages", ["sender_user_id"])
    op.create_index("ix_vet_contact_messages_request_created", "veterinary_contact_messages", ["request_id", "created_at"])

    if dialect != "postgresql":
        return

    op.execute("REVOKE ALL ON TABLE public.veterinary_contact_messages FROM PUBLIC, terravanta_app")
    op.execute("GRANT SELECT, INSERT ON TABLE public.veterinary_contact_messages TO terravanta_app")
    op.execute("ALTER TABLE public.veterinary_contact_messages ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.veterinary_contact_messages FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY terravanta_vet_contact_messages_select
        ON public.veterinary_contact_messages FOR SELECT TO terravanta_app
        USING (
            terravanta_private.can_read_farm(farm_id)
            AND EXISTS (
                SELECT 1 FROM public.veterinary_contact_requests r
                WHERE r.id = veterinary_contact_messages.request_id
                  AND r.farm_id = veterinary_contact_messages.farm_id
                  AND (
                      r.requester_user_id = terravanta_private.current_user_id()
                      OR r.veterinarian_user_id = terravanta_private.current_user_id()
                      OR (
                          r.status = 'pending'
                          AND EXISTS (
                              SELECT 1 FROM public.farm_members fm
                              WHERE fm.farm_id = r.farm_id
                                AND fm.user_id = terravanta_private.current_user_id()
                                AND fm.role = 'veterinarian'
                          )
                      )
                  )
            )
        )
    """)
    op.execute("""
        CREATE POLICY terravanta_vet_contact_messages_insert
        ON public.veterinary_contact_messages FOR INSERT TO terravanta_app
        WITH CHECK (
            source_channel = 'in_app'
            AND sender_user_id = terravanta_private.current_user_id()
            AND terravanta_private.can_write_health_farm(farm_id)
            AND EXISTS (
                SELECT 1 FROM public.veterinary_contact_requests r
                WHERE r.id = veterinary_contact_messages.request_id
                  AND r.farm_id = veterinary_contact_messages.farm_id
                  AND (
                      (r.requester_user_id = terravanta_private.current_user_id()
                       AND r.status IN ('pending', 'accepted', 'contacted'))
                      OR
                      (r.veterinarian_user_id = terravanta_private.current_user_id()
                       AND r.status IN ('accepted', 'contacted')
                       AND EXISTS (
                           SELECT 1 FROM public.farm_members fm
                           WHERE fm.farm_id = r.farm_id
                             AND fm.user_id = terravanta_private.current_user_id()
                             AND fm.role = 'veterinarian'
                       ))
                  )
            )
            AND EXISTS (
                SELECT 1 FROM public.farm_domain_events e
                WHERE e.id = veterinary_contact_messages.event_id
                  AND e.farm_id = veterinary_contact_messages.farm_id
                  AND e.aggregate_type = 'veterinary_contact_request'
                  AND e.aggregate_id = veterinary_contact_messages.request_id
            )
        )
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS terravanta_vet_contact_messages_insert ON public.veterinary_contact_messages")
        op.execute("DROP POLICY IF EXISTS terravanta_vet_contact_messages_select ON public.veterinary_contact_messages")
    for name in (
        "ix_vet_contact_messages_request_created",
        "ix_veterinary_contact_messages_sender_user_id",
        "ix_veterinary_contact_messages_farm_id",
        "ix_veterinary_contact_messages_request_id",
    ):
        op.drop_index(name, table_name="veterinary_contact_messages")
    op.drop_table("veterinary_contact_messages")
