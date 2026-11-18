"""Add tenant-scoped receivables evidence and confirmation records.

Revision ID: 0006_receivables_assurance
Revises: 0005_settlement_closes
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006_receivables_assurance"
down_revision = "0005_settlement_closes"
branch_labels = None
depends_on = None


def upgrade():
    uuid_type = sa.Uuid()
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

    op.create_table(
        "evidence_artifacts",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("organization_id", uuid_type, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by", uuid_type, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_party", sa.String(32), nullable=False, server_default="seller"),
        sa.Column("source_system", sa.String(120), nullable=False, server_default="manual_upload"),
        sa.Column("source_reference", sa.String(160), nullable=False, server_default=""),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(120), nullable=False),
        sa.Column("artifact_type", sa.String(60), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("sensitivity", sa.String(32), nullable=False, server_default="confidential"),
        sa.Column("retention_until", sa.Date(), nullable=True),
        sa.Column("source_metadata", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("id", "organization_id", name="uq_evidence_artifact_id_org"),
        sa.UniqueConstraint("organization_id", "sha256", name="uq_evidence_artifact_org_hash"),
        sa.CheckConstraint("source_party IN ('seller', 'counterparty', 'third_party', 'system')", name="ck_evidence_artifact_source_party"),
    )
    op.create_index("ix_evidence_artifacts_organization_id", "evidence_artifacts", ["organization_id"])

    op.create_table(
        "source_mapping_profiles",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("organization_id", uuid_type, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_system", sa.String(120), nullable=False),
        sa.Column("record_type", sa.String(60), nullable=False),
        sa.Column("schema_fingerprint", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("mapping_definition", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_by", uuid_type, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", uuid_type, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("id", "organization_id", name="uq_source_mapping_profile_id_org"),
        sa.UniqueConstraint("organization_id", "source_system", "record_type", "version", name="uq_source_mapping_profile_org_source_version"),
        sa.CheckConstraint("version > 0", name="ck_source_mapping_profile_version_positive"),
        sa.CheckConstraint("status IN ('draft', 'approved', 'retired')", name="ck_source_mapping_profile_status"),
    )
    op.create_index("ix_source_mapping_profiles_organization_id", "source_mapping_profiles", ["organization_id"])

    op.create_table(
        "counterparty_relationships",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("organization_id", uuid_type, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("counterparty_organization_id", uuid_type, sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("counterparty_name", sa.String(180), nullable=False),
        sa.Column("relationship_type", sa.String(40), nullable=False, server_default="processor"),
        sa.Column("external_reference", sa.String(120), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_by", uuid_type, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("id", "organization_id", name="uq_counterparty_relationship_id_org"),
        sa.UniqueConstraint("id", "organization_id", "counterparty_organization_id", name="uq_counterparty_relationship_id_org_counterparty"),
        sa.UniqueConstraint("organization_id", "external_reference", name="uq_counterparty_relationship_org_ref"),
        sa.CheckConstraint("relationship_type IN ('processor', 'buyer', 'aggregator', 'other')", name="ck_counterparty_relationship_type"),
        sa.CheckConstraint("status IN ('pending', 'active', 'suspended')", name="ck_counterparty_relationship_status"),
    )
    op.create_index("ix_counterparty_relationships_organization_id", "counterparty_relationships", ["organization_id"])
    op.create_index("ix_counterparty_relationships_counterparty_organization_id", "counterparty_relationships", ["counterparty_organization_id"])

    op.create_table(
        "supply_contracts",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("organization_id", uuid_type, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship_id", uuid_type, nullable=False),
        sa.Column("terms_artifact_id", uuid_type, nullable=True),
        sa.Column("contract_reference", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="KES"),
        sa.Column("terms_review_status", sa.String(32), nullable=False, server_default="seller_asserted"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("terms_snapshot", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_by", uuid_type, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["relationship_id", "organization_id"], ["counterparty_relationships.id", "counterparty_relationships.organization_id"], name="fk_supply_contract_relationship_org"),
        sa.ForeignKeyConstraint(["terms_artifact_id", "organization_id"], ["evidence_artifacts.id", "evidence_artifacts.organization_id"], name="fk_supply_contract_terms_artifact_org"),
        sa.UniqueConstraint("id", "organization_id", name="uq_supply_contract_id_org"),
        sa.UniqueConstraint("organization_id", "contract_reference", "version", name="uq_supply_contract_org_ref_version"),
        sa.CheckConstraint("version > 0", name="ck_supply_contract_version_positive"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_supply_contract_effective_dates"),
        sa.CheckConstraint("terms_review_status IN ('seller_asserted', 'counterparty_confirmed', 'under_review')", name="ck_supply_contract_review_status"),
        sa.CheckConstraint("status IN ('draft', 'active', 'superseded', 'expired')", name="ck_supply_contract_status"),
    )
    op.create_index("ix_supply_contracts_organization_id", "supply_contracts", ["organization_id"])

    op.create_table(
        "receivable_cases",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("organization_id", uuid_type, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship_id", uuid_type, nullable=False),
        sa.Column("contract_id", uuid_type, nullable=True),
        sa.Column("counterparty_organization_id", uuid_type, sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("source_document_type", sa.String(40), nullable=False),
        sa.Column("source_reference", sa.String(160), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("due_date_basis", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("due_date_reviewed_by", uuid_type, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("due_date_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="KES"),
        sa.Column("asserted_amount", sa.Numeric(16, 2), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", uuid_type, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["relationship_id", "organization_id"], ["counterparty_relationships.id", "counterparty_relationships.organization_id"], name="fk_receivable_case_relationship_org"),
        sa.ForeignKeyConstraint(["contract_id", "organization_id"], ["supply_contracts.id", "supply_contracts.organization_id"], name="fk_receivable_case_contract_org"),
        sa.UniqueConstraint("organization_id", "source_reference", name="uq_receivable_case_org_source_ref"),
        sa.UniqueConstraint("id", "organization_id", "counterparty_organization_id", name="uq_receivable_case_id_org_counterparty"),
        sa.CheckConstraint("asserted_amount >= 0", name="ck_receivable_case_asserted_amount_nonnegative"),
        sa.CheckConstraint("period_end IS NULL OR period_start IS NULL OR period_end >= period_start", name="ck_receivable_case_period_dates"),
        sa.CheckConstraint("due_date_basis IN ('unknown', 'contract', 'manual_review')", name="ck_receivable_case_due_date_basis"),
        sa.CheckConstraint("(due_date IS NULL AND due_date_basis = 'unknown') OR (due_date IS NOT NULL AND due_date_basis IN ('contract', 'manual_review') AND due_date_reviewed_by IS NOT NULL AND due_date_reviewed_at IS NOT NULL)", name="ck_receivable_case_due_date_requires_review"),
        sa.CheckConstraint("status IN ('draft', 'asserted', 'submitted', 'counterparty_confirmed', 'partially_confirmed', 'disputed', 'partially_paid', 'paid', 'closed')", name="ck_receivable_case_status"),
    )
    op.create_index("ix_receivable_cases_organization_id", "receivable_cases", ["organization_id"])
    op.create_index("ix_receivable_cases_status", "receivable_cases", ["status"])
    op.create_index("ix_receivable_cases_counterparty_organization_id", "receivable_cases", ["counterparty_organization_id"])
    op.create_index("ix_receivable_cases_org_status_due", "receivable_cases", ["organization_id", "status", "due_date"])

    op.create_table(
        "receivable_case_lines",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("organization_id", uuid_type, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", uuid_type, nullable=False),
        sa.Column("mapping_profile_id", uuid_type, nullable=True),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("line_type", sa.String(48), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False, server_default="increase"),
        sa.Column("source_reference", sa.String(160), nullable=False, server_default=""),
        sa.Column("occurred_on", sa.Date(), nullable=True),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=True),
        sa.Column("unit", sa.String(24), nullable=False, server_default=""),
        sa.Column("amount", sa.Numeric(16, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="KES"),
        sa.Column("evidence_artifact_id", uuid_type, nullable=True),
        sa.Column("source_locator", sa.String(180), nullable=False, server_default=""),
        sa.Column("provenance_class", sa.String(32), nullable=False, server_default="seller_attested"),
        sa.Column("created_by", uuid_type, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["case_id", "organization_id"], ["receivable_cases.id", "receivable_cases.organization_id"], ondelete="CASCADE", name="fk_receivable_case_line_case_org"),
        sa.ForeignKeyConstraint(["mapping_profile_id", "organization_id"], ["source_mapping_profiles.id", "source_mapping_profiles.organization_id"], name="fk_receivable_case_line_mapping_org"),
        sa.ForeignKeyConstraint(["evidence_artifact_id", "organization_id"], ["evidence_artifacts.id", "evidence_artifacts.organization_id"], name="fk_receivable_case_line_artifact_org"),
        sa.UniqueConstraint("case_id", "line_number", name="uq_receivable_case_line_number"),
        sa.CheckConstraint("line_number > 0", name="ck_receivable_case_line_number_positive"),
        sa.CheckConstraint("line_type IN ('accepted_supply', 'quality_adjustment', 'deduction', 'credit_note', 'other')", name="ck_receivable_case_line_type"),
        sa.CheckConstraint("direction IN ('increase', 'decrease', 'informational')", name="ck_receivable_case_line_direction"),
        sa.CheckConstraint("amount >= 0", name="ck_receivable_case_line_amount_nonnegative"),
        sa.CheckConstraint("quantity IS NULL OR quantity >= 0", name="ck_receivable_case_line_quantity_nonnegative"),
        sa.CheckConstraint("provenance_class IN ('seller_attested', 'counterparty_supplied', 'third_party_evidence', 'system_derived')", name="ck_receivable_case_line_provenance"),
    )
    op.create_index("ix_receivable_case_lines_organization_id", "receivable_case_lines", ["organization_id"])
    op.create_index("ix_receivable_case_lines_case", "receivable_case_lines", ["case_id"])

    op.create_table(
        "receivable_evidence_links",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("organization_id", uuid_type, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", uuid_type, nullable=False),
        sa.Column("artifact_id", uuid_type, nullable=False),
        sa.Column("evidence_role", sa.String(48), nullable=False),
        sa.Column("source_locator", sa.String(180), nullable=False, server_default=""),
        sa.Column("linked_by", uuid_type, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["case_id", "organization_id"], ["receivable_cases.id", "receivable_cases.organization_id"], ondelete="CASCADE", name="fk_receivable_evidence_case_org"),
        sa.ForeignKeyConstraint(["artifact_id", "organization_id"], ["evidence_artifacts.id", "evidence_artifacts.organization_id"], name="fk_receivable_evidence_artifact_org"),
        sa.UniqueConstraint("case_id", "artifact_id", "evidence_role", "source_locator", name="uq_receivable_evidence_link"),
    )
    op.create_index("ix_receivable_evidence_links_organization_id", "receivable_evidence_links", ["organization_id"])
    op.create_index("ix_receivable_evidence_case_role", "receivable_evidence_links", ["case_id", "evidence_role"])

    op.create_table(
        "counterparty_confirmations",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("organization_id", uuid_type, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", uuid_type, nullable=False),
        sa.Column("counterparty_organization_id", uuid_type, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("confirmed_by_user_id", uuid_type, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("response_status", sa.String(32), nullable=False),
        sa.Column("asserted_amount_snapshot", sa.Numeric(16, 2), nullable=False),
        sa.Column("confirmed_amount", sa.Numeric(16, 2), nullable=True),
        sa.Column("disputed_amount", sa.Numeric(16, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="KES"),
        sa.Column("response_reference", sa.String(160), nullable=False, server_default=""),
        sa.Column("response_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_artifact_id", uuid_type, nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["case_id", "organization_id", "counterparty_organization_id"], ["receivable_cases.id", "receivable_cases.organization_id", "receivable_cases.counterparty_organization_id"], ondelete="CASCADE", name="fk_counterparty_confirmation_case_org_counterparty"),
        sa.ForeignKeyConstraint(["counterparty_organization_id", "confirmed_by_user_id"], ["organization_members.organization_id", "organization_members.user_id"], name="fk_counterparty_confirmation_user_org_member"),
        sa.ForeignKeyConstraint(["evidence_artifact_id", "organization_id"], ["evidence_artifacts.id", "evidence_artifacts.organization_id"], name="fk_counterparty_confirmation_artifact_org"),
        sa.CheckConstraint("response_status IN ('accepted', 'partially_accepted', 'disputed', 'rejected', 'needs_information')", name="ck_counterparty_confirmation_status"),
        sa.CheckConstraint("asserted_amount_snapshot >= 0", name="ck_counterparty_confirmation_asserted_nonnegative"),
        sa.CheckConstraint("confirmed_amount IS NULL OR confirmed_amount >= 0", name="ck_counterparty_confirmation_confirmed_nonnegative"),
        sa.CheckConstraint("disputed_amount IS NULL OR disputed_amount >= 0", name="ck_counterparty_confirmation_disputed_nonnegative"),
    )
    op.create_index("ix_counterparty_confirmations_organization_id", "counterparty_confirmations", ["organization_id"])
    op.create_index("ix_counterparty_confirmations_case_time", "counterparty_confirmations", ["case_id", "confirmed_at"])

    op.create_table(
        "cash_receipts",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("organization_id", uuid_type, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_reference", sa.String(160), nullable=False),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(16, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="KES"),
        sa.Column("payment_rail", sa.String(40), nullable=False, server_default="unknown"),
        sa.Column("verification_status", sa.String(32), nullable=False, server_default="seller_attested"),
        sa.Column("verified_by", uuid_type, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_artifact_id", uuid_type, nullable=True),
        sa.Column("recorded_by", uuid_type, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["evidence_artifact_id", "organization_id"], ["evidence_artifacts.id", "evidence_artifacts.organization_id"], name="fk_cash_receipt_artifact_org"),
        sa.UniqueConstraint("organization_id", "source_reference", name="uq_cash_receipt_org_source_ref"),
        sa.UniqueConstraint("id", "organization_id", name="uq_cash_receipt_id_org"),
        sa.CheckConstraint("amount > 0", name="ck_cash_receipt_amount_positive"),
        sa.CheckConstraint("verification_status IN ('seller_attested', 'bank_evidence_reviewed', 'counterparty_confirmed')", name="ck_cash_receipt_verification_status"),
        sa.CheckConstraint("(verification_status = 'seller_attested' AND verified_by IS NULL AND verified_at IS NULL) OR (verification_status = 'bank_evidence_reviewed' AND verified_by IS NOT NULL AND verified_at IS NOT NULL AND evidence_artifact_id IS NOT NULL) OR (verification_status = 'counterparty_confirmed' AND verified_by IS NOT NULL AND verified_at IS NOT NULL)", name="ck_cash_receipt_verification_requires_review"),
    )
    op.create_index("ix_cash_receipts_organization_id", "cash_receipts", ["organization_id"])
    op.create_index("ix_cash_receipts_org_date", "cash_receipts", ["organization_id", "received_on"])

    op.create_table(
        "cash_allocations",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("organization_id", uuid_type, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("receipt_id", uuid_type, nullable=False),
        sa.Column("case_id", uuid_type, nullable=False),
        sa.Column("amount", sa.Numeric(16, 2), nullable=False),
        sa.Column("allocated_on", sa.Date(), nullable=False),
        sa.Column("allocated_by", uuid_type, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("allocation_reference", sa.String(160), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["receipt_id", "organization_id"], ["cash_receipts.id", "cash_receipts.organization_id"], ondelete="CASCADE", name="fk_cash_allocation_receipt_org"),
        sa.ForeignKeyConstraint(["case_id", "organization_id"], ["receivable_cases.id", "receivable_cases.organization_id"], ondelete="CASCADE", name="fk_cash_allocation_case_org"),
        sa.CheckConstraint("amount > 0", name="ck_cash_allocation_amount_positive"),
    )
    op.create_index("ix_cash_allocations_organization_id", "cash_allocations", ["organization_id"])
    op.create_index("ix_cash_allocations_case", "cash_allocations", ["case_id"])

    op.create_table(
        "receivable_case_events",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("organization_id", uuid_type, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", uuid_type, nullable=False),
        sa.Column("actor_user_id", uuid_type, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=False, server_default=""),
        sa.Column("to_status", sa.String(32), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_artifact_id", uuid_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["case_id", "organization_id"], ["receivable_cases.id", "receivable_cases.organization_id"], ondelete="CASCADE", name="fk_receivable_case_event_case_org"),
        sa.ForeignKeyConstraint(["evidence_artifact_id", "organization_id"], ["evidence_artifacts.id", "evidence_artifacts.organization_id"], name="fk_receivable_case_event_artifact_org"),
    )
    op.create_index("ix_receivable_case_events_organization_id", "receivable_case_events", ["organization_id"])
    op.create_index("ix_receivable_case_events_case_time", "receivable_case_events", ["case_id", "created_at"])


def downgrade():
    for table, index in [
        ("receivable_case_events", "ix_receivable_case_events_case_time"),
        ("receivable_case_events", "ix_receivable_case_events_organization_id"),
        ("cash_allocations", "ix_cash_allocations_case"),
        ("cash_allocations", "ix_cash_allocations_organization_id"),
        ("cash_receipts", "ix_cash_receipts_org_date"),
        ("cash_receipts", "ix_cash_receipts_organization_id"),
        ("counterparty_confirmations", "ix_counterparty_confirmations_case_time"),
        ("counterparty_confirmations", "ix_counterparty_confirmations_organization_id"),
        ("receivable_evidence_links", "ix_receivable_evidence_case_role"),
        ("receivable_evidence_links", "ix_receivable_evidence_links_organization_id"),
        ("receivable_case_lines", "ix_receivable_case_lines_case"),
        ("receivable_case_lines", "ix_receivable_case_lines_organization_id"),
        ("receivable_cases", "ix_receivable_cases_org_status_due"),
        ("receivable_cases", "ix_receivable_cases_counterparty_organization_id"),
        ("receivable_cases", "ix_receivable_cases_status"),
        ("receivable_cases", "ix_receivable_cases_organization_id"),
        ("supply_contracts", "ix_supply_contracts_organization_id"),
        ("source_mapping_profiles", "ix_source_mapping_profiles_organization_id"),
        ("counterparty_relationships", "ix_counterparty_relationships_counterparty_organization_id"),
        ("counterparty_relationships", "ix_counterparty_relationships_organization_id"),
        ("evidence_artifacts", "ix_evidence_artifacts_organization_id"),
    ]:
        op.drop_index(index, table_name=table)
    for table in [
        "receivable_case_events",
        "cash_allocations",
        "cash_receipts",
        "counterparty_confirmations",
        "receivable_evidence_links",
        "receivable_case_lines",
        "receivable_cases",
        "supply_contracts",
        "counterparty_relationships",
        "source_mapping_profiles",
        "evidence_artifacts",
    ]:
        op.drop_table(table)
