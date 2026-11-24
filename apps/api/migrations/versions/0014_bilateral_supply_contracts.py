"""Add bilateral, version-pinned supply contract review events.

Revision ID: 0014_bilateral_supply_contracts
Revises: 0013_whatsapp_delivery_safety
"""
from alembic import op
import sqlalchemy as sa


revision = "0014_bilateral_supply_contracts"
down_revision = "0013_whatsapp_delivery_safety"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supply_contract_review_events",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("counterparty_organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("terms_sha256", sa.String(64), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["contract_id", "organization_id"],
            ["supply_contracts.id", "supply_contracts.organization_id"],
            ondelete="CASCADE", name="fk_supply_contract_review_event_contract_org",
        ),
        sa.CheckConstraint("decision IN ('confirmed', 'needs_changes')", name="ck_supply_contract_review_event_decision"),
        sa.CheckConstraint("length(terms_sha256) = 64", name="ck_supply_contract_review_event_hash_length"),
    )
    op.create_index("ix_supply_contract_review_events_organization_id", "supply_contract_review_events", ["organization_id"])
    op.create_index("ix_supply_contract_review_events_counterparty_organization_id", "supply_contract_review_events", ["counterparty_organization_id"])
    op.create_index("ix_supply_contract_review_events_contract_time", "supply_contract_review_events", ["contract_id", "created_at"])

    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""
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
            ) OR EXISTS (
                SELECT 1 FROM public.supply_contracts c
                WHERE c.terms_artifact_id = p_artifact_id
                  AND terravanta_private.can_read_contract(c.id)
            )
        $$;

        REVOKE UPDATE ON TABLE public.supply_contracts FROM terravanta_app;
        GRANT UPDATE (status, terms_review_status) ON TABLE public.supply_contracts TO terravanta_app;
        DROP POLICY IF EXISTS terravanta_supply_contracts_update ON public.supply_contracts;
        CREATE POLICY terravanta_supply_contracts_update ON public.supply_contracts
            FOR UPDATE TO terravanta_app
            USING (terravanta_private.can_read_contract(id))
            WITH CHECK (terravanta_private.can_read_contract(id));

        REVOKE ALL ON TABLE public.supply_contract_review_events FROM PUBLIC;
        GRANT SELECT, INSERT ON TABLE public.supply_contract_review_events TO terravanta_app;
        ALTER TABLE public.supply_contract_review_events ENABLE ROW LEVEL SECURITY;
        CREATE POLICY terravanta_supply_contract_review_events_select
            ON public.supply_contract_review_events FOR SELECT TO terravanta_app
            USING (terravanta_private.can_read_contract(contract_id));
        CREATE POLICY terravanta_supply_contract_review_events_insert
            ON public.supply_contract_review_events FOR INSERT TO terravanta_app
            WITH CHECK (
                actor_user_id = terravanta_private.current_user_id()
                AND terravanta_private.can_read_contract(contract_id)
                AND terravanta_private.is_org_member(counterparty_organization_id)
                AND EXISTS (
                    SELECT 1
                    FROM public.supply_contracts c
                    JOIN public.counterparty_relationships r
                      ON r.id = c.relationship_id AND r.organization_id = c.organization_id
                    WHERE c.id = supply_contract_review_events.contract_id
                      AND c.organization_id = supply_contract_review_events.organization_id
                      AND r.counterparty_organization_id = supply_contract_review_events.counterparty_organization_id
                )
            );
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS terravanta_supply_contract_review_events_insert ON public.supply_contract_review_events")
        op.execute("DROP POLICY IF EXISTS terravanta_supply_contract_review_events_select ON public.supply_contract_review_events")
        op.execute("REVOKE ALL ON TABLE public.supply_contract_review_events FROM terravanta_app")
        op.execute("REVOKE UPDATE (status, terms_review_status) ON TABLE public.supply_contracts FROM terravanta_app")
        op.execute("GRANT UPDATE ON TABLE public.supply_contracts TO terravanta_app")
        op.execute("DROP POLICY IF EXISTS terravanta_supply_contracts_update ON public.supply_contracts")
        op.execute("CREATE POLICY terravanta_supply_contracts_update ON public.supply_contracts FOR UPDATE TO terravanta_app USING (terravanta_private.is_cooperative_member(organization_id)) WITH CHECK (terravanta_private.is_cooperative_member(organization_id))")
        op.execute("""
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
        """)
    op.drop_index("ix_supply_contract_review_events_contract_time", table_name="supply_contract_review_events")
    op.drop_index("ix_supply_contract_review_events_counterparty_organization_id", table_name="supply_contract_review_events")
    op.drop_index("ix_supply_contract_review_events_organization_id", table_name="supply_contract_review_events")
    op.drop_table("supply_contract_review_events")
