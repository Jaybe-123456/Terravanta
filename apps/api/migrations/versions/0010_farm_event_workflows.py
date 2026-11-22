"""Add append-only farm events, scheduled workflow steps, and recipient inbox.

Revision ID: 0010_farm_event_workflows
Revises: 0009_health_followups
"""
from alembic import op
import sqlalchemy as sa


revision = "0010_farm_event_workflows"
down_revision = "0009_health_followups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    op.create_table(
        "farm_domain_events",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("farm_id", sa.Uuid(), sa.ForeignKey("farms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("aggregate_type", sa.String(80), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("idempotency_key", sa.String(180), nullable=False, unique=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_farm_domain_events_farm_id", "farm_domain_events", ["farm_id"])
    op.create_index("ix_farm_domain_events_farm_created", "farm_domain_events", ["farm_id", "created_at"])

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("farm_id", sa.Uuid(), sa.ForeignKey("farms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("farm_domain_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_type", sa.String(80), nullable=False),
        sa.Column("step", sa.String(40), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(220), nullable=False, unique=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("step IN ('upcoming', 'due', 'overdue')", name="ck_workflow_run_step"),
        sa.CheckConstraint("status IN ('pending', 'completed', 'cancelled', 'failed')", name="ck_workflow_run_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_workflow_run_attempts"),
    )
    op.create_index("ix_workflow_runs_farm_id", "workflow_runs", ["farm_id"])
    op.create_index("ix_workflow_runs_event_id", "workflow_runs", ["event_id"])
    op.create_index("ix_workflow_runs_scheduled_at", "workflow_runs", ["scheduled_at"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])
    op.create_index("ix_workflow_runs_due", "workflow_runs", ["status", "scheduled_at"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("farm_id", sa.Uuid(), sa.ForeignKey("farms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("farm_domain_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notification_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="info"),
        sa.Column("action_section", sa.String(40), nullable=False, server_default="overview"),
        sa.Column("idempotency_key", sa.String(260), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("severity IN ('info', 'medium', 'high')", name="ck_notification_severity"),
    )
    op.create_index("ix_notifications_farm_id", "notifications", ["farm_id"])
    op.create_index("ix_notifications_recipient_user_id", "notifications", ["recipient_user_id"])
    op.create_index("ix_notifications_recipient_created", "notifications", ["recipient_user_id", "created_at"])

    if dialect != "postgresql":
        return

    op.execute("CREATE SCHEMA IF NOT EXISTS terravanta_private")
    op.execute("REVOKE ALL ON TABLE public.farm_domain_events, public.workflow_runs, public.notifications FROM PUBLIC")
    op.execute("GRANT SELECT, INSERT ON TABLE public.farm_domain_events TO terravanta_app")
    op.execute("GRANT SELECT, INSERT ON TABLE public.workflow_runs TO terravanta_app")
    op.execute("GRANT SELECT ON TABLE public.notifications TO terravanta_app")
    op.execute("GRANT UPDATE (read_at) ON TABLE public.notifications TO terravanta_app")

    op.execute("ALTER TABLE public.farm_domain_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.workflow_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY terravanta_farm_domain_events_select
        ON public.farm_domain_events FOR SELECT TO terravanta_app
        USING (terravanta_private.can_read_farm(farm_id))
    """)
    op.execute("""
        CREATE POLICY terravanta_farm_domain_events_insert
        ON public.farm_domain_events FOR INSERT TO terravanta_app
        WITH CHECK (
            terravanta_private.can_write_health_farm(farm_id)
            AND actor_user_id = terravanta_private.current_user_id()
        )
    """)
    op.execute("""
        CREATE POLICY terravanta_workflow_runs_select
        ON public.workflow_runs FOR SELECT TO terravanta_app
        USING (terravanta_private.can_read_farm(farm_id))
    """)
    op.execute("""
        CREATE POLICY terravanta_workflow_runs_insert
        ON public.workflow_runs FOR INSERT TO terravanta_app
        WITH CHECK (
            terravanta_private.can_write_health_farm(farm_id)
            AND EXISTS (
                SELECT 1 FROM public.farm_domain_events e
                WHERE e.id = event_id AND e.farm_id = workflow_runs.farm_id
            )
        )
    """)
    op.execute("""
        CREATE POLICY terravanta_notifications_select
        ON public.notifications FOR SELECT TO terravanta_app
        USING (recipient_user_id = terravanta_private.current_user_id())
    """)
    op.execute("""
        CREATE POLICY terravanta_notifications_update_read_at
        ON public.notifications FOR UPDATE TO terravanta_app
        USING (recipient_user_id = terravanta_private.current_user_id())
        WITH CHECK (recipient_user_id = terravanta_private.current_user_id())
    """)

    # This function is the only cross-tenant worker operation. It can process
    # only predefined follow-up reminders and inserts inbox rows only for
    # current members of the farm. It cannot send external messages or change
    # clinical records.
    op.execute("""
        CREATE OR REPLACE FUNCTION terravanta_private.process_due_followup_workflows(p_limit integer DEFAULT 100)
        RETURNS integer
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_run record;
            v_case_status text;
            v_current_due date;
            v_animal_tag text;
            v_processed integer := 0;
        BEGIN
            FOR v_run IN
                SELECT wr.id, wr.farm_id, wr.event_id, wr.workflow_type, wr.step,
                       wr.aggregate_id, wr.due_on, wr.idempotency_key
                FROM public.workflow_runs wr
                WHERE wr.status = 'pending' AND wr.scheduled_at <= now()
                ORDER BY wr.scheduled_at, wr.created_at
                LIMIT LEAST(GREATEST(COALESCE(p_limit, 100), 1), 500)
                FOR UPDATE OF wr SKIP LOCKED
            LOOP
                SELECT e.status, e.follow_up_on, a.tag
                INTO v_case_status, v_current_due, v_animal_tag
                FROM public.animal_health_events e
                JOIN public.animals a ON a.id = e.animal_id AND a.farm_id = e.farm_id
                WHERE e.id = v_run.aggregate_id AND e.farm_id = v_run.farm_id;

                IF NOT FOUND OR v_case_status <> 'open' OR v_current_due IS DISTINCT FROM v_run.due_on THEN
                    UPDATE public.workflow_runs
                    SET status = 'cancelled', attempts = attempts + 1, completed_at = now()
                    WHERE id = v_run.id;
                ELSE
                    INSERT INTO public.notifications (
                        id, farm_id, event_id, recipient_user_id, notification_type,
                        title, body, severity, action_section, idempotency_key
                    )
                    SELECT
                        gen_random_uuid(), v_run.farm_id, v_run.event_id, fm.user_id,
                        'veterinary_follow_up_' || v_run.step,
                        CASE v_run.step
                            WHEN 'upcoming' THEN 'Veterinary follow-up coming up'
                            WHEN 'overdue' THEN 'Veterinary follow-up is overdue'
                            ELSE 'Veterinary follow-up due today'
                        END,
                        'Follow-up for animal ' || v_animal_tag || ' is scheduled for ' || v_run.due_on::text || '.',
                        CASE v_run.step WHEN 'overdue' THEN 'high' WHEN 'due' THEN 'medium' ELSE 'info' END,
                        'veterinary',
                        v_run.idempotency_key || ':' || fm.user_id::text
                    FROM public.farm_members fm
                    WHERE fm.farm_id = v_run.farm_id
                      AND fm.role IN ('owner', 'farmer', 'veterinarian')
                    ON CONFLICT (idempotency_key) DO NOTHING;

                    UPDATE public.workflow_runs
                    SET status = 'completed', attempts = attempts + 1, completed_at = now()
                    WHERE id = v_run.id;
                END IF;
                v_processed := v_processed + 1;
            END LOOP;
            RETURN v_processed;
        END;
        $$
    """)
    op.execute("REVOKE ALL ON FUNCTION terravanta_private.process_due_followup_workflows(integer) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION terravanta_private.process_due_followup_workflows(integer) TO terravanta_app")
    op.execute("""
        WITH source_events AS (
            INSERT INTO public.farm_domain_events (
                id, farm_id, event_type, aggregate_type, aggregate_id,
                actor_user_id, idempotency_key, payload, occurred_at, created_at
            )
            SELECT
                gen_random_uuid(), e.farm_id, 'animal_health.follow_up_backfilled',
                'animal_health_event', e.id, NULL,
                'health-follow-up-backfill:' || e.id::text || ':' || e.follow_up_on::text,
                json_build_object('system_generated', true, 'source', 'migration_0010', 'follow_up_on', e.follow_up_on::text),
                e.created_at, now()
            FROM public.animal_health_events e
            WHERE e.status = 'open' AND e.follow_up_on IS NOT NULL
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, farm_id, aggregate_id
        )
        INSERT INTO public.workflow_runs (
            id, farm_id, event_id, workflow_type, step, aggregate_id, due_on,
            scheduled_at, status, idempotency_key, attempts, last_error, created_at
        )
        SELECT
            gen_random_uuid(), e.farm_id, s.id, 'health_follow_up_reminders_v1',
            due_step.step, e.id, e.follow_up_on,
            GREATEST((due_step.local_day::timestamp + time '08:00') AT TIME ZONE 'Africa/Nairobi', now()),
            'pending',
            'health_follow_up_reminders_v1:' || e.id::text || ':' || s.id::text || ':' || e.follow_up_on::text || ':' || due_step.step,
            0, '', now()
        FROM source_events s
        JOIN public.animal_health_events e ON e.id = s.aggregate_id AND e.farm_id = s.farm_id
        CROSS JOIN LATERAL (VALUES
            ('upcoming'::text, e.follow_up_on - 2),
            ('due'::text, e.follow_up_on),
            ('overdue'::text, e.follow_up_on + 1)
        ) AS due_step(step, local_day)
        WHERE (due_step.step = 'upcoming' AND due_step.local_day >= current_date)
           OR (due_step.step = 'due' AND e.follow_up_on >= current_date)
           OR due_step.step = 'overdue'
        ON CONFLICT (idempotency_key) DO NOTHING
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS terravanta_private.process_due_followup_workflows(integer)")
        op.execute("DROP POLICY IF EXISTS terravanta_notifications_update_read_at ON public.notifications")
        op.execute("DROP POLICY IF EXISTS terravanta_notifications_select ON public.notifications")
        op.execute("DROP POLICY IF EXISTS terravanta_workflow_runs_insert ON public.workflow_runs")
        op.execute("DROP POLICY IF EXISTS terravanta_workflow_runs_select ON public.workflow_runs")
        op.execute("DROP POLICY IF EXISTS terravanta_farm_domain_events_insert ON public.farm_domain_events")
        op.execute("DROP POLICY IF EXISTS terravanta_farm_domain_events_select ON public.farm_domain_events")
    for index, table in [
        ("ix_notifications_recipient_created", "notifications"),
        ("ix_notifications_recipient_user_id", "notifications"),
        ("ix_notifications_farm_id", "notifications"),
        ("ix_workflow_runs_due", "workflow_runs"),
        ("ix_workflow_runs_status", "workflow_runs"),
        ("ix_workflow_runs_scheduled_at", "workflow_runs"),
        ("ix_workflow_runs_event_id", "workflow_runs"),
        ("ix_workflow_runs_farm_id", "workflow_runs"),
        ("ix_farm_domain_events_farm_created", "farm_domain_events"),
        ("ix_farm_domain_events_farm_id", "farm_domain_events"),
    ]:
        op.drop_index(index, table_name=table)
    op.drop_table("notifications")
    op.drop_table("workflow_runs")
    op.drop_table("farm_domain_events")
