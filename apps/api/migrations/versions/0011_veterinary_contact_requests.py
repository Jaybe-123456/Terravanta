"""Add an auditable farmer-to-veterinarian contact request queue.

Revision ID: 0011_veterinary_contact_requests
Revises: 0010_farm_event_workflows
"""
from alembic import op
import sqlalchemy as sa


revision = "0011_veterinary_contact_requests"
down_revision = "0010_farm_event_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    op.create_table(
        "veterinary_contact_requests",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("farm_id", sa.Uuid(), sa.ForeignKey("farms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("animal_id", sa.Uuid(), sa.ForeignKey("animals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("requester_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("veterinarian_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("urgency", sa.String(20), nullable=False, server_default="routine"),
        sa.Column("preferred_contact_method", sa.String(20), nullable=False, server_default="phone_call"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("urgency IN ('routine', 'urgent', 'emergency')", name="ck_vet_contact_urgency"),
        sa.CheckConstraint("preferred_contact_method IN ('phone_call', 'whatsapp', 'in_app')", name="ck_vet_contact_method"),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'declined', 'contacted', 'cancelled')", name="ck_vet_contact_status"),
    )
    op.create_index("ix_veterinary_contact_requests_farm_id", "veterinary_contact_requests", ["farm_id"])
    op.create_index("ix_veterinary_contact_requests_animal_id", "veterinary_contact_requests", ["animal_id"])
    op.create_index("ix_veterinary_contact_requests_status", "veterinary_contact_requests", ["status"])
    op.create_index("ix_vet_contact_farm_status_created", "veterinary_contact_requests", ["farm_id", "status", "created_at"])
    op.create_index("ix_vet_contact_vet_status_created", "veterinary_contact_requests", ["veterinarian_user_id", "status", "created_at"])

    if dialect != "postgresql":
        return

    op.execute("REVOKE ALL ON TABLE public.veterinary_contact_requests FROM PUBLIC, terravanta_app")
    op.execute("GRANT SELECT, INSERT ON TABLE public.veterinary_contact_requests TO terravanta_app")
    op.execute("GRANT UPDATE (status, veterinarian_user_id, responded_at, updated_at) ON TABLE public.veterinary_contact_requests TO terravanta_app")
    op.execute("GRANT INSERT ON TABLE public.notifications TO terravanta_app")
    op.execute("ALTER TABLE public.veterinary_contact_requests ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY terravanta_vet_contact_select
        ON public.veterinary_contact_requests FOR SELECT TO terravanta_app
        USING (
            terravanta_private.can_read_farm(farm_id)
            AND (
                requester_user_id = terravanta_private.current_user_id()
                OR veterinarian_user_id = terravanta_private.current_user_id()
                OR (
                    status = 'pending'
                    AND EXISTS (
                        SELECT 1 FROM public.farm_members fm
                        WHERE fm.farm_id = veterinary_contact_requests.farm_id
                          AND fm.user_id = terravanta_private.current_user_id()
                          AND fm.role = 'veterinarian'
                    )
                )
            )
        )
    """)
    op.execute("""
        CREATE POLICY terravanta_vet_contact_insert
        ON public.veterinary_contact_requests FOR INSERT TO terravanta_app
        WITH CHECK (
            terravanta_private.can_write_farm(farm_id)
            AND requester_user_id = terravanta_private.current_user_id()
            AND veterinarian_user_id IS NULL
            AND status = 'pending'
            AND EXISTS (
                SELECT 1 FROM public.farm_members fm
                WHERE fm.farm_id = veterinary_contact_requests.farm_id
                  AND fm.role = 'veterinarian'
            )
        )
    """)
    op.execute("""
        CREATE POLICY terravanta_vet_contact_update
        ON public.veterinary_contact_requests FOR UPDATE TO terravanta_app
        USING (
            (requester_user_id = terravanta_private.current_user_id() AND status = 'pending')
            OR (
                status IN ('pending', 'accepted')
                AND EXISTS (
                    SELECT 1 FROM public.farm_members fm
                    WHERE fm.farm_id = veterinary_contact_requests.farm_id
                      AND fm.user_id = terravanta_private.current_user_id()
                      AND fm.role = 'veterinarian'
                )
                AND (veterinarian_user_id IS NULL OR veterinarian_user_id = terravanta_private.current_user_id())
            )
        )
        WITH CHECK (
            (requester_user_id = terravanta_private.current_user_id() AND status = 'cancelled' AND veterinarian_user_id IS NULL)
            OR (
                veterinarian_user_id = terravanta_private.current_user_id()
                AND status IN ('accepted', 'declined', 'contacted')
                AND EXISTS (
                    SELECT 1 FROM public.farm_members fm
                    WHERE fm.farm_id = veterinary_contact_requests.farm_id
                      AND fm.user_id = terravanta_private.current_user_id()
                      AND fm.role = 'veterinarian'
                )
            )
        )
    """)
    op.execute("""
        CREATE POLICY terravanta_notifications_insert_farm_member
        ON public.notifications FOR INSERT TO terravanta_app
        WITH CHECK (
            terravanta_private.can_write_health_farm(farm_id)
            AND EXISTS (
                SELECT 1 FROM public.farm_members fm
                WHERE fm.farm_id = notifications.farm_id
                  AND fm.user_id = notifications.recipient_user_id
            )
            AND EXISTS (
                SELECT 1 FROM public.farm_domain_events e
                WHERE e.id = notifications.event_id AND e.farm_id = notifications.farm_id
            )
        )
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION terravanta_private.enforce_vet_contact_transition()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_actor uuid := terravanta_private.current_user_id();
            v_is_veterinarian boolean;
        BEGIN
            IF NEW.farm_id IS DISTINCT FROM OLD.farm_id
               OR NEW.animal_id IS DISTINCT FROM OLD.animal_id
               OR NEW.requester_user_id IS DISTINCT FROM OLD.requester_user_id
               OR NEW.message IS DISTINCT FROM OLD.message
               OR NEW.urgency IS DISTINCT FROM OLD.urgency
               OR NEW.preferred_contact_method IS DISTINCT FROM OLD.preferred_contact_method
               OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'contact request facts are immutable';
            END IF;

            SELECT EXISTS (
                SELECT 1 FROM public.farm_members fm
                WHERE fm.farm_id = OLD.farm_id
                  AND fm.user_id = v_actor
                  AND fm.role = 'veterinarian'
            ) INTO v_is_veterinarian;

            IF OLD.status = 'pending' AND v_actor = OLD.requester_user_id
               AND NEW.status = 'cancelled' AND NEW.veterinarian_user_id IS NULL THEN
                NEW.updated_at := now();
                NEW.responded_at := NULL;
                RETURN NEW;
            END IF;

            IF OLD.status = 'pending' AND v_is_veterinarian
               AND NEW.veterinarian_user_id = v_actor
               AND NEW.status IN ('accepted', 'declined') THEN
                NEW.updated_at := now();
                NEW.responded_at := now();
                RETURN NEW;
            END IF;

            IF OLD.status = 'accepted' AND OLD.veterinarian_user_id = v_actor
               AND NEW.veterinarian_user_id = v_actor AND NEW.status = 'contacted' THEN
                NEW.updated_at := now();
                NEW.responded_at := now();
                RETURN NEW;
            END IF;

            RAISE EXCEPTION 'invalid veterinary contact request transition';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER veterinary_contact_request_transition
        BEFORE UPDATE ON public.veterinary_contact_requests
        FOR EACH ROW EXECUTE FUNCTION terravanta_private.enforce_vet_contact_transition()
    """)
    op.execute("REVOKE ALL ON FUNCTION terravanta_private.enforce_vet_contact_transition() FROM PUBLIC")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS veterinary_contact_request_transition ON public.veterinary_contact_requests")
        op.execute("DROP FUNCTION IF EXISTS terravanta_private.enforce_vet_contact_transition()")
        op.execute("DROP POLICY IF EXISTS terravanta_notifications_insert_farm_member ON public.notifications")
        op.execute("DROP POLICY IF EXISTS terravanta_vet_contact_update ON public.veterinary_contact_requests")
        op.execute("DROP POLICY IF EXISTS terravanta_vet_contact_insert ON public.veterinary_contact_requests")
        op.execute("DROP POLICY IF EXISTS terravanta_vet_contact_select ON public.veterinary_contact_requests")
        op.execute("REVOKE INSERT ON TABLE public.notifications FROM terravanta_app")
    for index in (
        "ix_vet_contact_vet_status_created", "ix_vet_contact_farm_status_created",
        "ix_veterinary_contact_requests_status", "ix_veterinary_contact_requests_animal_id",
        "ix_veterinary_contact_requests_farm_id",
    ):
        op.drop_index(index, table_name="veterinary_contact_requests")
    op.drop_table("veterinary_contact_requests")
