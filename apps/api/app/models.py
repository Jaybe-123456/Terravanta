from datetime import datetime, timezone
from decimal import Decimal
import secrets
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
    __table_args__ = (UniqueConstraint("id", "farm_id", name="uq_animal_health_event_id_farm"),)


class AnimalHealthFollowUp(Base):
    """Append-only veterinarian record of an attempted or completed case follow-up."""
    __tablename__ = "animal_health_follow_ups"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False)
    health_event_id: Mapped[object] = mapped_column(Uuid, nullable=False)
    recorded_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    recorded_by_name: Mapped[str] = mapped_column(String(120), nullable=False)
    follow_up_status: Mapped[str] = mapped_column(String(24), nullable=False)
    occurred_on: Mapped[object] = mapped_column(Date, nullable=False)
    clinical_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    case_disposition: Mapped[str | None] = mapped_column(String(32), nullable=True)
    treatment_adherence: Mapped[str] = mapped_column(String(24), default="unknown", nullable=False)
    care_plan_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    next_follow_up_on: Mapped[object | None] = mapped_column(Date, nullable=True)
    case_cost_to_date_kes: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    case_cost_source: Mapped[str] = mapped_column(String(24), default="not_recorded", nullable=False)
    milk_price_kes_per_liter: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    milk_price_source: Mapped[str] = mapped_column(String(24), default="not_recorded", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (
        ForeignKeyConstraint(
            ["health_event_id", "farm_id"],
            ["animal_health_events.id", "animal_health_events.farm_id"],
            ondelete="CASCADE",
            name="fk_health_follow_up_event_farm",
        ),
        CheckConstraint("follow_up_status IN ('completed', 'missed', 'unable_to_reach')", name="ck_health_follow_up_status"),
        CheckConstraint("clinical_outcome IS NULL OR clinical_outcome IN ('resolved', 'improving', 'unchanged', 'worsened', 'referred', 'deceased', 'not_assessed')", name="ck_health_follow_up_outcome"),
        CheckConstraint("case_disposition IS NULL OR case_disposition IN ('closed_recovered', 'continue_follow_up', 'referred', 'closed_other')", name="ck_health_follow_up_disposition"),
        CheckConstraint("(follow_up_status = 'completed' AND clinical_outcome IS NOT NULL AND case_disposition IS NOT NULL) OR (follow_up_status <> 'completed' AND clinical_outcome IS NULL AND case_disposition IS NULL)", name="ck_health_follow_up_outcome_required"),
        CheckConstraint("(case_disposition = 'closed_recovered' AND clinical_outcome = 'resolved') OR (case_disposition = 'closed_other' AND clinical_outcome = 'deceased') OR (case_disposition = 'referred' AND clinical_outcome = 'referred') OR (case_disposition = 'continue_follow_up' AND clinical_outcome NOT IN ('deceased', 'referred')) OR case_disposition IS NULL", name="ck_health_follow_up_disposition_consistent"),
        CheckConstraint("((follow_up_status <> 'completed' OR case_disposition IN ('continue_follow_up', 'referred')) AND next_follow_up_on IS NOT NULL) OR (follow_up_status = 'completed' AND case_disposition IN ('closed_recovered', 'closed_other') AND next_follow_up_on IS NULL)", name="ck_health_follow_up_next_date"),
        CheckConstraint("treatment_adherence IN ('as_directed', 'partially_followed', 'not_started', 'unknown')", name="ck_health_follow_up_adherence"),
        CheckConstraint("case_cost_to_date_kes IS NULL OR case_cost_to_date_kes >= 0", name="ck_health_follow_up_cost_nonnegative"),
        CheckConstraint("(case_cost_to_date_kes IS NULL AND case_cost_source = 'not_recorded') OR (case_cost_to_date_kes IS NOT NULL AND case_cost_source = 'farmer_reported')", name="ck_health_follow_up_cost_source_matches"),
        CheckConstraint("case_cost_source IN ('not_recorded', 'farmer_reported')", name="ck_health_follow_up_cost_source"),
        CheckConstraint("milk_price_kes_per_liter IS NULL OR milk_price_kes_per_liter > 0", name="ck_health_follow_up_milk_price_positive"),
        CheckConstraint("(milk_price_kes_per_liter IS NULL AND milk_price_source = 'not_recorded') OR (milk_price_kes_per_liter IS NOT NULL AND milk_price_source = 'farmer_reported')", name="ck_health_follow_up_milk_source_matches"),
        CheckConstraint("milk_price_source IN ('not_recorded', 'farmer_reported')", name="ck_health_follow_up_milk_source"),
        Index("ix_health_follow_ups_farm_event_date", "farm_id", "health_event_id", "occurred_on"),
    )


class FarmDomainEvent(Base):
    """Append-only record of a farm fact that can start a bounded workflow."""
    __tablename__ = "farm_domain_events"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[object] = mapped_column(Uuid, nullable=False)
    actor_user_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    __table_args__ = (Index("ix_farm_domain_events_farm_created", "farm_id", "created_at"),)


class WorkflowRun(Base):
    """Durable scheduled step owned by a versioned deterministic workflow."""
    __tablename__ = "workflow_runs"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farm_domain_events.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_type: Mapped[str] = mapped_column(String(80), nullable=False)
    step: Mapped[str] = mapped_column(String(40), nullable=False)
    aggregate_id: Mapped[object] = mapped_column(Uuid, nullable=False)
    due_on: Mapped[object] = mapped_column(Date, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(220), unique=True, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("step IN ('upcoming', 'due', 'overdue')", name="ck_workflow_run_step"),
        CheckConstraint("status IN ('pending', 'completed', 'cancelled', 'failed')", name="ck_workflow_run_status"),
        CheckConstraint("attempts >= 0", name="ck_workflow_run_attempts"),
        Index("ix_workflow_runs_due", "status", "scheduled_at"),
    )


class Notification(Base):
    """In-app notification inbox item; recipient visibility is enforced by RLS."""
    __tablename__ = "notifications"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farm_domain_events.id", ondelete="CASCADE"), nullable=False)
    recipient_user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    notification_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    action_section: Mapped[str] = mapped_column(String(40), default="overview", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(260), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("severity IN ('info', 'medium', 'high')", name="ck_notification_severity"),
        Index("ix_notifications_recipient_created", "recipient_user_id", "created_at"),
    )


class VeterinaryContactRequest(Base):
    """Farmer request for a veterinarian to contact them; this is not an emergency dispatch."""
    __tablename__ = "veterinary_contact_requests"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True)
    animal_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("animals.id", ondelete="SET NULL"), nullable=True, index=True)
    requester_user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    veterinarian_user_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    urgency: Mapped[str] = mapped_column(String(20), default="routine", nullable=False)
    preferred_contact_method: Mapped[str] = mapped_column(String(20), default="phone_call", nullable=False)
    conversation_code: Mapped[str] = mapped_column(String(12), unique=True, default=lambda: secrets.token_hex(6).upper(), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("urgency IN ('routine', 'urgent', 'emergency')", name="ck_vet_contact_urgency"),
        CheckConstraint("preferred_contact_method IN ('phone_call', 'whatsapp', 'in_app')", name="ck_vet_contact_method"),
        CheckConstraint("status IN ('pending', 'accepted', 'declined', 'contacted', 'cancelled')", name="ck_vet_contact_status"),
        Index("ix_vet_contact_farm_status_created", "farm_id", "status", "created_at"),
        Index("ix_vet_contact_vet_status_created", "veterinarian_user_id", "status", "created_at"),
    )


class VeterinaryContactMessage(Base):
    """Immutable conversation entry attached to a farmer-veterinarian request."""
    __tablename__ = "veterinary_contact_messages"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    request_id: Mapped[object] = mapped_column(Uuid, ForeignKey("veterinary_contact_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    farm_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id: Mapped[object] = mapped_column(Uuid, ForeignKey("farm_domain_events.id", ondelete="RESTRICT"), nullable=False)
    sender_user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source_channel: Mapped[str] = mapped_column(String(20), default="in_app", nullable=False)
    external_message_id: Mapped[str | None] = mapped_column(String(180), nullable=True, unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    __table_args__ = (
        CheckConstraint("length(trim(body)) BETWEEN 1 AND 4000", name="ck_vet_contact_message_body"),
        CheckConstraint("source_channel IN ('in_app', 'whatsapp')", name="ck_vet_contact_message_channel"),
        Index("ix_vet_contact_messages_request_created", "request_id", "created_at"),
    )


class WhatsAppPreference(Base):
    """One verified WhatsApp endpoint and explicit channel consent per identity."""
    __tablename__ = "whatsapp_preferences"
    user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    phone_e164: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_version: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    consent_source: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class WhatsAppLinkChallenge(Base):
    """Short-lived one-use challenge; only a hash is stored."""
    __tablename__ = "whatsapp_link_challenges"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    consent_version: Mapped[str] = mapped_column(String(40), nullable=False)
    consent_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (Index("ix_whatsapp_pairing_user_created", "user_id", "created_at"),)


class CommunicationOutbox(Base):
    """Durable, consent-gated WhatsApp delivery job for a conversation message."""
    __tablename__ = "communication_outbox"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    recipient_user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    farm_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("farms.id", ondelete="CASCADE"), nullable=True, index=True)
    request_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("veterinary_contact_requests.id", ondelete="CASCADE"), nullable=True, index=True)
    message_id: Mapped[object | None] = mapped_column(Uuid, ForeignKey("veterinary_contact_messages.id", ondelete="SET NULL"), nullable=True, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    conversation_code: Mapped[str | None] = mapped_column(String(12), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(180), nullable=True, unique=True)
    last_error_code: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(220), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'sending', 'sent', 'delivered', 'read', 'failed', 'cancelled', 'blocked')", name="ck_communication_outbox_status"),
        CheckConstraint("attempts >= 0", name="ck_communication_outbox_attempts"),
        Index("ix_communication_outbox_ready", "status", "next_attempt_at"),
    )


class MetaWebhookEvent(Base):
    """Deduplication and processing receipt; raw Meta payloads are never retained."""
    __tablename__ = "meta_webhook_events"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    provider_event_id: Mapped[str] = mapped_column(String(220), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(20), default="received", nullable=False)
    safe_error_code: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (CheckConstraint("processing_status IN ('received', 'processed', 'ignored', 'failed')", name="ck_meta_webhook_event_status"),)


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
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    retention_basis: Mapped[str] = mapped_column(String(32), default="unreviewed", nullable=False)
    retention_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class SupplyContractReviewEvent(Base):
    """Immutable counterparty decision on a specific supply-contract version."""
    __tablename__ = "supply_contract_review_events"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    contract_id: Mapped[object] = mapped_column(Uuid)
    counterparty_organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    actor_user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(24))
    terms_sha256: Mapped[str] = mapped_column(String(64))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (
        ForeignKeyConstraint(["contract_id", "organization_id"], ["supply_contracts.id", "supply_contracts.organization_id"], ondelete="CASCADE", name="fk_supply_contract_review_event_contract_org"),
        CheckConstraint("decision IN ('confirmed', 'needs_changes')", name="ck_supply_contract_review_event_decision"),
        CheckConstraint("length(terms_sha256) = 64", name="ck_supply_contract_review_event_hash_length"),
        Index("ix_supply_contract_review_events_contract_time", "contract_id", "created_at"),
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
        UniqueConstraint("id", "case_id", "organization_id", name="uq_receivable_case_line_id_case_org"),
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


class CounterpartyCaseEvidence(Base):
    """Private processor-owned evidence explicitly shared into one submitted claim."""
    __tablename__ = "counterparty_case_evidence"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[object] = mapped_column(Uuid)
    counterparty_organization_id: Mapped[object] = mapped_column(Uuid)
    artifact_id: Mapped[object] = mapped_column(Uuid)
    source_locator: Mapped[str] = mapped_column(String(180), default="")
    linked_by: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "organization_id", "counterparty_organization_id"],
            ["receivable_cases.id", "receivable_cases.organization_id", "receivable_cases.counterparty_organization_id"],
            ondelete="CASCADE", name="fk_counterparty_case_evidence_case_org_party",
        ),
        ForeignKeyConstraint(
            ["artifact_id", "counterparty_organization_id"],
            ["evidence_artifacts.id", "evidence_artifacts.organization_id"],
            name="fk_counterparty_case_evidence_artifact_org",
        ),
        ForeignKeyConstraint(
            ["counterparty_organization_id", "linked_by"],
            ["organization_members.organization_id", "organization_members.user_id"],
            name="fk_counterparty_case_evidence_user_org_member",
        ),
        UniqueConstraint("case_id", "artifact_id", "source_locator", name="uq_counterparty_case_evidence_case_artifact_locator"),
        Index("ix_counterparty_case_evidence_case", "case_id", "created_at"),
    )


class CounterpartyLineReview(Base):
    """Append-only processor comparison against one cooperative-asserted source line."""
    __tablename__ = "counterparty_line_reviews"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    organization_id: Mapped[object] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[object] = mapped_column(Uuid)
    case_line_id: Mapped[object] = mapped_column(Uuid)
    counterparty_organization_id: Mapped[object] = mapped_column(Uuid)
    reviewed_by_user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id"))
    review_status: Mapped[str] = mapped_column(String(40))
    seller_amount_snapshot: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    processor_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    processor_direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    seller_direction_snapshot: Mapped[str] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(3), default="KES")
    processor_reference: Mapped[str] = mapped_column(String(160), default="")
    source_locator: Mapped[str] = mapped_column(String(180), default="")
    review_note: Mapped[str] = mapped_column(Text, default="")
    evidence_artifact_id: Mapped[object | None] = mapped_column(Uuid, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (
        ForeignKeyConstraint(
            ["case_id", "organization_id", "counterparty_organization_id"],
            ["receivable_cases.id", "receivable_cases.organization_id", "receivable_cases.counterparty_organization_id"],
            ondelete="CASCADE", name="fk_counterparty_line_review_case_org_party",
        ),
        ForeignKeyConstraint(
            ["case_line_id", "case_id", "organization_id"],
            ["receivable_case_lines.id", "receivable_case_lines.case_id", "receivable_case_lines.organization_id"],
            ondelete="CASCADE", name="fk_counterparty_line_review_case_line",
        ),
        ForeignKeyConstraint(
            ["counterparty_organization_id", "reviewed_by_user_id"],
            ["organization_members.organization_id", "organization_members.user_id"],
            name="fk_counterparty_line_review_user_org_member",
        ),
        ForeignKeyConstraint(
            ["evidence_artifact_id", "counterparty_organization_id"],
            ["evidence_artifacts.id", "evidence_artifacts.organization_id"],
            name="fk_counterparty_line_review_artifact_org",
        ),
        CheckConstraint("review_status IN ('matched', 'value_differs', 'missing_from_processor_record')", name="ck_counterparty_line_review_status"),
        CheckConstraint("seller_amount_snapshot >= 0", name="ck_counterparty_line_review_seller_amount_nonnegative"),
        CheckConstraint("processor_amount IS NULL OR processor_amount >= 0", name="ck_counterparty_line_review_processor_amount_nonnegative"),
        CheckConstraint("seller_direction_snapshot IN ('increase', 'decrease', 'informational')", name="ck_counterparty_line_review_seller_direction"),
        CheckConstraint("processor_direction IS NULL OR processor_direction IN ('increase', 'decrease', 'informational')", name="ck_counterparty_line_review_processor_direction"),
        CheckConstraint("(review_status = 'missing_from_processor_record' AND processor_amount IS NULL AND processor_direction IS NULL) OR (review_status IN ('matched', 'value_differs') AND processor_amount IS NOT NULL AND processor_direction IS NOT NULL)", name="ck_counterparty_line_review_amount_presence"),
        Index("ix_counterparty_line_reviews_case_line_time", "case_line_id", "reviewed_at"),
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


class ClientWriteReceipt(Base):
    """Append-only response receipt for idempotent retry of offline writes."""
    __tablename__ = "client_write_receipts"
    id: Mapped[object] = mapped_column(Uuid, primary_key=True, default=uid)
    actor_user_id: Mapped[object] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (
        UniqueConstraint("actor_user_id", "idempotency_key", name="uq_client_write_receipt_user_key"),
        CheckConstraint("length(request_hash) = 64", name="ck_client_write_receipt_hash_length"),
    )


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
