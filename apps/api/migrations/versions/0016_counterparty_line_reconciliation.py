"""Add append-only processor line reviews and shared counterparty evidence.

Revision ID: 0016_counterparty_line_reconciliation
Revises: 0015_immutable_source_mapping_profiles
"""
from alembic import op
import sqlalchemy as sa


revision = "0016_counterparty_line_reconciliation"
down_revision = "0015_immutable_source_mapping_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        with op.batch_alter_table("receivable_case_lines") as batch_op:
            batch_op.create_unique_constraint(
                "uq_receivable_case_line_id_case_org", ["id", "case_id", "organization_id"],
            )
    else:
        op.create_unique_constraint(
            "uq_receivable_case_line_id_case_org", "receivable_case_lines",
            ["id", "case_id", "organization_id"],
        )

    op.create_table(
        "counterparty_case_evidence",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("counterparty_organization_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("source_locator", sa.String(180), nullable=False, server_default=""),
        sa.Column("linked_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["case_id", "organization_id", "counterparty_organization_id"],
            ["receivable_cases.id", "receivable_cases.organization_id", "receivable_cases.counterparty_organization_id"],
            ondelete="CASCADE", name="fk_counterparty_case_evidence_case_org_party",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id", "counterparty_organization_id"],
            ["evidence_artifacts.id", "evidence_artifacts.organization_id"],
            name="fk_counterparty_case_evidence_artifact_org",
        ),
        sa.ForeignKeyConstraint(
            ["counterparty_organization_id", "linked_by"],
            ["organization_members.organization_id", "organization_members.user_id"],
            name="fk_counterparty_case_evidence_user_org_member",
        ),
        sa.UniqueConstraint(
            "case_id", "artifact_id", "source_locator",
            name="uq_counterparty_case_evidence_case_artifact_locator",
        ),
    )
    op.create_index(
        "ix_counterparty_case_evidence_case", "counterparty_case_evidence", ["case_id", "created_at"],
    )

    op.create_table(
        "counterparty_line_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("case_line_id", sa.Uuid(), nullable=False),
        sa.Column("counterparty_organization_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("review_status", sa.String(40), nullable=False),
        sa.Column("seller_amount_snapshot", sa.Numeric(16, 2), nullable=False),
        sa.Column("processor_amount", sa.Numeric(16, 2), nullable=True),
        sa.Column("processor_direction", sa.String(16), nullable=True),
        sa.Column("seller_direction_snapshot", sa.String(16), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="KES"),
        sa.Column("processor_reference", sa.String(160), nullable=False, server_default=""),
        sa.Column("source_locator", sa.String(180), nullable=False, server_default=""),
        sa.Column("review_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["case_id", "organization_id", "counterparty_organization_id"],
            ["receivable_cases.id", "receivable_cases.organization_id", "receivable_cases.counterparty_organization_id"],
            ondelete="CASCADE", name="fk_counterparty_line_review_case_org_party",
        ),
        sa.ForeignKeyConstraint(
            ["case_line_id", "case_id", "organization_id"],
            ["receivable_case_lines.id", "receivable_case_lines.case_id", "receivable_case_lines.organization_id"],
            ondelete="CASCADE", name="fk_counterparty_line_review_case_line",
        ),
        sa.ForeignKeyConstraint(
            ["counterparty_organization_id", "reviewed_by_user_id"],
            ["organization_members.organization_id", "organization_members.user_id"],
            name="fk_counterparty_line_review_user_org_member",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_artifact_id", "counterparty_organization_id"],
            ["evidence_artifacts.id", "evidence_artifacts.organization_id"],
            name="fk_counterparty_line_review_artifact_org",
        ),
        sa.CheckConstraint(
            "review_status IN ('matched', 'value_differs', 'missing_from_processor_record')",
            name="ck_counterparty_line_review_status",
        ),
        sa.CheckConstraint("seller_amount_snapshot >= 0", name="ck_counterparty_line_review_seller_amount_nonnegative"),
        sa.CheckConstraint("processor_amount IS NULL OR processor_amount >= 0", name="ck_counterparty_line_review_processor_amount_nonnegative"),
        sa.CheckConstraint(
            "seller_direction_snapshot IN ('increase', 'decrease', 'informational')",
            name="ck_counterparty_line_review_seller_direction",
        ),
        sa.CheckConstraint(
            "processor_direction IS NULL OR processor_direction IN ('increase', 'decrease', 'informational')",
            name="ck_counterparty_line_review_processor_direction",
        ),
        sa.CheckConstraint(
            "(review_status = 'missing_from_processor_record' AND processor_amount IS NULL AND processor_direction IS NULL) OR "
            "(review_status IN ('matched', 'value_differs') AND processor_amount IS NOT NULL AND processor_direction IS NOT NULL)",
            name="ck_counterparty_line_review_amount_presence",
        ),
    )
    op.create_index(
        "ix_counterparty_line_reviews_case_line_time", "counterparty_line_reviews", ["case_line_id", "reviewed_at"],
    )

    if dialect != "postgresql":
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
            ) OR EXISTS (
                SELECT 1 FROM public.counterparty_case_evidence e
                WHERE e.artifact_id = p_artifact_id
                  AND terravanta_private.can_read_case(e.case_id)
            ) OR EXISTS (
                SELECT 1 FROM public.counterparty_line_reviews r
                WHERE r.evidence_artifact_id = p_artifact_id
                  AND terravanta_private.can_read_case(r.case_id)
            )
        $$;

        REVOKE ALL ON TABLE public.counterparty_case_evidence FROM PUBLIC;
        REVOKE ALL ON TABLE public.counterparty_line_reviews FROM PUBLIC;
        GRANT SELECT, INSERT ON TABLE public.counterparty_case_evidence TO terravanta_app;
        GRANT SELECT, INSERT ON TABLE public.counterparty_line_reviews TO terravanta_app;

        ALTER TABLE public.counterparty_case_evidence ENABLE ROW LEVEL SECURITY;
        CREATE POLICY terravanta_counterparty_case_evidence_select
            ON public.counterparty_case_evidence FOR SELECT TO terravanta_app
            USING (terravanta_private.can_read_case(case_id));
        CREATE POLICY terravanta_counterparty_case_evidence_insert
            ON public.counterparty_case_evidence FOR INSERT TO terravanta_app
            WITH CHECK (
                linked_by = terravanta_private.current_user_id()
                AND terravanta_private.is_org_member(counterparty_organization_id)
                AND terravanta_private.can_read_case(case_id)
                AND EXISTS (
                    SELECT 1 FROM public.receivable_cases c
                    WHERE c.id = counterparty_case_evidence.case_id
                      AND c.organization_id = counterparty_case_evidence.organization_id
                      AND c.counterparty_organization_id = counterparty_case_evidence.counterparty_organization_id
                      AND c.status NOT IN ('draft', 'asserted')
                )
            );

        ALTER TABLE public.counterparty_line_reviews ENABLE ROW LEVEL SECURITY;
        CREATE POLICY terravanta_counterparty_line_reviews_select
            ON public.counterparty_line_reviews FOR SELECT TO terravanta_app
            USING (terravanta_private.can_read_case(case_id));
        CREATE POLICY terravanta_counterparty_line_reviews_insert
            ON public.counterparty_line_reviews FOR INSERT TO terravanta_app
            WITH CHECK (
                reviewed_by_user_id = terravanta_private.current_user_id()
                AND terravanta_private.is_org_member(counterparty_organization_id)
                AND terravanta_private.can_read_case(case_id)
                AND EXISTS (
                    SELECT 1 FROM public.receivable_cases c
                    JOIN public.receivable_case_lines l
                      ON l.case_id = c.id AND l.organization_id = c.organization_id
                    WHERE c.id = counterparty_line_reviews.case_id
                      AND c.organization_id = counterparty_line_reviews.organization_id
                      AND c.counterparty_organization_id = counterparty_line_reviews.counterparty_organization_id
                      AND c.status NOT IN ('draft', 'asserted', 'paid', 'closed')
                      AND l.id = counterparty_line_reviews.case_line_id
                )
                AND (
                    evidence_artifact_id IS NULL OR EXISTS (
                        SELECT 1 FROM public.counterparty_case_evidence e
                        WHERE e.case_id = counterparty_line_reviews.case_id
                          AND e.counterparty_organization_id = counterparty_line_reviews.counterparty_organization_id
                          AND e.artifact_id = counterparty_line_reviews.evidence_artifact_id
                    )
                )
            );

        CREATE OR REPLACE FUNCTION terravanta_private.validate_counterparty_line_review()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public, terravanta_private
        AS $$
        DECLARE
            source_amount numeric(16, 2);
            source_direction text;
            claim_currency text;
        BEGIN
            SELECT l.amount, l.direction, c.currency
              INTO source_amount, source_direction, claim_currency
              FROM public.receivable_cases c
              JOIN public.receivable_case_lines l
                ON l.case_id = c.id AND l.organization_id = c.organization_id
             WHERE c.id = NEW.case_id
               AND c.organization_id = NEW.organization_id
               AND l.id = NEW.case_line_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'claim line is unavailable for processor review';
            END IF;
            IF NEW.seller_amount_snapshot IS DISTINCT FROM source_amount
               OR NEW.seller_direction_snapshot IS DISTINCT FROM source_direction
               OR NEW.currency IS DISTINCT FROM claim_currency THEN
                RAISE EXCEPTION 'seller line snapshot must match the source claim line';
            END IF;
            IF NEW.review_status = 'matched'
               AND (NEW.processor_amount IS DISTINCT FROM source_amount
                    OR NEW.processor_direction IS DISTINCT FROM source_direction) THEN
                RAISE EXCEPTION 'a matched processor line must match source amount and direction';
            END IF;
            IF NEW.review_status = 'value_differs'
               AND NEW.processor_amount IS NOT DISTINCT FROM source_amount
               AND NEW.processor_direction IS NOT DISTINCT FROM source_direction THEN
                RAISE EXCEPTION 'a value-difference review must differ in amount or direction';
            END IF;
            IF NEW.evidence_artifact_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM public.counterparty_case_evidence e
                 WHERE e.case_id = NEW.case_id
                   AND e.counterparty_organization_id = NEW.counterparty_organization_id
                   AND e.artifact_id = NEW.evidence_artifact_id
            ) THEN
                RAISE EXCEPTION 'processor evidence must be explicitly shared to this claim';
            END IF;
            RETURN NEW;
        END
        $$;

        REVOKE ALL ON FUNCTION terravanta_private.validate_counterparty_line_review() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION terravanta_private.validate_counterparty_line_review() TO terravanta_app;
        CREATE TRIGGER trg_counterparty_line_review_validate
            BEFORE INSERT ON public.counterparty_line_reviews
            FOR EACH ROW EXECUTE FUNCTION terravanta_private.validate_counterparty_line_review();
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_counterparty_line_review_validate ON public.counterparty_line_reviews")
        op.execute("DROP FUNCTION IF EXISTS terravanta_private.validate_counterparty_line_review()")
        op.execute("DROP POLICY IF EXISTS terravanta_counterparty_line_reviews_insert ON public.counterparty_line_reviews")
        op.execute("DROP POLICY IF EXISTS terravanta_counterparty_line_reviews_select ON public.counterparty_line_reviews")
        op.execute("DROP POLICY IF EXISTS terravanta_counterparty_case_evidence_insert ON public.counterparty_case_evidence")
        op.execute("DROP POLICY IF EXISTS terravanta_counterparty_case_evidence_select ON public.counterparty_case_evidence")
        op.execute("REVOKE ALL ON TABLE public.counterparty_line_reviews FROM terravanta_app")
        op.execute("REVOKE ALL ON TABLE public.counterparty_case_evidence FROM terravanta_app")
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
        """)
    op.drop_index("ix_counterparty_line_reviews_case_line_time", table_name="counterparty_line_reviews")
    op.drop_table("counterparty_line_reviews")
    op.drop_index("ix_counterparty_case_evidence_case", table_name="counterparty_case_evidence")
    op.drop_table("counterparty_case_evidence")
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("receivable_case_lines") as batch_op:
            batch_op.drop_constraint("uq_receivable_case_line_id_case_org", type_="unique")
    else:
        op.drop_constraint(
            "uq_receivable_case_line_id_case_org", "receivable_case_lines", type_="unique",
        )
