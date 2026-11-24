"""Restrict source mapping profile lifecycle to draft then approved.

Revision ID: 0015_immutable_source_mapping_profiles
Revises: 0014_bilateral_supply_contracts
"""
from alembic import op


revision = "0015_immutable_source_mapping_profiles"
down_revision = "0014_bilateral_supply_contracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""
        REVOKE UPDATE ON TABLE public.source_mapping_profiles FROM terravanta_app;
        GRANT UPDATE (status, approved_by, approved_at)
            ON TABLE public.source_mapping_profiles TO terravanta_app;

        DROP POLICY IF EXISTS terravanta_source_mapping_profiles_insert
            ON public.source_mapping_profiles;
        CREATE POLICY terravanta_source_mapping_profiles_insert
            ON public.source_mapping_profiles FOR INSERT TO terravanta_app
            WITH CHECK (
                terravanta_private.is_cooperative_member(organization_id)
                AND status = 'draft'
                AND approved_by IS NULL
                AND approved_at IS NULL
            );

        DROP POLICY IF EXISTS terravanta_source_mapping_profiles_update
            ON public.source_mapping_profiles;
        CREATE POLICY terravanta_source_mapping_profiles_update
            ON public.source_mapping_profiles FOR UPDATE TO terravanta_app
            USING (
                terravanta_private.is_cooperative_member(organization_id)
                AND status = 'draft'
            )
            WITH CHECK (
                terravanta_private.is_cooperative_member(organization_id)
                AND (
                    status = 'draft'
                    OR (
                        status = 'approved'
                        AND approved_by = terravanta_private.current_user_id()
                        AND approved_at IS NOT NULL
                    )
                )
            );
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""
        REVOKE UPDATE (status, approved_by, approved_at)
            ON TABLE public.source_mapping_profiles FROM terravanta_app;
        GRANT UPDATE ON TABLE public.source_mapping_profiles TO terravanta_app;

        DROP POLICY IF EXISTS terravanta_source_mapping_profiles_insert
            ON public.source_mapping_profiles;
        CREATE POLICY terravanta_source_mapping_profiles_insert
            ON public.source_mapping_profiles FOR INSERT TO terravanta_app
            WITH CHECK (terravanta_private.is_cooperative_member(organization_id));

        DROP POLICY IF EXISTS terravanta_source_mapping_profiles_update
            ON public.source_mapping_profiles;
        CREATE POLICY terravanta_source_mapping_profiles_update
            ON public.source_mapping_profiles FOR UPDATE TO terravanta_app
            USING (terravanta_private.is_cooperative_member(organization_id))
            WITH CHECK (terravanta_private.is_cooperative_member(organization_id));
    """)
