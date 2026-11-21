"""Add veterinarian follow-up outcomes and tenant policies.

Revision ID: 0009_health_followups
Revises: 0008_tenant_rls
"""
from alembic import op
import sqlalchemy as sa


revision = "0009_health_followups"
down_revision = "0008_tenant_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.create_unique_constraint(
            "uq_animal_health_event_id_farm", "animal_health_events", ["id", "farm_id"]
        )
    event_farm_constraint = sa.ForeignKeyConstraint(
        ["health_event_id", "farm_id"],
        ["animal_health_events.id", "animal_health_events.farm_id"],
        ondelete="CASCADE",
        name="fk_health_follow_up_event_farm",
    ) if dialect == "postgresql" else sa.ForeignKeyConstraint(
        ["health_event_id"], ["animal_health_events.id"],
        ondelete="CASCADE", name="fk_health_follow_up_event",
    )
    op.create_table(
        "animal_health_follow_ups",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("farm_id", sa.Uuid(), sa.ForeignKey("farms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("health_event_id", sa.Uuid(), nullable=False),
        sa.Column("recorded_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recorded_by_name", sa.String(120), nullable=False),
        sa.Column("follow_up_status", sa.String(24), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("clinical_outcome", sa.String(32), nullable=True),
        sa.Column("case_disposition", sa.String(32), nullable=True),
        sa.Column("treatment_adherence", sa.String(24), nullable=False, server_default="unknown"),
        sa.Column("care_plan_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("next_follow_up_on", sa.Date(), nullable=True),
        sa.Column("case_cost_to_date_kes", sa.Numeric(12, 2), nullable=True),
        sa.Column("case_cost_source", sa.String(24), nullable=False, server_default="not_recorded"),
        sa.Column("milk_price_kes_per_liter", sa.Numeric(10, 2), nullable=True),
        sa.Column("milk_price_source", sa.String(24), nullable=False, server_default="not_recorded"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        event_farm_constraint,
        sa.CheckConstraint("follow_up_status IN ('completed', 'missed', 'unable_to_reach')", name="ck_health_follow_up_status"),
        sa.CheckConstraint("clinical_outcome IS NULL OR clinical_outcome IN ('resolved', 'improving', 'unchanged', 'worsened', 'referred', 'deceased', 'not_assessed')", name="ck_health_follow_up_outcome"),
        sa.CheckConstraint("case_disposition IS NULL OR case_disposition IN ('closed_recovered', 'continue_follow_up', 'referred', 'closed_other')", name="ck_health_follow_up_disposition"),
        sa.CheckConstraint("(follow_up_status = 'completed' AND clinical_outcome IS NOT NULL AND case_disposition IS NOT NULL) OR (follow_up_status <> 'completed' AND clinical_outcome IS NULL AND case_disposition IS NULL)", name="ck_health_follow_up_outcome_required"),
        sa.CheckConstraint("(case_disposition = 'closed_recovered' AND clinical_outcome = 'resolved') OR (case_disposition = 'closed_other' AND clinical_outcome = 'deceased') OR (case_disposition = 'referred' AND clinical_outcome = 'referred') OR (case_disposition = 'continue_follow_up' AND clinical_outcome NOT IN ('deceased', 'referred')) OR case_disposition IS NULL", name="ck_health_follow_up_disposition_consistent"),
        sa.CheckConstraint("((follow_up_status <> 'completed' OR case_disposition IN ('continue_follow_up', 'referred')) AND next_follow_up_on IS NOT NULL) OR (follow_up_status = 'completed' AND case_disposition IN ('closed_recovered', 'closed_other') AND next_follow_up_on IS NULL)", name="ck_health_follow_up_next_date"),
        sa.CheckConstraint("treatment_adherence IN ('as_directed', 'partially_followed', 'not_started', 'unknown')", name="ck_health_follow_up_adherence"),
        sa.CheckConstraint("case_cost_to_date_kes IS NULL OR case_cost_to_date_kes >= 0", name="ck_health_follow_up_cost_nonnegative"),
        sa.CheckConstraint("(case_cost_to_date_kes IS NULL AND case_cost_source = 'not_recorded') OR (case_cost_to_date_kes IS NOT NULL AND case_cost_source = 'farmer_reported')", name="ck_health_follow_up_cost_source_matches"),
        sa.CheckConstraint("case_cost_source IN ('not_recorded', 'farmer_reported')", name="ck_health_follow_up_cost_source"),
        sa.CheckConstraint("milk_price_kes_per_liter IS NULL OR milk_price_kes_per_liter > 0", name="ck_health_follow_up_milk_price_positive"),
        sa.CheckConstraint("(milk_price_kes_per_liter IS NULL AND milk_price_source = 'not_recorded') OR (milk_price_kes_per_liter IS NOT NULL AND milk_price_source = 'farmer_reported')", name="ck_health_follow_up_milk_source_matches"),
        sa.CheckConstraint("milk_price_source IN ('not_recorded', 'farmer_reported')", name="ck_health_follow_up_milk_source"),
    )
    op.create_index(
        "ix_health_follow_ups_farm_event_date",
        "animal_health_follow_ups",
        ["farm_id", "health_event_id", "occurred_on"],
    )
    if dialect == "postgresql":
        op.execute("ALTER TABLE public.animal_health_follow_ups ENABLE ROW LEVEL SECURITY")
        op.execute("REVOKE ALL ON TABLE public.animal_health_follow_ups FROM PUBLIC")
        op.execute("GRANT SELECT, INSERT ON TABLE public.animal_health_follow_ups TO terravanta_app")
        op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON TABLE public.animal_health_follow_ups FROM terravanta_app")
        op.execute("""
            CREATE POLICY terravanta_health_follow_ups_select
            ON public.animal_health_follow_ups FOR SELECT TO terravanta_app
            USING (terravanta_private.can_read_farm(farm_id))
        """)
        op.execute("""
            CREATE POLICY terravanta_health_follow_ups_insert
            ON public.animal_health_follow_ups FOR INSERT TO terravanta_app
            WITH CHECK (
                terravanta_private.can_verify_health_farm(farm_id)
                AND recorded_by = terravanta_private.current_user_id()
            )
        """)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS terravanta_health_follow_ups_select ON public.animal_health_follow_ups")
        op.execute("DROP POLICY IF EXISTS terravanta_health_follow_ups_insert ON public.animal_health_follow_ups")
    op.drop_index("ix_health_follow_ups_farm_event_date", table_name="animal_health_follow_ups")
    op.drop_table("animal_health_follow_ups")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("uq_animal_health_event_id_farm", "animal_health_events", type_="unique")
