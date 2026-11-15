from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
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


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(40), primary_key=True)
    user: Mapped[User] = relationship(back_populates="roles")


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
