"""Add opt-in phone linking, a durable WhatsApp outbox and webhook receipts.

Revision ID: 0013_whatsapp_delivery_safety
Revises: 0012_veterinary_contact_messages
"""
from alembic import op
import sqlalchemy as sa


revision = "0013_whatsapp_delivery_safety"
down_revision = "0012_veterinary_contact_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    op.add_column("veterinary_contact_requests", sa.Column("conversation_code", sa.String(12), nullable=True))
    if dialect == "postgresql":
        op.execute("UPDATE public.veterinary_contact_requests SET conversation_code = upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 12)) WHERE conversation_code IS NULL")
    else:
        op.execute("UPDATE veterinary_contact_requests SET conversation_code = upper(substr(hex(randomblob(6)), 1, 12)) WHERE conversation_code IS NULL")
    op.alter_column("veterinary_contact_requests", "conversation_code", nullable=False)
    op.create_index("ix_vet_contact_request_conversation_code", "veterinary_contact_requests", ["conversation_code"], unique=True)

    op.create_table(
        "whatsapp_preferences",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("phone_e164", sa.String(20), nullable=True, unique=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_version", sa.String(40), nullable=False, server_default=""),
        sa.Column("consent_source", sa.String(80), nullable=False, server_default=""),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "phone_e164 IS NULL OR (verified_at IS NOT NULL AND consent_granted_at IS NOT NULL)",
            name="ck_whatsapp_preference_verified_consent",
        ),
    )

    op.create_table(
        "whatsapp_link_challenges",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("consent_version", sa.String(40), nullable=False),
        sa.Column("consent_accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_whatsapp_link_challenges_user_id", "whatsapp_link_challenges", ["user_id"])
    op.create_index("ix_whatsapp_link_challenges_expires_at", "whatsapp_link_challenges", ["expires_at"])
    op.create_index("ix_whatsapp_pairing_user_created", "whatsapp_link_challenges", ["user_id", "created_at"])

    op.create_table(
        "communication_outbox",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("farm_id", sa.Uuid(), sa.ForeignKey("farms.id", ondelete="CASCADE"), nullable=True),
        sa.Column("request_id", sa.Uuid(), sa.ForeignKey("veterinary_contact_requests.id", ondelete="CASCADE"), nullable=True),
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("veterinary_contact_messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("conversation_code", sa.String(12), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(180), nullable=True, unique=True),
        sa.Column("last_error_code", sa.String(80), nullable=False, server_default=""),
        sa.Column("idempotency_key", sa.String(220), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('queued', 'sending', 'sent', 'delivered', 'read', 'failed', 'cancelled', 'blocked')", name="ck_communication_outbox_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_communication_outbox_attempts"),
    )
    op.create_index("ix_communication_outbox_recipient_user_id", "communication_outbox", ["recipient_user_id"])
    op.create_index("ix_communication_outbox_farm_id", "communication_outbox", ["farm_id"])
    op.create_index("ix_communication_outbox_request_id", "communication_outbox", ["request_id"])
    op.create_index("ix_communication_outbox_message_id", "communication_outbox", ["message_id"])
    op.create_index("ix_communication_outbox_status", "communication_outbox", ["status"])
    op.create_index("ix_communication_outbox_next_attempt_at", "communication_outbox", ["next_attempt_at"])
    op.create_index("ix_communication_outbox_ready", "communication_outbox", ["status", "next_attempt_at"])
    op.create_index("ix_communication_outbox_created_at", "communication_outbox", ["created_at"])

    op.create_table(
        "meta_webhook_events",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("provider_event_id", sa.String(220), nullable=False, unique=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("processing_status", sa.String(20), nullable=False, server_default="received"),
        sa.Column("safe_error_code", sa.String(80), nullable=False, server_default=""),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("processing_status IN ('received', 'processed', 'ignored', 'failed')", name="ck_meta_webhook_event_status"),
    )
    op.create_index("ix_meta_webhook_events_received_at", "meta_webhook_events", ["received_at"])

    if dialect != "postgresql":
        return

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'terravanta_worker') THEN
                CREATE ROLE terravanta_worker NOLOGIN INHERIT NOBYPASSRLS;
            END IF;
            IF EXISTS (
                SELECT 1 FROM pg_roles
                WHERE rolname = 'terravanta_worker'
                  AND (rolcanlogin OR rolbypassrls OR NOT rolinherit)
            ) THEN
                RAISE EXCEPTION 'terravanta_worker must be NOLOGIN INHERIT NOBYPASSRLS';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'terravanta_webhook') THEN
                CREATE ROLE terravanta_webhook NOLOGIN INHERIT NOBYPASSRLS;
            END IF;
            IF EXISTS (
                SELECT 1 FROM pg_roles
                WHERE rolname = 'terravanta_webhook'
                  AND (rolcanlogin OR rolbypassrls OR NOT rolinherit)
            ) THEN
                RAISE EXCEPTION 'terravanta_webhook must be NOLOGIN INHERIT NOBYPASSRLS';
            END IF;
            IF pg_has_role('terravanta_webhook', 'terravanta_app', 'MEMBER') THEN
                RAISE EXCEPTION 'terravanta_webhook must not inherit the application role';
            END IF;
        END $$;
        GRANT terravanta_app TO terravanta_worker;
        GRANT USAGE ON SCHEMA public TO terravanta_webhook;
    """)

    op.execute("REVOKE ALL ON TABLE public.whatsapp_preferences, public.whatsapp_link_challenges, public.communication_outbox, public.meta_webhook_events FROM PUBLIC, terravanta_app")
    op.execute("GRANT SELECT ON TABLE public.whatsapp_preferences TO terravanta_app")
    op.execute("GRANT SELECT, INSERT ON TABLE public.whatsapp_link_challenges TO terravanta_app")
    op.execute("GRANT SELECT ON TABLE public.communication_outbox TO terravanta_app")
    op.execute("ALTER TABLE public.whatsapp_preferences ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.whatsapp_preferences NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.whatsapp_link_challenges ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.whatsapp_link_challenges NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.communication_outbox ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.communication_outbox NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.meta_webhook_events ENABLE ROW LEVEL SECURITY")
    # Signed Meta ingress uses a dedicated NOLOGIN group role and a separate
    # login. It never uses the migration owner connection.
    op.execute("""
        GRANT SELECT, INSERT, UPDATE ON TABLE public.whatsapp_preferences TO terravanta_webhook;
        GRANT SELECT ON TABLE public.whatsapp_link_challenges TO terravanta_webhook;
        GRANT UPDATE (consumed_at) ON TABLE public.whatsapp_link_challenges TO terravanta_webhook;
        GRANT INSERT ON TABLE public.veterinary_contact_messages, public.farm_domain_events,
            public.notifications, public.audit_logs TO terravanta_webhook;
        GRANT SELECT (id, conversation_code, requester_user_id, veterinarian_user_id, farm_id, status, urgency)
            ON TABLE public.veterinary_contact_requests TO terravanta_webhook;
        GRANT SELECT (farm_id, user_id, role) ON TABLE public.farm_members TO terravanta_webhook;
        GRANT INSERT ON TABLE public.communication_outbox TO terravanta_webhook;
        GRANT SELECT (id, provider_message_id, status), UPDATE (status, last_error_code, updated_at)
            ON TABLE public.communication_outbox TO terravanta_webhook;
        GRANT SELECT, INSERT, UPDATE ON TABLE public.meta_webhook_events TO terravanta_webhook;
    """)
    op.execute("""
        CREATE POLICY terravanta_whatsapp_preferences_select
        ON public.whatsapp_preferences FOR SELECT TO terravanta_app
        USING (user_id = terravanta_private.current_user_id())
    """)
    op.execute("""
        CREATE POLICY terravanta_whatsapp_challenges_select
        ON public.whatsapp_link_challenges FOR SELECT TO terravanta_app
        USING (user_id = terravanta_private.current_user_id())
    """)
    op.execute("""
        CREATE POLICY terravanta_whatsapp_challenges_insert
        ON public.whatsapp_link_challenges FOR INSERT TO terravanta_app
        WITH CHECK (user_id = terravanta_private.current_user_id())
    """)
    op.execute("""
        CREATE POLICY terravanta_communication_outbox_select
        ON public.communication_outbox FOR SELECT TO terravanta_app
        USING (recipient_user_id = terravanta_private.current_user_id())
    """)

    # These permissive policies apply only to the separate Meta webhook role.
    # SQL grants further restrict that role to the channel tables/columns above.
    for table, action in (
        ("whatsapp_preferences", "ALL"),
        ("whatsapp_link_challenges", "SELECT"),
        ("whatsapp_link_challenges", "UPDATE"),
        ("communication_outbox", "SELECT"),
        ("communication_outbox", "INSERT"),
        ("communication_outbox", "UPDATE"),
        ("meta_webhook_events", "ALL"),
        ("veterinary_contact_requests", "SELECT"),
        ("farm_members", "SELECT"),
        ("farm_domain_events", "INSERT"),
        ("veterinary_contact_messages", "INSERT"),
        ("notifications", "INSERT"),
        ("audit_logs", "INSERT"),
    ):
        policy_name = f"terravanta_webhook_{table}_{action.lower()}"
        if action == "ALL":
            op.execute(f'CREATE POLICY "{policy_name}" ON public.{table} FOR ALL TO terravanta_webhook USING (true) WITH CHECK (true)')
        elif action == "INSERT":
            op.execute(f'CREATE POLICY "{policy_name}" ON public.{table} FOR INSERT TO terravanta_webhook WITH CHECK (true)')
        elif action == "UPDATE":
            op.execute(f'CREATE POLICY "{policy_name}" ON public.{table} FOR UPDATE TO terravanta_webhook USING (true) WITH CHECK (true)')
        else:
            op.execute(f'CREATE POLICY "{policy_name}" ON public.{table} FOR SELECT TO terravanta_webhook USING (true)')

    op.execute("""
        CREATE OR REPLACE FUNCTION terravanta_private.enqueue_whatsapp_contact_message(p_message_id uuid)
        RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_message public.veterinary_contact_messages%ROWTYPE;
            v_request public.veterinary_contact_requests%ROWTYPE;
            v_recipient uuid;
            v_outbox_id uuid;
        BEGIN
            SELECT * INTO v_message FROM public.veterinary_contact_messages WHERE id = p_message_id;
            IF NOT FOUND THEN RETURN NULL; END IF;
            IF terravanta_private.current_user_id() IS DISTINCT FROM v_message.sender_user_id THEN
                RETURN NULL;
            END IF;
            SELECT * INTO v_request FROM public.veterinary_contact_requests WHERE id = v_message.request_id;
            IF NOT FOUND THEN RETURN NULL; END IF;

            IF v_message.sender_user_id = v_request.requester_user_id THEN
                v_recipient := v_request.veterinarian_user_id;
            ELSIF v_message.sender_user_id = v_request.veterinarian_user_id THEN
                v_recipient := v_request.requester_user_id;
            ELSE
                RETURN NULL;
            END IF;
            IF v_recipient IS NULL OR NOT EXISTS (
                SELECT 1 FROM public.whatsapp_preferences p
                WHERE p.user_id = v_recipient AND p.phone_e164 IS NOT NULL
                  AND p.verified_at IS NOT NULL AND p.consent_granted_at IS NOT NULL
                  AND p.consent_revoked_at IS NULL
            ) OR NOT EXISTS (
                SELECT 1 FROM public.whatsapp_preferences p
                WHERE p.user_id = v_message.sender_user_id AND p.phone_e164 IS NOT NULL
                  AND p.verified_at IS NOT NULL AND p.consent_granted_at IS NOT NULL
                  AND p.consent_revoked_at IS NULL
            ) THEN RETURN NULL; END IF;

            INSERT INTO public.communication_outbox (
                id, recipient_user_id, farm_id, request_id, message_id, body,
                conversation_code, status, attempts, next_attempt_at, idempotency_key
            ) VALUES (
                gen_random_uuid(), v_recipient, v_request.farm_id, v_request.id,
                v_message.id, v_message.body, v_request.conversation_code, 'queued', 0,
                now(), 'wa-contact-message:' || v_message.id::text || ':' || v_recipient::text
            ) ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id INTO v_outbox_id;

            IF v_outbox_id IS NULL THEN
                SELECT id INTO v_outbox_id FROM public.communication_outbox
                WHERE idempotency_key = 'wa-contact-message:' || v_message.id::text || ':' || v_recipient::text;
            END IF;
            RETURN v_outbox_id;
        END;
        $$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION terravanta_private.enqueue_whatsapp_contact_request(p_request_id uuid)
        RETURNS integer
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_request public.veterinary_contact_requests%ROWTYPE;
            v_count integer := 0;
        BEGIN
            SELECT * INTO v_request FROM public.veterinary_contact_requests WHERE id = p_request_id;
            IF NOT FOUND OR v_request.status <> 'pending'
               OR terravanta_private.current_user_id() IS DISTINCT FROM v_request.requester_user_id THEN
                RETURN 0;
            END IF;

            INSERT INTO public.communication_outbox (
                id, recipient_user_id, farm_id, request_id, body,
                conversation_code, status, attempts, next_attempt_at, idempotency_key
            )
            SELECT gen_random_uuid(), m.user_id, v_request.farm_id, v_request.id,
                   'A farmer requested veterinary contact. Open Terravanta to review the request.',
                   v_request.conversation_code, 'queued', 0, now(),
                   'wa-vet-contact-request:' || v_request.id::text || ':' || m.user_id::text
            FROM public.farm_members m
            JOIN public.whatsapp_preferences p ON p.user_id = m.user_id
            JOIN public.whatsapp_preferences requester_consent
              ON requester_consent.user_id = v_request.requester_user_id
            WHERE m.farm_id = v_request.farm_id AND m.role = 'veterinarian'
              AND (v_request.veterinarian_user_id IS NULL OR v_request.veterinarian_user_id = m.user_id)
              AND p.phone_e164 IS NOT NULL AND p.verified_at IS NOT NULL
              AND p.consent_granted_at IS NOT NULL AND p.consent_revoked_at IS NULL
              AND requester_consent.phone_e164 IS NOT NULL
              AND requester_consent.verified_at IS NOT NULL
              AND requester_consent.consent_granted_at IS NOT NULL
              AND requester_consent.consent_revoked_at IS NULL
            ON CONFLICT (idempotency_key) DO NOTHING;
            GET DIAGNOSTICS v_count = ROW_COUNT;
            RETURN v_count;
        END;
        $$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION terravanta_private.revoke_whatsapp_consent()
        RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE v_user_id uuid := terravanta_private.current_user_id();
        BEGIN
            IF v_user_id IS NULL THEN RETURN false; END IF;
            UPDATE public.whatsapp_link_challenges
            SET consumed_at = now()
            WHERE user_id = v_user_id AND consumed_at IS NULL;
            UPDATE public.whatsapp_preferences
            SET phone_e164 = NULL, verified_at = NULL, consent_revoked_at = now(), updated_at = now()
            WHERE user_id = v_user_id AND phone_e164 IS NOT NULL
              AND consent_granted_at IS NOT NULL AND consent_revoked_at IS NULL;
            IF NOT FOUND THEN RETURN false; END IF;
            UPDATE public.communication_outbox SET status = 'cancelled', locked_until = NULL,
                last_error_code = 'consent_revoked', updated_at = now()
            WHERE recipient_user_id = v_user_id AND status IN ('queued', 'sending');
            RETURN true;
        END;
        $$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION terravanta_private.claim_whatsapp_deliveries(p_limit integer DEFAULT 50)
        RETURNS TABLE(outbox_id uuid, destination_phone text, message_body text,
                      conversation_code text, in_service_window boolean, attempt_number integer)
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            UPDATE public.communication_outbox o
            SET status = 'cancelled', locked_until = NULL, last_error_code = 'consent_revoked', updated_at = now()
            WHERE o.status IN ('queued', 'sending')
              AND NOT EXISTS (
                  SELECT 1 FROM public.whatsapp_preferences p
                  WHERE p.user_id = o.recipient_user_id AND p.phone_e164 IS NOT NULL
                    AND p.verified_at IS NOT NULL AND p.consent_granted_at IS NOT NULL
                    AND p.consent_revoked_at IS NULL
              );

            RETURN QUERY
            WITH candidates AS (
                SELECT o.id, p.phone_e164, p.last_inbound_at, o.body, o.conversation_code
                FROM public.communication_outbox o
                JOIN public.whatsapp_preferences p ON p.user_id = o.recipient_user_id
                WHERE p.verified_at IS NOT NULL AND p.consent_granted_at IS NOT NULL
                  AND p.consent_revoked_at IS NULL AND p.phone_e164 IS NOT NULL
                  AND ((o.status = 'queued' AND o.next_attempt_at <= now())
                       OR (o.status = 'sending' AND o.locked_until <= now()))
                ORDER BY o.next_attempt_at, o.created_at
                FOR UPDATE OF o SKIP LOCKED
                LIMIT LEAST(GREATEST(COALESCE(p_limit, 50), 1), 200)
            ), claimed AS (
                UPDATE public.communication_outbox o
                SET status = 'sending', attempts = o.attempts + 1,
                    locked_until = now() + interval '3 minutes', updated_at = now()
                FROM candidates c WHERE o.id = c.id
                RETURNING o.id, o.recipient_user_id, o.body, o.conversation_code, o.attempts
            )
            SELECT c.id, p.phone_e164, c.body, c.conversation_code,
                   p.last_inbound_at IS NOT NULL AND p.last_inbound_at >= now() - interval '24 hours',
                   c.attempts
            FROM claimed c JOIN public.whatsapp_preferences p ON p.user_id = c.recipient_user_id;
        END;
        $$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION terravanta_private.finish_whatsapp_delivery(
            p_outbox_id uuid, p_result text, p_provider_message_id text DEFAULT NULL,
            p_error_code text DEFAULT '', p_retryable boolean DEFAULT false
        ) RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            IF p_result NOT IN ('sent', 'failed', 'blocked') THEN
                RAISE EXCEPTION 'invalid WhatsApp delivery result';
            END IF;
            UPDATE public.communication_outbox
            SET status = CASE
                    WHEN p_result = 'sent' THEN 'sent'
                    WHEN p_result = 'blocked' THEN 'blocked'
                    WHEN p_retryable AND attempts < 6 THEN 'queued'
                    ELSE 'failed'
                END,
                provider_message_id = CASE WHEN p_result = 'sent' THEN p_provider_message_id ELSE provider_message_id END,
                last_error_code = CASE WHEN p_result = 'sent' THEN '' ELSE left(coalesce(p_error_code, ''), 80) END,
                next_attempt_at = CASE WHEN p_result = 'failed' AND p_retryable AND attempts < 6
                    THEN now() + make_interval(secs => LEAST(900, (15 * power(2, greatest(attempts - 1, 0)))::integer))
                    ELSE next_attempt_at END,
                locked_until = NULL, updated_at = now()
            WHERE id = p_outbox_id AND status = 'sending';
            RETURN FOUND;
        END;
        $$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION terravanta_private.authorize_whatsapp_delivery(p_outbox_id uuid)
        RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE v_recipient uuid;
        BEGIN
            SELECT recipient_user_id INTO v_recipient
            FROM public.communication_outbox
            WHERE id = p_outbox_id AND status = 'sending'
            FOR UPDATE;
            IF NOT FOUND THEN RETURN false; END IF;
            IF NOT EXISTS (
                SELECT 1 FROM public.whatsapp_preferences p
                WHERE p.user_id = v_recipient AND p.phone_e164 IS NOT NULL
                  AND p.verified_at IS NOT NULL AND p.consent_granted_at IS NOT NULL
                  AND p.consent_revoked_at IS NULL
            ) THEN
                UPDATE public.communication_outbox
                SET status = 'cancelled', locked_until = NULL,
                    last_error_code = 'consent_revoked', updated_at = now()
                WHERE id = p_outbox_id AND status = 'sending';
                RETURN false;
            END IF;
            RETURN true;
        END;
        $$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION terravanta_private.apply_whatsapp_delivery_status(
            p_provider_message_id text, p_status text, p_error_code text DEFAULT ''
        ) RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE v_current text;
        BEGIN
            IF p_status NOT IN ('sent', 'delivered', 'read', 'failed') THEN RETURN false; END IF;
            SELECT status INTO v_current FROM public.communication_outbox
            WHERE provider_message_id = p_provider_message_id FOR UPDATE;
            IF NOT FOUND THEN RETURN false; END IF;
            UPDATE public.communication_outbox
            SET status = CASE
                    WHEN p_status = 'failed' THEN 'failed'
                    WHEN p_status = 'read' THEN 'read'
                    WHEN p_status = 'delivered' AND v_current <> 'read' THEN 'delivered'
                    WHEN p_status = 'sent' AND v_current NOT IN ('delivered', 'read') THEN 'sent'
                    ELSE v_current END,
                last_error_code = CASE WHEN p_status = 'failed' THEN left(coalesce(p_error_code, ''), 80) ELSE last_error_code END,
                updated_at = now()
            WHERE provider_message_id = p_provider_message_id;
            RETURN true;
        END;
        $$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION terravanta_private.maintain_whatsapp_retention()
        RETURNS integer
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE v_count integer := 0; v_changed integer := 0;
        BEGIN
            UPDATE public.communication_outbox
            SET body = '[message content removed after retention period]',
                conversation_code = NULL, updated_at = now()
            WHERE created_at < now() - interval '90 days'
              AND body <> '[message content removed after retention period]';
            GET DIAGNOSTICS v_changed = ROW_COUNT;
            v_count := v_count + v_changed;

            DELETE FROM public.whatsapp_link_challenges
            WHERE (consumed_at IS NOT NULL AND consumed_at < now() - interval '30 days')
               OR expires_at < now() - interval '30 days';
            GET DIAGNOSTICS v_changed = ROW_COUNT;
            v_count := v_count + v_changed;

            DELETE FROM public.meta_webhook_events
            WHERE received_at < now() - interval '90 days';
            GET DIAGNOSTICS v_changed = ROW_COUNT;
            RETURN v_count + v_changed;
        END;
        $$
    """)
    for signature in (
        "enqueue_whatsapp_contact_message(uuid)",
        "enqueue_whatsapp_contact_request(uuid)",
        "revoke_whatsapp_consent()",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION terravanta_private.{signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION terravanta_private.{signature} TO terravanta_app")
    for signature in (
        "claim_whatsapp_deliveries(integer)",
        "authorize_whatsapp_delivery(uuid)",
        "finish_whatsapp_delivery(uuid, text, text, text, boolean)",
        "maintain_whatsapp_retention()",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION terravanta_private.{signature} FROM PUBLIC, terravanta_app")
        op.execute(f"GRANT EXECUTE ON FUNCTION terravanta_private.{signature} TO terravanta_worker")
    op.execute("REVOKE ALL ON FUNCTION terravanta_private.apply_whatsapp_delivery_status(text, text, text) FROM PUBLIC, terravanta_app")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table, action in (
            ("audit_logs", "insert"),
            ("notifications", "insert"),
            ("veterinary_contact_messages", "insert"),
            ("farm_domain_events", "insert"),
            ("farm_members", "select"),
            ("veterinary_contact_requests", "select"),
            ("communication_outbox", "update"),
            ("communication_outbox", "insert"),
            ("communication_outbox", "select"),
            ("whatsapp_link_challenges", "update"),
            ("whatsapp_link_challenges", "select"),
            ("meta_webhook_events", "all"),
            ("whatsapp_preferences", "all"),
        ):
            op.execute(f'DROP POLICY IF EXISTS "terravanta_webhook_{table}_{action}" ON public.{table}')
        op.execute("""
            REVOKE ALL PRIVILEGES ON TABLE public.whatsapp_preferences,
                public.whatsapp_link_challenges, public.communication_outbox,
                public.meta_webhook_events, public.veterinary_contact_messages,
                public.farm_domain_events, public.notifications, public.audit_logs
                FROM terravanta_webhook;
            REVOKE SELECT (id, conversation_code, requester_user_id, veterinarian_user_id, farm_id, status, urgency)
                ON TABLE public.veterinary_contact_requests FROM terravanta_webhook;
            REVOKE SELECT (farm_id, user_id, role) ON TABLE public.farm_members FROM terravanta_webhook;
            REVOKE SELECT (id, provider_message_id, status), UPDATE (status, last_error_code, updated_at)
                ON TABLE public.communication_outbox FROM terravanta_webhook;
            REVOKE USAGE ON SCHEMA public FROM terravanta_webhook;
        """)
        op.execute("DROP POLICY IF EXISTS terravanta_communication_outbox_select ON public.communication_outbox")
        op.execute("DROP POLICY IF EXISTS terravanta_whatsapp_challenges_insert ON public.whatsapp_link_challenges")
        op.execute("DROP POLICY IF EXISTS terravanta_whatsapp_challenges_select ON public.whatsapp_link_challenges")
        op.execute("DROP POLICY IF EXISTS terravanta_whatsapp_preferences_select ON public.whatsapp_preferences")
        for signature in (
            "apply_whatsapp_delivery_status(text, text, text)",
            "maintain_whatsapp_retention()",
            "finish_whatsapp_delivery(uuid, text, text, text, boolean)",
            "authorize_whatsapp_delivery(uuid)",
            "claim_whatsapp_deliveries(integer)",
            "revoke_whatsapp_consent()",
            "enqueue_whatsapp_contact_request(uuid)",
            "enqueue_whatsapp_contact_message(uuid)",
        ):
            op.execute(f"DROP FUNCTION IF EXISTS terravanta_private.{signature}")
    op.drop_index("ix_meta_webhook_events_received_at", table_name="meta_webhook_events")
    for table in ("meta_webhook_events", "communication_outbox", "whatsapp_link_challenges", "whatsapp_preferences"):
        if table == "communication_outbox":
            op.drop_index("ix_communication_outbox_created_at", table_name=table)
        op.drop_table(table)
    op.drop_index("ix_vet_contact_request_conversation_code", table_name="veterinary_contact_requests")
    op.drop_column("veterinary_contact_requests", "conversation_code")
