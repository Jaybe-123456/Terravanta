from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def uid():
    return uuid4()


def now_utc():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    display_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    roles: Mapped[list["UserRole"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class SupabaseIdentityLink(Base):
    """Maps a verified Supabase subject to Terravanta's stable internal user ID."""
    __tablename__ = "supabase_identity_links"
    supabase_user_id: Mapped[object] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(40), primary_key=True)
    user: Mapped[User] = relationship(back_populates="roles")


class AccessCode(Base):
    """Legacy schema retained for historical Alembic revisions; no runtime auth path uses it."""
    __tablename__ = "access_codes"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    code_type: Mapped[str] = mapped_column(String(20), default="invite", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(180))
    kind: Mapped[str] = mapped_column(String(40), default="cooperative")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class OrganizationMember(Base):
    __tablename__ = "organization_members"
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(40), default="cooperative_admin")


class Farm(Base):
    __tablename__ = "farms"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    owner_name: Mapped[str] = mapped_column(String(180))
    county: Mapped[str] = mapped_column(String(80))
    subcounty: Mapped[str] = mapped_column(String(80))
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    size_acres: Mapped[float] = mapped_column(Float, default=0)
    farming_system: Mapped[str] = mapped_column(String(80), default="mixed")
    production_activities: Mapped[list] = mapped_column(JSON, default=list)
    verification_status: Mapped[str] = mapped_column(String(40), default="farmer_submitted")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class FarmMember(Base):
    __tablename__ = "farm_members"
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(40))


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    granted_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    grantee_org_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("organizations.id"), nullable=True)
    grantee_email: Mapped[str] = mapped_column(String(255), default="cooperative@terravanta.demo")
    scope: Mapped[str] = mapped_column(String(60), default="delivery_summary")
    status: Mapped[str] = mapped_column(String(20), default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Plot(Base):
    __tablename__ = "plots"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    area_acres: Mapped[float] = mapped_column(Float)
    crop_type: Mapped[str] = mapped_column(String(100))
    planting_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    harvest_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    is_feed_crop: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class CropType(Base):
    __tablename__ = "crop_types"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    category: Mapped[str] = mapped_column(String(60), default="food")


class CropActivity(Base):
    __tablename__ = "crop_activities"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    plot_id: Mapped[object] = mapped_column(Uuid, ForeignKey("plots.id", ondelete="CASCADE"), index=True)
    activity_type: Mapped[str] = mapped_column(String(80))
    occurred_on: Mapped[object] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(Text, default="")


class SoilTest(Base):
    __tablename__ = "soil_tests"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    plot_id: Mapped[object] = mapped_column(Uuid, ForeignKey("plots.id"), index=True)
    tested_on: Mapped[object] = mapped_column(Date)
    laboratory: Mapped[str] = mapped_column(String(160), default="")
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class WaterTest(Base):
    __tablename__ = "water_tests"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    tested_on: Mapped[object] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(120), default="")
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class Herd(Base):
    __tablename__ = "herds"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))


class Animal(Base):
    __tablename__ = "animals"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    herd_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("herds.id"), nullable=True)
    tag: Mapped[str] = mapped_column(String(60), index=True)
    name: Mapped[str] = mapped_column(String(120))
    species: Mapped[str] = mapped_column(String(60))
    breed: Mapped[str] = mapped_column(String(100), default="")
    sex: Mapped[str] = mapped_column(String(30), default="unknown")
    date_of_birth: Mapped[object | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (Index("ix_animals_farm_tag", "farm_id", "tag", unique=True),)


class AnimalHealthEvent(Base):
    __tablename__ = "animal_health_events"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    animal_id: Mapped[object] = mapped_column(Uuid, ForeignKey("animals.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    verified_by: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(60))
    occurred_on: Mapped[object] = mapped_column(Date)
    summary: Mapped[str] = mapped_column(Text)
    observations: Mapped[dict] = mapped_column(JSON, default=dict)
    follow_up_on: Mapped[object | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ClinicalObservation(Base):
    __tablename__ = "clinical_observations"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    health_event_id: Mapped[object] = mapped_column(Uuid, ForeignKey("animal_health_events.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(100))
    value: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(32), default="")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Vaccination(Base):
    __tablename__ = "vaccinations"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    animal_id: Mapped[object] = mapped_column(Uuid, ForeignKey("animals.id", ondelete="CASCADE"), index=True)
    recorded_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    vaccine_name: Mapped[str] = mapped_column(String(160))
    administered_on: Mapped[object] = mapped_column(Date)
    follow_up_on: Mapped[object | None] = mapped_column(Date, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class Treatment(Base):
    __tablename__ = "treatments"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    animal_id: Mapped[object] = mapped_column(Uuid, ForeignKey("animals.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("animal_health_events.id"), nullable=True)
    recorded_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    details: Mapped[str] = mapped_column(Text)
    occurred_on: Mapped[object] = mapped_column(Date)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class ReproductiveEvent(Base):
    __tablename__ = "reproductive_events"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    animal_id: Mapped[object] = mapped_column(Uuid, ForeignKey("animals.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(60))
    occurred_on: Mapped[object] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(Text, default="")


class VeterinaryVisit(Base):
    __tablename__ = "veterinary_visits"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    animal_id: Mapped[object] = mapped_column(Uuid, ForeignKey("animals.id", ondelete="CASCADE"), index=True)
    veterinarian_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    visited_on: Mapped[object] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(Text, default="")
    follow_up_on: Mapped[object | None] = mapped_column(Date, nullable=True)


class FeedSupplier(Base):
    __tablename__ = "feed_suppliers"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(180))


class FeedBatch(Base):
    __tablename__ = "feed_batches"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    plot_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("plots.id"), nullable=True)
    supplier_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("feed_suppliers.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    ingredients: Mapped[list] = mapped_column(JSON, default=list)
    quantity_kg: Mapped[float] = mapped_column(Float)
    batch_date: Mapped[object] = mapped_column(Date)
    storage_conditions: Mapped[str] = mapped_column(String(180), default="")
    aflatoxin_status: Mapped[str] = mapped_column(String(40), default="not_tested")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class FeedIngredient(Base):
    __tablename__ = "feed_ingredients"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    feed_batch_id: Mapped[object] = mapped_column(Uuid, ForeignKey("feed_batches.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    quantity_kg: Mapped[float | None] = mapped_column(Float, nullable=True)


class FeedAllocation(Base):
    __tablename__ = "feed_allocations"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    feed_batch_id: Mapped[object] = mapped_column(Uuid, ForeignKey("feed_batches.id"), index=True)
    animal_id: Mapped[object] = mapped_column(Uuid, ForeignKey("animals.id"), index=True)
    allocated_kg: Mapped[float] = mapped_column(Float)
    allocated_on: Mapped[object] = mapped_column(Date)


class ManureRecord(Base):
    __tablename__ = "manure_records"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    collected_on: Mapped[object] = mapped_column(Date)
    quantity_kg: Mapped[float] = mapped_column(Float)
    source_notes: Mapped[str] = mapped_column(Text, default="")


class CompostBatch(Base):
    __tablename__ = "compost_batches"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    manure_record_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("manure_records.id"), nullable=True)
    created_on: Mapped[object] = mapped_column(Date)
    quantity_kg: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(40), default="curing")


class CompostApplication(Base):
    __tablename__ = "compost_applications"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    compost_batch_id: Mapped[object] = mapped_column(Uuid, ForeignKey("compost_batches.id"), index=True)
    plot_id: Mapped[object] = mapped_column(Uuid, ForeignKey("plots.id"), index=True)
    applied_on: Mapped[object] = mapped_column(Date)
    quantity_kg: Mapped[float] = mapped_column(Float)


class ProductionRecord(Base):
    __tablename__ = "production_records"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    animal_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("animals.id"), nullable=True)
    plot_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("plots.id"), nullable=True)
    product_type: Mapped[str] = mapped_column(String(50))
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(24))
    recorded_on: Mapped[object] = mapped_column(Date)
    quality_measurements: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Buyer(Base):
    __tablename__ = "buyers"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160))
    organization_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("organizations.id"), nullable=True)


class ProductLot(Base):
    __tablename__ = "product_lots"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    production_record_id: Mapped[object] = mapped_column(Uuid, ForeignKey("production_records.id"), index=True)
    lot_code: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    product_type: Mapped[str] = mapped_column(String(50))
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Delivery(Base):
    __tablename__ = "deliveries"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    product_lot_id: Mapped[object] = mapped_column(Uuid, ForeignKey("product_lots.id"), index=True)
    buyer_id: Mapped[object] = mapped_column(Uuid, ForeignKey("buyers.id"), index=True)
    delivery_date: Mapped[object] = mapped_column(Date)
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(30), default="accepted")
    reference: Mapped[str] = mapped_column(String(80), default="")


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    uploaded_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(255))
    source_sha256: Mapped[str] = mapped_column(String(64))
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("organization_id", "source_sha256", name="uq_reconciliation_org_source"),)


class ReconciliationItem(Base):
    __tablename__ = "reconciliation_items"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    run_id: Mapped[object] = mapped_column(Uuid, ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    farm_code: Mapped[str] = mapped_column(String(40), default="")
    submitted_date: Mapped[str] = mapped_column(String(32), default="")
    collection_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    submitted_quantity: Mapped[str] = mapped_column(String(32), default="")
    quantity_liters: Mapped[float | None] = mapped_column(Float, nullable=True)
    receipt_reference: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(40), index=True)
    matched_farm_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("farms.id"), nullable=True, index=True)
    matched_delivery_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("deliveries.id"), nullable=True, index=True)
    discrepancy_details: Mapped[list] = mapped_column(JSON, default=list)
    review_status: Mapped[str] = mapped_column(String(24), default="pending")
    reviewed_by: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("run_id", "row_number", name="uq_reconciliation_run_row"),)


class SettlementClose(Base):
    __tablename__ = "settlement_closes"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    period_start: Mapped[object] = mapped_column(Date)
    period_end: Mapped[object] = mapped_column(Date)
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    collection_filename: Mapped[str] = mapped_column(String(255))
    processor_filename: Mapped[str] = mapped_column(String(255))
    payout_filename: Mapped[str] = mapped_column(String(255))
    collection_sha256: Mapped[str] = mapped_column(String(64))
    processor_sha256: Mapped[str] = mapped_column(String(64))
    payout_sha256: Mapped[str] = mapped_column(String(64))
    collection_row_count: Mapped[int] = mapped_column(Integer, default=0)
    processor_row_count: Mapped[int] = mapped_column(Integer, default=0)
    payout_row_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="review_required", index=True)
    approval_note: Mapped[str] = mapped_column(String(500), default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("organization_id", "source_fingerprint", name="uq_settlement_org_fingerprint"),)


class SettlementCloseItem(Base):
    __tablename__ = "settlement_close_items"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    close_id: Mapped[object] = mapped_column(Uuid, ForeignKey("settlement_closes.id", ondelete="CASCADE"), index=True)
    member_code: Mapped[str] = mapped_column(String(80), index=True)
    collection_liters: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    processor_liters: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    volume_variance_liters: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    gross_amount_kes: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    deductions_kes: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    net_amount_kes: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    payout_amount_kes: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    processor_arithmetic_variance_kes: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    payout_variance_kes: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    status: Mapped[str] = mapped_column(String(30), index=True)
    issues: Mapped[list] = mapped_column(JSON, default=list)
    source_rows: Mapped[dict] = mapped_column(JSON, default=dict)
    source_references: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    reviewer_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("close_id", "member_code", name="uq_settlement_member_per_close"),)


class EvidenceArtifact(Base):
    """Private, immutable source-file metadata for receivable evidence."""
    __tablename__ = "evidence_artifacts"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    uploaded_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    source_party: Mapped[str] = mapped_column(String(32), default="seller")
    source_system: Mapped[str] = mapped_column(String(120), default="manual_upload")
    source_reference: Mapped[str] = mapped_column(String(160), default="")
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(120))
    artifact_type: Mapped[str] = mapped_column(String(60))
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(Text)
    sensitivity: Mapped[str] = mapped_column(String(32), default="confidential")
    retention_until: Mapped[object | None] = mapped_column(Date, nullable=True)
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_evidence_artifact_id_org"),
        UniqueConstraint("organization_id", "sha256", name="uq_evidence_artifact_org_hash"),
        CheckConstraint("source_party IN ('seller', 'counterparty', 'third_party', 'system')", name="ck_evidence_artifact_source_party"),
    )


class SourceMappingProfile(Base):
    """Versioned, human-approved mapping from a named source export."""
    __tablename__ = "source_mapping_profiles"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    source_system: Mapped[str] = mapped_column(String(120))
    record_type: Mapped[str] = mapped_column(String(60))
    schema_fingerprint: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    mapping_definition: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_source_mapping_profile_id_org"),
        UniqueConstraint("organization_id", "source_system", "record_type", "version", name="uq_source_mapping_profile_org_source_version"),
        CheckConstraint("version > 0", name="ck_source_mapping_profile_version_positive"),
        CheckConstraint("status IN ('draft', 'approved', 'retired')", name="ck_source_mapping_profile_status"),
    )


class CounterpartyRelationship(Base):
    """A seller cooperative's explicit relationship with a processor or buyer."""
    __tablename__ = "counterparty_relationships"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    counterparty_organization_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("organizations.id"), nullable=True, index=True)
    counterparty_name: Mapped[str] = mapped_column(String(180))
    relationship_type: Mapped[str] = mapped_column(String(40), default="processor")
    external_reference: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_counterparty_relationship_id_org"),
        UniqueConstraint("id", "organization_id", "counterparty_organization_id", name="uq_counterparty_relationship_id_org_counterparty"),
        UniqueConstraint("organization_id", "external_reference", name="uq_counterparty_relationship_org_ref"),
        CheckConstraint("relationship_type IN ('processor', 'buyer', 'aggregator', 'other')", name="ck_counterparty_relationship_type"),
        CheckConstraint("status IN ('pending', 'active', 'suspended')", name="ck_counterparty_relationship_status"),
    )


class SupplyContract(Base):
    """A versioned, human-reviewed snapshot of seller/buyer commercial terms."""
    __tablename__ = "supply_contracts"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    relationship_id: Mapped[object] = mapped_column(Uuid)
    terms_artifact_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    contract_reference: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer, default=1)
    effective_from: Mapped[object] = mapped_column(Date)
    effective_to: Mapped[object | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="KES")
    terms_review_status: Mapped[str] = mapped_column(String(32), default="seller_asserted")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    terms_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (
        ForeignKeyConstraint(["relationship_id", "organization_id"], ["counterparty_relationships.id", "counterparty_relationships.organization_id"], name="fk_supply_contract_relationship_org"),
        ForeignKeyConstraint(["terms_artifact_id", "organization_id"], ["evidence_artifacts.id", "evidence_artifacts.organization_id"], name="fk_supply_contract_terms_artifact_org"),
        UniqueConstraint("id", "organization_id", name="uq_supply_contract_id_org"),
        UniqueConstraint("organization_id", "contract_reference", "version", name="uq_supply_contract_org_ref_version"),
        CheckConstraint("version > 0", name="ck_supply_contract_version_positive"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_supply_contract_effective_dates"),
        CheckConstraint("terms_review_status IN ('seller_asserted', 'counterparty_confirmed', 'under_review')", name="ck_supply_contract_review_status"),
        CheckConstraint("status IN ('draft', 'active', 'superseded', 'expired')", name="ck_supply_contract_status"),
    )


class ReceivableCase(Base):
    """Seller-side assertion of an amount due; confirmation and cash stay separate."""
    __tablename__ = "receivable_cases"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    relationship_id: Mapped[object] = mapped_column(Uuid)
    contract_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    counterparty_organization_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("organizations.id"), nullable=True, index=True)
    source_document_type: Mapped[str] = mapped_column(String(40))
    source_reference: Mapped[str] = mapped_column(String(160))
    period_start: Mapped[object | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[object | None] = mapped_column(Date, nullable=True)
    invoice_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    due_date_basis: Mapped[str] = mapped_column(String(32), default="unknown")
    due_date_reviewed_by: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    due_date_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="KES")
    asserted_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    __table_args__ = (
        ForeignKeyConstraint(["relationship_id", "organization_id"], ["counterparty_relationships.id", "counterparty_relationships.organization_id"], name="fk_receivable_case_relationship_org"),
        ForeignKeyConstraint(["contract_id", "organization_id"], ["supply_contracts.id", "supply_contracts.organization_id"], name="fk_receivable_case_contract_org"),
        UniqueConstraint("organization_id", "source_reference", name="uq_receivable_case_org_source_ref"),
        UniqueConstraint("id", "organization_id", name="uq_receivable_case_id_org"),
        UniqueConstraint("id", "organization_id", "counterparty_organization_id", name="uq_receivable_case_id_org_counterparty"),
        CheckConstraint("asserted_amount >= 0", name="ck_receivable_case_asserted_amount_nonnegative"),
        CheckConstraint("period_end IS NULL OR period_start IS NULL OR period_end >= period_start", name="ck_receivable_case_period_dates"),
        CheckConstraint("due_date_basis IN ('unknown', 'contract', 'manual_review')", name="ck_receivable_case_due_date_basis"),
        CheckConstraint("(due_date IS NULL AND due_date_basis = 'unknown') OR (due_date IS NOT NULL AND due_date_basis IN ('contract', 'manual_review') AND due_date_reviewed_by IS NOT NULL AND due_date_reviewed_at IS NOT NULL)", name="ck_receivable_case_due_date_requires_review"),
        CheckConstraint("status IN ('draft', 'asserted', 'submitted', 'counterparty_confirmed', 'partially_confirmed', 'disputed', 'partially_paid', 'paid', 'closed')", name="ck_receivable_case_status"),
        Index("ix_receivable_cases_org_status_due", "organization_id", "status", "due_date"),
    )


class ReceivableCaseLine(Base):
    """A normalized claim line whose amount and direction remain source-linked."""
    __tablename__ = "receivable_case_lines"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[object] = mapped_column(Uuid)
    mapping_profile_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    line_number: Mapped[int] = mapped_column(Integer)
    line_type: Mapped[str] = mapped_column(String(48))
    direction: Mapped[str] = mapped_column(String(16), default="increase")
    source_reference: Mapped[str] = mapped_column(String(160), default="")
    occurred_on: Mapped[object | None] = mapped_column(Date, nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    unit: Mapped[str] = mapped_column(String(24), default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    currency: Mapped[str] = mapped_column(String(3), default="KES")
    evidence_artifact_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    source_locator: Mapped[str] = mapped_column(String(180), default="")
    provenance_class: Mapped[str] = mapped_column(String(32), default="seller_attested")
    created_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (
        ForeignKeyConstraint(["case_id", "organization_id"], ["receivable_cases.id", "receivable_cases.organization_id"], ondelete="CASCADE", name="fk_receivable_case_line_case_org"),
        ForeignKeyConstraint(["mapping_profile_id", "organization_id"], ["source_mapping_profiles.id", "source_mapping_profiles.organization_id"], name="fk_receivable_case_line_mapping_org"),
        ForeignKeyConstraint(["evidence_artifact_id", "organization_id"], ["evidence_artifacts.id", "evidence_artifacts.organization_id"], name="fk_receivable_case_line_artifact_org"),
        UniqueConstraint("case_id", "line_number", name="uq_receivable_case_line_number"),
        CheckConstraint("line_number > 0", name="ck_receivable_case_line_number_positive"),
        CheckConstraint("line_type IN ('accepted_supply', 'quality_adjustment', 'deduction', 'credit_note', 'other')", name="ck_receivable_case_line_type"),
        CheckConstraint("direction IN ('increase', 'decrease', 'informational')", name="ck_receivable_case_line_direction"),
        CheckConstraint("amount >= 0", name="ck_receivable_case_line_amount_nonnegative"),
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="ck_receivable_case_line_quantity_nonnegative"),
        CheckConstraint("provenance_class IN ('seller_attested', 'counterparty_supplied', 'third_party_evidence', 'system_derived')", name="ck_receivable_case_line_provenance"),
        Index("ix_receivable_case_lines_case", "case_id"),
    )


class ReceivableEvidenceLink(Base):
    __tablename__ = "receivable_evidence_links"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[object] = mapped_column(Uuid)
    artifact_id: Mapped[object] = mapped_column(Uuid)
    evidence_role: Mapped[str] = mapped_column(String(48))
    source_locator: Mapped[str] = mapped_column(String(180), default="")
    linked_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (
        ForeignKeyConstraint(["case_id", "organization_id"], ["receivable_cases.id", "receivable_cases.organization_id"], ondelete="CASCADE", name="fk_receivable_evidence_case_org"),
        ForeignKeyConstraint(["artifact_id", "organization_id"], ["evidence_artifacts.id", "evidence_artifacts.organization_id"], name="fk_receivable_evidence_artifact_org"),
        UniqueConstraint("case_id", "artifact_id", "evidence_role", "source_locator", name="uq_receivable_evidence_link"),
        Index("ix_receivable_evidence_case_role", "case_id", "evidence_role"),
    )


class CounterpartyConfirmation(Base):
    """Append-only response by an authenticated counterparty reviewer."""
    __tablename__ = "counterparty_confirmations"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[object] = mapped_column(Uuid)
    counterparty_organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id"))
    confirmed_by_user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    response_status: Mapped[str] = mapped_column(String(32))
    asserted_amount_snapshot: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    confirmed_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    disputed_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="KES")
    response_reference: Mapped[str] = mapped_column(String(160), default="")
    response_note: Mapped[str] = mapped_column(Text, default="")
    evidence_artifact_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (
        ForeignKeyConstraint(["case_id", "organization_id", "counterparty_organization_id"], ["receivable_cases.id", "receivable_cases.organization_id", "receivable_cases.counterparty_organization_id"], ondelete="CASCADE", name="fk_counterparty_confirmation_case_org_counterparty"),
        ForeignKeyConstraint(["counterparty_organization_id", "confirmed_by_user_id"], ["organization_members.organization_id", "organization_members.user_id"], name="fk_counterparty_confirmation_user_org_member"),
        ForeignKeyConstraint(["evidence_artifact_id", "organization_id"], ["evidence_artifacts.id", "evidence_artifacts.organization_id"], name="fk_counterparty_confirmation_artifact_org"),
        CheckConstraint("response_status IN ('accepted', 'partially_accepted', 'disputed', 'rejected', 'needs_information')", name="ck_counterparty_confirmation_status"),
        CheckConstraint("asserted_amount_snapshot >= 0", name="ck_counterparty_confirmation_asserted_nonnegative"),
        CheckConstraint("confirmed_amount IS NULL OR confirmed_amount >= 0", name="ck_counterparty_confirmation_confirmed_nonnegative"),
        CheckConstraint("disputed_amount IS NULL OR disputed_amount >= 0", name="ck_counterparty_confirmation_disputed_nonnegative"),
        Index("ix_counterparty_confirmations_case_time", "case_id", "confirmed_at"),
    )


class CashReceipt(Base):
    """Observed inbound funds only; never a payment instruction."""
    __tablename__ = "cash_receipts"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    source_reference: Mapped[str] = mapped_column(String(160))
    received_on: Mapped[object] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    currency: Mapped[str] = mapped_column(String(3), default="KES")
    payment_rail: Mapped[str] = mapped_column(String(40), default="unknown")
    verification_status: Mapped[str] = mapped_column(String(32), default="seller_attested")
    verified_by: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_artifact_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    recorded_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (
        ForeignKeyConstraint(["evidence_artifact_id", "organization_id"], ["evidence_artifacts.id", "evidence_artifacts.organization_id"], name="fk_cash_receipt_artifact_org"),
        UniqueConstraint("organization_id", "source_reference", name="uq_cash_receipt_org_source_ref"),
        UniqueConstraint("id", "organization_id", name="uq_cash_receipt_id_org"),
        CheckConstraint("amount > 0", name="ck_cash_receipt_amount_positive"),
        CheckConstraint("verification_status IN ('seller_attested', 'bank_evidence_reviewed', 'counterparty_confirmed')", name="ck_cash_receipt_verification_status"),
        CheckConstraint("(verification_status = 'seller_attested' AND verified_by IS NULL AND verified_at IS NULL) OR (verification_status = 'bank_evidence_reviewed' AND verified_by IS NOT NULL AND verified_at IS NOT NULL AND evidence_artifact_id IS NOT NULL) OR (verification_status = 'counterparty_confirmed' AND verified_by IS NOT NULL AND verified_at IS NOT NULL)", name="ck_cash_receipt_verification_requires_review"),
        Index("ix_cash_receipts_org_date", "organization_id", "received_on"),
    )


class CashAllocation(Base):
    __tablename__ = "cash_allocations"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    receipt_id: Mapped[object] = mapped_column(Uuid)
    case_id: Mapped[object] = mapped_column(Uuid)
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    allocated_on: Mapped[object] = mapped_column(Date)
    allocated_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    allocation_reference: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (
        ForeignKeyConstraint(["receipt_id", "organization_id"], ["cash_receipts.id", "cash_receipts.organization_id"], ondelete="CASCADE", name="fk_cash_allocation_receipt_org"),
        ForeignKeyConstraint(["case_id", "organization_id"], ["receivable_cases.id", "receivable_cases.organization_id"], ondelete="CASCADE", name="fk_cash_allocation_case_org"),
        CheckConstraint("amount > 0", name="ck_cash_allocation_amount_positive"),
        Index("ix_cash_allocations_case", "case_id"),
    )


class ReceivableCaseEvent(Base):
    """Append-only workflow event; edits are represented by a new event."""
    __tablename__ = "receivable_case_events"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[object] = mapped_column(Uuid)
    actor_user_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64))
    from_status: Mapped[str] = mapped_column(String(32), default="")
    to_status: Mapped[str] = mapped_column(String(32), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    evidence_artifact_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (
        ForeignKeyConstraint(["case_id", "organization_id"], ["receivable_cases.id", "receivable_cases.organization_id"], ondelete="CASCADE", name="fk_receivable_case_event_case_org"),
        ForeignKeyConstraint(["evidence_artifact_id", "organization_id"], ["evidence_artifacts.id", "evidence_artifacts.organization_id"], name="fk_receivable_case_event_artifact_org"),
        Index("ix_receivable_case_events_case_time", "case_id", "created_at"),
    )


class ReceivablesPilotDecision(Base):
    """Append-only customer discovery outcome recorded by the cooperative account."""
    __tablename__ = "receivables_pilot_decisions"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[object] = mapped_column(Uuid)
    recorded_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    budget_owner_name: Mapped[str] = mapped_column(String(180))
    budget_owner_title: Mapped[str] = mapped_column(String(120), default="")
    budget_owner_organization: Mapped[str] = mapped_column(String(180))
    decision: Mapped[str] = mapped_column(String(32))
    decision_source: Mapped[str] = mapped_column(String(32))
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="KES")
    price_unit: Mapped[str] = mapped_column(String(120), default="")
    decision_note: Mapped[str] = mapped_column(Text, default="")
    next_step: Mapped[str] = mapped_column(String(500), default="")
    evidence_artifact_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    decided_on: Mapped[object] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (
        ForeignKeyConstraint(["case_id", "organization_id"], ["receivable_cases.id", "receivable_cases.organization_id"], name="fk_receivables_pilot_decision_case_org"),
        ForeignKeyConstraint(["evidence_artifact_id", "organization_id"], ["evidence_artifacts.id", "evidence_artifacts.organization_id"], name="fk_receivables_pilot_decision_artifact_org"),
        CheckConstraint("decision IN ('approved_paid_repeat', 'conditional_paid_repeat', 'declined', 'not_decided')", name="ck_receivables_pilot_decision_status"),
        CheckConstraint("decision_source IN ('direct_statement', 'email', 'meeting_notes', 'other')", name="ck_receivables_pilot_decision_source"),
        CheckConstraint("price_amount IS NULL OR price_amount >= 0", name="ck_receivables_pilot_decision_price_nonnegative"),
        CheckConstraint("decision <> 'approved_paid_repeat' OR (price_amount IS NOT NULL AND price_unit <> '' AND evidence_artifact_id IS NOT NULL)", name="ck_receivables_pilot_decision_approved_requires_price_evidence"),
        Index("ix_receivables_pilot_decisions_case_time", "case_id", "created_at"),
    )


class QualityTest(Base):
    __tablename__ = "quality_tests"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    product_lot_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("product_lots.id"), nullable=True)
    feed_batch_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("feed_batches.id"), nullable=True)
    tested_on: Mapped[object] = mapped_column(Date)
    test_type: Mapped[str] = mapped_column(String(100))
    result: Mapped[str] = mapped_column(String(160))
    verified_by: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)


class LaboratoryReport(Base):
    __tablename__ = "laboratory_reports"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    document_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="pending_review")
    uploaded_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class TraceabilityEvent(Base):
    __tablename__ = "traceability_events"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    product_lot_id: Mapped[object] = mapped_column(Uuid, ForeignKey("product_lots.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(60))
    event_date: Mapped[object] = mapped_column(Date)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class AIRequest(Base):
    __tablename__ = "ai_requests"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    request_type: Mapped[str] = mapped_column(String(60))
    model_name: Mapped[str] = mapped_column(String(180))
    prompt_version: Mapped[str] = mapped_column(String(40), default="v1")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(String(40), default="started")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AIResponse(Base):
    __tablename__ = "ai_responses"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    request_id: Mapped[object] = mapped_column(Uuid, ForeignKey("ai_requests.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    structured_output: Mapped[dict] = mapped_column(JSON, default=dict)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AIPromptVersion(Base):
    __tablename__ = "ai_prompt_versions"
    version: Mapped[str] = mapped_column(String(40), primary_key=True)
    description: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AIFeedback(Base):
    __tablename__ = "ai_feedback"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    request_id: Mapped[object] = mapped_column(Uuid, ForeignKey("ai_requests.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(Text, default="")


class DocumentExtraction(Base):
    __tablename__ = "document_extractions"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id"), index=True)
    uploaded_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    extracted_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="pending_review")
    source_model: Mapped[str] = mapped_column(String(180), default="local-text-extractor")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(220))
    source_url: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str] = mapped_column(String(180))
    content: Mapped[str] = mapped_column(Text, default="")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    user_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    farm_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("farms.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(80), default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
