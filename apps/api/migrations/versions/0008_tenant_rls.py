"""Enable tenant-scoped PostgreSQL RLS for API queries.

Revision ID: 0008_tenant_rls
Revises: 0007_receivables_pilot_decisions
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_tenant_rls"
down_revision = "0007_receivables_pilot_decisions"
branch_labels = None
depends_on = None


def _policy(table: str, action: str, expression: str, *, check: str | None = None) -> None:
    policy_name = f"terravanta_{table}_{action.lower()}"
    op.execute(f'CREATE POLICY "{policy_name}" ON public."{table}" FOR {action} TO terravanta_app ' +
               (f"USING ({expression})" if action != "INSERT" else "") +
               (f" WITH CHECK ({check or expression})" if action in {"INSERT", "UPDATE"} else ""))


def _tenant_table(table: str, read: str, *, insert: str | None = None, update: str | None = None) -> None:
    op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')
    _policy(table, "SELECT", read)
    if insert:
        _policy(table, "INSERT", insert)
    if update:
        _policy(table, "UPDATE", update, check=update)


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.create_table(
            "supabase_identity_links",
            sa.Column("supabase_user_id", sa.Uuid(), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        return
    if dialect != "postgresql":
        return

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'terravanta_app') THEN
                CREATE ROLE terravanta_app NOLOGIN INHERIT NOBYPASSRLS;
            END IF;
        END $$;
        ALTER ROLE terravanta_app NOLOGIN INHERIT NOBYPASSRLS;
        GRANT USAGE ON SCHEMA public TO terravanta_app;
        REVOKE CREATE ON SCHEMA public FROM PUBLIC;
    """)
    # Supabase owns authentication, while the existing Terravanta user UUID is
    # referenced by farm, health, and audit records. Keep the mapping private;
    # runtime access is limited to the SECURITY DEFINER helpers below.
    op.execute("""
        CREATE TABLE public.supabase_identity_links (
            supabase_user_id uuid PRIMARY KEY,
            user_id uuid NOT NULL UNIQUE REFERENCES public.users(id) ON DELETE CASCADE,
            linked_at timestamptz NOT NULL DEFAULT now()
        );
        ALTER TABLE public.supabase_identity_links ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON TABLE public.supabase_identity_links FROM PUBLIC;
        REVOKE ALL ON TABLE public.supabase_identity_links FROM terravanta_app;
        CREATE INDEX ix_users_email_lower ON public.users (lower(email));
    """)
    app_tables = [
        "users", "user_roles", "organizations", "organization_members", "farms", "farm_members", "consents",
        "plots", "crop_types", "crop_activities", "soil_tests", "water_tests", "herds", "animals",
        "animal_health_events", "clinical_observations", "vaccinations", "treatments", "reproductive_events",
        "veterinary_visits", "feed_suppliers", "feed_batches", "feed_ingredients", "feed_allocations",
        "manure_records", "compost_batches", "compost_applications", "production_records", "buyers", "product_lots",
        "deliveries", "reconciliation_runs", "reconciliation_items", "settlement_closes", "settlement_close_items",
        "access_codes", "evidence_artifacts", "source_mapping_profiles", "counterparty_relationships", "supply_contracts",
        "receivable_cases", "receivable_case_lines", "receivable_evidence_links", "counterparty_confirmations",
        "cash_receipts", "cash_allocations", "receivable_case_events", "receivables_pilot_decisions", "quality_tests",
        "laboratory_reports", "traceability_events", "ai_requests", "ai_responses", "ai_prompt_versions", "ai_feedback",
        "document_extractions", "knowledge_sources", "audit_logs",
    ]
    qualified_tables = ", ".join(f"public.{table}" for table in app_tables)
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON TABLE {qualified_tables} TO terravanta_app")
    op.execute("CREATE SCHEMA IF NOT EXISTS terravanta_private")
    op.execute("REVOKE ALL ON SCHEMA terravanta_private FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA terravanta_private TO terravanta_app")

    op.execute("""
        CREATE OR REPLACE FUNCTION terravanta_private.current_user_id()
        RETURNS uuid
        LANGUAGE sql STABLE PARALLEL SAFE
        SET search_path = pg_catalog
        AS $$
            SELECT nullif(current_setting('terravanta.user_id', true), '')::uuid
        $$;

        CREATE OR REPLACE FUNCTION terravanta_private.resolve_auth_user(p_subject uuid)
        RETURNS uuid
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT COALESCE(
                (SELECT l.user_id FROM public.supabase_identity_links l
                 WHERE l.supabase_user_id = p_subject),
                (SELECT u.id FROM public.users u WHERE u.id = p_subject)
            )
        $$;

        CREATE OR REPLACE FUNCTION terravanta_private.claim_farmer_identity(
            p_subject uuid, p_email text, p_display_name text
        )
        RETURNS TABLE (internal_user_id uuid, outcome text)
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_email text := lower(btrim(coalesce(p_email, '')));
            v_name text := btrim(coalesce(p_display_name, ''));
            v_user_id uuid;
            v_conflicting_role boolean;
            v_email_match_count bigint;
        BEGIN
            IF p_subject IS NULL OR p_subject IS DISTINCT FROM
               nullif(current_setting('terravanta.auth_subject', true), '')::uuid THEN
                RETURN QUERY SELECT NULL::uuid, 'unauthorized'::text;
                RETURN;
            END IF;
            IF length(v_email) < 5 OR length(v_email) > 255 OR position('@' IN v_email) < 2
               OR length(v_name) < 2 OR length(v_name) > 120 THEN
                RETURN QUERY SELECT NULL::uuid, 'invalid_profile'::text;
                RETURN;
            END IF;

            -- Serialize all provisioning for this verified email. This prevents
            -- duplicate identities racing during concurrent first sign-ins.
            PERFORM pg_advisory_xact_lock(hashtextextended(v_email, 0));

            SELECT l.user_id INTO v_user_id
            FROM public.supabase_identity_links l
            WHERE l.supabase_user_id = p_subject;
            IF FOUND THEN
                IF NOT EXISTS (SELECT 1 FROM public.users u WHERE u.id = v_user_id AND lower(u.email) = v_email) THEN
                    RETURN QUERY SELECT NULL::uuid, 'conflict'::text;
                    RETURN;
                END IF;
                RETURN QUERY SELECT v_user_id, 'existing'::text;
                RETURN;
            END IF;

            -- Accounts provisioned directly against the Supabase subject already
            -- have a canonical ID and need no bridge row.
            SELECT count(*) INTO v_email_match_count
            FROM public.users u
            WHERE lower(u.email) = v_email;
            IF v_email_match_count > 1 THEN
                RETURN QUERY SELECT NULL::uuid, 'conflict'::text;
                RETURN;
            END IF;

            SELECT u.id INTO v_user_id
            FROM public.users u
            WHERE u.id = p_subject
            FOR UPDATE;
            IF FOUND THEN
                IF NOT EXISTS (SELECT 1 FROM public.users u WHERE u.id = v_user_id AND lower(u.email) = v_email) THEN
                    RETURN QUERY SELECT NULL::uuid, 'conflict'::text;
                    RETURN;
                END IF;
                RETURN QUERY SELECT v_user_id, 'existing'::text;
                RETURN;
            END IF;

            SELECT u.id INTO v_user_id
            FROM public.users u
            WHERE lower(u.email) = v_email
            ORDER BY u.created_at
            LIMIT 1
            FOR UPDATE;
            IF FOUND THEN
                IF EXISTS (SELECT 1 FROM public.supabase_identity_links l WHERE l.user_id = v_user_id) THEN
                    RETURN QUERY SELECT NULL::uuid, 'conflict'::text;
                    RETURN;
                END IF;
                SELECT EXISTS (
                    SELECT 1 FROM public.user_roles r
                    WHERE r.user_id = v_user_id AND r.role <> 'farmer'
                ) OR EXISTS (
                    SELECT 1 FROM public.organization_members m
                    WHERE m.user_id = v_user_id
                ) OR EXISTS (
                    SELECT 1 FROM public.farm_members m
                    WHERE m.user_id = v_user_id AND m.role = 'veterinarian'
                ) INTO v_conflicting_role;
                IF v_conflicting_role THEN
                    RETURN QUERY SELECT NULL::uuid, 'conflict'::text;
                    RETURN;
                END IF;
                INSERT INTO public.supabase_identity_links (supabase_user_id, user_id)
                VALUES (p_subject, v_user_id);
                IF NOT EXISTS (SELECT 1 FROM public.user_roles r WHERE r.user_id = v_user_id AND r.role = 'farmer') THEN
                    INSERT INTO public.user_roles (user_id, role) VALUES (v_user_id, 'farmer');
                END IF;
                RETURN QUERY SELECT v_user_id, 'linked_legacy_farmer'::text;
                RETURN;
            END IF;

            INSERT INTO public.users (id, display_name, email, created_at)
            VALUES (p_subject, v_name, v_email, now())
            RETURNING id INTO v_user_id;
            INSERT INTO public.user_roles (user_id, role) VALUES (v_user_id, 'farmer');
            RETURN QUERY SELECT v_user_id, 'created'::text;
        END
        $$;

        CREATE OR REPLACE FUNCTION terravanta_private.is_org_member(p_org_id uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT p_org_id IS NOT NULL AND EXISTS (
                SELECT 1 FROM public.organization_members m
                JOIN public.organizations o ON o.id = m.organization_id
                WHERE m.organization_id = p_org_id
                  AND m.user_id = terravanta_private.current_user_id()
                  AND ((o.kind = 'cooperative' AND m.role = 'cooperative_admin')
                    OR (o.kind = 'processor' AND m.role = 'processor_admin'))
            )
        $$;

        CREATE OR REPLACE FUNCTION terravanta_private.is_cooperative_member(p_org_id uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM public.organization_members m
                JOIN public.organizations o ON o.id = m.organization_id
                WHERE m.organization_id = p_org_id
                  AND m.user_id = terravanta_private.current_user_id()
                  AND o.kind = 'cooperative' AND m.role = 'cooperative_admin'
            )
        $$;

        CREATE OR REPLACE FUNCTION terravanta_private.is_farm_member(p_farm_id uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT p_farm_id IS NOT NULL AND (
                EXISTS (SELECT 1 FROM public.farms f
                        WHERE f.id = p_farm_id AND f.created_by = terravanta_private.current_user_id())
                OR EXISTS (SELECT 1 FROM public.farm_members m
                           WHERE m.farm_id = p_farm_id AND m.user_id = terravanta_private.current_user_id())
            )
        $$;

        CREATE OR REPLACE FUNCTION terravanta_private.can_write_farm(p_farm_id uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT p_farm_id IS NOT NULL AND (
                EXISTS (SELECT 1 FROM public.farms f
                        WHERE f.id = p_farm_id AND f.created_by = terravanta_private.current_user_id())
                OR EXISTS (SELECT 1 FROM public.farm_members m
                           WHERE m.farm_id = p_farm_id
                             AND m.user_id = terravanta_private.current_user_id()
                             AND m.role IN ('owner', 'farmer'))
            )
        $$;

        CREATE OR REPLACE FUNCTION terravanta_private.can_write_health_farm(p_farm_id uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT terravanta_private.can_write_farm(p_farm_id)
                OR EXISTS (SELECT 1 FROM public.farm_members m
                           WHERE m.farm_id = p_farm_id
                             AND m.user_id = terravanta_private.current_user_id()
                             AND m.role = 'veterinarian')
        $$;

        CREATE OR REPLACE FUNCTION terravanta_private.can_verify_health_farm(p_farm_id uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT EXISTS (SELECT 1 FROM public.farm_members m
                           WHERE m.farm_id = p_farm_id
                             AND m.user_id = terravanta_private.current_user_id()
                             AND m.role = 'veterinarian')
        $$;

        CREATE OR REPLACE FUNCTION terravanta_private.can_read_farm(p_farm_id uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT terravanta_private.is_farm_member(p_farm_id)
        $$;

        CREATE OR REPLACE FUNCTION terravanta_private.can_read_delivery_summary(p_farm_id uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM public.consents c
                WHERE c.farm_id = p_farm_id
                  AND c.status = 'active'
                  AND c.scope = 'delivery_summary'
                  AND (c.expires_at IS NULL OR c.expires_at > now())
                  AND (
                    (
                      lower(coalesce(c.grantee_email, '')) = lower(coalesce((
                          SELECT u.email FROM public.users u
                          WHERE u.id = terravanta_private.current_user_id()
                      ), ''))
                      AND EXISTS (SELECT 1 FROM public.user_roles ur
                                  WHERE ur.user_id = terravanta_private.current_user_id()
                                    AND ur.role = 'cooperative_admin')
                    )
                    OR EXISTS (
                        SELECT 1 FROM public.organization_members m
                        JOIN public.organizations o ON o.id = m.organization_id
                        WHERE m.organization_id = c.grantee_org_id
                          AND m.user_id = terravanta_private.current_user_id()
                          AND m.role = 'cooperative_admin'
                          AND o.kind = 'cooperative'
                    )
                  )
            )
        $$;

        CREATE OR REPLACE FUNCTION terravanta_private.shared_farm_card(p_farm_id uuid)
        RETURNS TABLE (id uuid, name varchar, code varchar, is_synthetic boolean)
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT f.id, f.name, f.code, f.is_synthetic
            FROM public.farms f
            WHERE f.id = p_farm_id
              AND terravanta_private.can_read_delivery_summary(f.id)
        $$;

        CREATE OR REPLACE FUNCTION terravanta_private.can_read_related_org(p_org_id uuid, p_counterparty_id uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT terravanta_private.is_org_member(p_org_id)
                OR terravanta_private.is_org_member(p_counterparty_id)
        $$;

        CREATE OR REPLACE FUNCTION terravanta_private.can_read_case(p_case_id uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM public.receivable_cases c
                WHERE c.id = p_case_id
                  AND terravanta_private.can_read_related_org(c.organization_id, c.counterparty_organization_id)
            )
        $$;

        CREATE OR REPLACE FUNCTION terravanta_private.can_read_contract(p_contract_id uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM public.supply_contracts c
                JOIN public.counterparty_relationships r ON r.id = c.relationship_id
                WHERE c.id = p_contract_id
                  AND terravanta_private.can_read_related_org(r.organization_id, r.counterparty_organization_id)
            )
        $$;

        CREATE OR REPLACE FUNCTION terravanta_private.can_read_artifact(p_artifact_id uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM public.evidence_artifacts a
                WHERE a.id = p_artifact_id
                  AND terravanta_private.is_org_member(a.organization_id)
            ) OR EXISTS (
                SELECT 1 FROM public.receivable_evidence_links l
                WHERE l.artifact_id = p_artifact_id
                  AND terravanta_private.can_read_case(l.case_id)
            ) OR EXISTS (
                SELECT 1 FROM public.counterparty_confirmations c
                WHERE c.evidence_artifact_id = p_artifact_id
                  AND terravanta_private.can_read_case(c.case_id)
            )
        $$;

        CREATE OR REPLACE FUNCTION terravanta_private.can_read_reconciliation(p_run_id uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT EXISTS (SELECT 1 FROM public.reconciliation_runs r
                           WHERE r.id = p_run_id AND terravanta_private.is_cooperative_member(r.organization_id))
        $$;

        CREATE OR REPLACE FUNCTION terravanta_private.can_read_settlement_close(p_close_id uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT EXISTS (SELECT 1 FROM public.settlement_closes c
                           WHERE c.id = p_close_id AND terravanta_private.is_cooperative_member(c.organization_id))
        $$;

        CREATE OR REPLACE FUNCTION terravanta_private.can_read_ai_request(p_request_id uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT EXISTS (SELECT 1 FROM public.ai_requests r
                           WHERE r.id = p_request_id
                             AND r.user_id = terravanta_private.current_user_id()
                             AND terravanta_private.can_read_farm(r.farm_id))
        $$;

        REVOKE ALL ON ALL FUNCTIONS IN SCHEMA terravanta_private FROM PUBLIC;
        GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA terravanta_private TO terravanta_app;
    """)

    # Farm-owned records are readable by farm members. Only delivery and lot
    # rows can be read through the delivery-summary consent scope. The API uses
    # a security-definer projection for the few farm identity fields shared.
    farm_tables = [
        "farms", "plots", "soil_tests", "water_tests", "herds", "animals",
        "feed_batches", "feed_allocations", "manure_records", "compost_batches",
        "compost_applications", "production_records", "product_lots", "deliveries",
        "quality_tests", "laboratory_reports", "traceability_events", "document_extractions",
    ]
    clinical_tables = ["animal_health_events", "vaccinations", "treatments", "reproductive_events", "veterinary_visits"]
    for table in farm_tables:
        write = "terravanta_private.can_write_farm(farm_id)"
        read = "terravanta_private.can_read_farm(farm_id)"
        update = write
        if table == "farms":
            read = "terravanta_private.can_read_farm(id)"
            write = "created_by = terravanta_private.current_user_id()"
            update = "terravanta_private.can_write_farm(id)"
        elif table in {"deliveries", "product_lots"}:
            read = "terravanta_private.can_read_farm(farm_id) OR terravanta_private.can_read_delivery_summary(farm_id)"
        if table == "document_extractions":
            write = "terravanta_private.can_write_health_farm(farm_id)"
            update = write
        _tenant_table(table, read, insert=write, update=update)
    for table in clinical_tables:
        write = "terravanta_private.can_write_health_farm(farm_id)"
        update = "terravanta_private.can_verify_health_farm(farm_id)"
        _tenant_table(table, "terravanta_private.can_read_farm(farm_id)", insert=write, update=update)

    # Identity and membership tables are not self-service role administration.
    _tenant_table("users", "id = terravanta_private.current_user_id()",
                  insert="id = terravanta_private.current_user_id()",
                  update="id = terravanta_private.current_user_id()")
    _tenant_table("user_roles", "user_id = terravanta_private.current_user_id()",
                  insert="user_id = terravanta_private.current_user_id() AND role = 'farmer'")
    _tenant_table("organizations", "kind IN ('cooperative', 'processor') OR terravanta_private.is_org_member(id)")
    _tenant_table("organization_members", "terravanta_private.is_org_member(organization_id)")
    _tenant_table("farm_members", "user_id = terravanta_private.current_user_id() OR terravanta_private.can_write_farm(farm_id)",
                  insert="user_id = terravanta_private.current_user_id() AND (role = 'owner' AND EXISTS (SELECT 1 FROM public.farms f WHERE f.id = farm_id AND f.created_by = terravanta_private.current_user_id()))",
                  update="terravanta_private.can_write_farm(farm_id)")
    _tenant_table("consents",
                  "terravanta_private.can_read_farm(farm_id) OR (grantee_org_id IS NOT NULL AND terravanta_private.is_org_member(grantee_org_id)) OR (lower(grantee_email) = lower((SELECT u.email FROM public.users u WHERE u.id = terravanta_private.current_user_id())) AND EXISTS (SELECT 1 FROM public.user_roles ur WHERE ur.user_id = terravanta_private.current_user_id() AND ur.role = 'cooperative_admin'))",
                  insert="terravanta_private.can_write_farm(farm_id) AND granted_by = terravanta_private.current_user_id()",
                  update="terravanta_private.can_write_farm(farm_id)")

    # Farm child tables without their own farm_id inherit the parent boundary.
    child_scopes = {
        "crop_activities": ("EXISTS (SELECT 1 FROM public.plots p WHERE p.id = plot_id AND terravanta_private.can_read_farm(p.farm_id))",
                            "EXISTS (SELECT 1 FROM public.plots p WHERE p.id = plot_id AND terravanta_private.can_write_farm(p.farm_id))"),
        "clinical_observations": ("EXISTS (SELECT 1 FROM public.animal_health_events e WHERE e.id = health_event_id AND terravanta_private.can_read_farm(e.farm_id))",
                                  "EXISTS (SELECT 1 FROM public.animal_health_events e WHERE e.id = health_event_id AND terravanta_private.can_write_health_farm(e.farm_id))"),
        "feed_ingredients": ("EXISTS (SELECT 1 FROM public.feed_batches b WHERE b.id = feed_batch_id AND terravanta_private.can_read_farm(b.farm_id))",
                             "EXISTS (SELECT 1 FROM public.feed_batches b WHERE b.id = feed_batch_id AND terravanta_private.can_write_farm(b.farm_id))"),
        "reconciliation_items": ("terravanta_private.can_read_reconciliation(run_id)", "terravanta_private.can_read_reconciliation(run_id)"),
        "settlement_close_items": ("terravanta_private.can_read_settlement_close(close_id)", "terravanta_private.can_read_settlement_close(close_id)"),
    }
    for table, (read, write) in child_scopes.items():
        _tenant_table(table, read, insert=write, update=write)

    # Organization settlement, claims, and counterparties.
    for table in ("reconciliation_runs", "settlement_closes", "source_mapping_profiles", "cash_receipts", "cash_allocations", "receivables_pilot_decisions"):
        _tenant_table(table, "terravanta_private.is_cooperative_member(organization_id)",
                      insert="terravanta_private.is_cooperative_member(organization_id)",
                      update="terravanta_private.is_cooperative_member(organization_id)")
    _tenant_table("counterparty_relationships",
                  "terravanta_private.can_read_related_org(organization_id, counterparty_organization_id)",
                  insert="terravanta_private.is_cooperative_member(organization_id) AND created_by = terravanta_private.current_user_id()",
                  update="terravanta_private.is_cooperative_member(organization_id)")
    _tenant_table("supply_contracts", "terravanta_private.can_read_contract(id)",
                  insert="terravanta_private.is_cooperative_member(organization_id) AND created_by = terravanta_private.current_user_id()",
                  update="terravanta_private.is_cooperative_member(organization_id)")
    _tenant_table("receivable_cases",
                  "terravanta_private.can_read_related_org(organization_id, counterparty_organization_id)",
                  insert="terravanta_private.is_cooperative_member(organization_id) AND created_by = terravanta_private.current_user_id()",
                  update="terravanta_private.can_read_related_org(organization_id, counterparty_organization_id)")
    _tenant_table("receivable_case_lines",
                  "terravanta_private.can_read_case(case_id)",
                  insert="terravanta_private.is_org_member(organization_id) AND created_by = terravanta_private.current_user_id()")
    _tenant_table("evidence_artifacts", "terravanta_private.can_read_artifact(id)",
                  insert="terravanta_private.is_org_member(organization_id) AND uploaded_by = terravanta_private.current_user_id()")
    _tenant_table("receivable_evidence_links", "terravanta_private.can_read_case(case_id)",
                  insert="terravanta_private.can_read_case(case_id) AND linked_by = terravanta_private.current_user_id()")
    _tenant_table("counterparty_confirmations", "terravanta_private.can_read_case(case_id)",
                  insert="terravanta_private.is_org_member(counterparty_organization_id) AND confirmed_by_user_id = terravanta_private.current_user_id()")
    _tenant_table("receivable_case_events", "terravanta_private.can_read_case(case_id)",
                  insert="terravanta_private.can_read_case(case_id) AND (actor_user_id IS NULL OR actor_user_id = terravanta_private.current_user_id())")

    # First-party AI records, safe reference material, global lookup catalogs.
    _tenant_table("ai_requests", "user_id = terravanta_private.current_user_id() AND terravanta_private.can_read_farm(farm_id)",
                  insert="user_id = terravanta_private.current_user_id() AND terravanta_private.can_read_farm(farm_id)",
                  update="user_id = terravanta_private.current_user_id() AND terravanta_private.can_read_farm(farm_id)")
    _tenant_table("ai_responses", "terravanta_private.can_read_ai_request(request_id)",
                  insert="terravanta_private.can_read_ai_request(request_id)")
    _tenant_table("ai_feedback", "user_id = terravanta_private.current_user_id() AND terravanta_private.can_read_ai_request(request_id)",
                  insert="user_id = terravanta_private.current_user_id() AND terravanta_private.can_read_ai_request(request_id)")
    _tenant_table("audit_logs", "user_id = terravanta_private.current_user_id() OR (farm_id IS NOT NULL AND terravanta_private.can_read_farm(farm_id))",
                  insert="user_id = terravanta_private.current_user_id() AND (farm_id IS NULL OR terravanta_private.can_read_farm(farm_id))")
    _tenant_table("crop_types", "true")
    _tenant_table("feed_suppliers", "true")
    _tenant_table("buyers", "organization_id IS NULL OR terravanta_private.is_org_member(organization_id)")
    _tenant_table("ai_prompt_versions", "true")
    _tenant_table("knowledge_sources", "approved IS TRUE")

    # Legacy hashed email-code records are no longer reachable by any API path.
    # Leave the table available to historical Alembic migrations but deny the app role access.
    op.execute('ALTER TABLE public.access_codes ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL ON TABLE public.access_codes FROM terravanta_app')
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    raise RuntimeError("Tenant RLS is a security boundary; roll back the application, not these policies.")
