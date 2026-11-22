import re
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class FarmCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    owner_name: str = Field(min_length=2, max_length=180)
    county: str = Field(min_length=2, max_length=80)
    subcounty: str = Field(min_length=2, max_length=80)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    size_acres: float = Field(ge=0)
    farming_system: str = "mixed"
    production_activities: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def coordinates_must_be_a_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Provide both latitude and longitude, or leave both blank")
        return self


class PlotCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    area_acres: float = Field(gt=0)
    crop_type: str = Field(min_length=2, max_length=100)
    planting_date: date | None = None
    harvest_date: date | None = None
    is_feed_crop: bool = False

    @model_validator(mode="after")
    def harvest_follows_planting(self):
        if self.planting_date and self.harvest_date and self.harvest_date < self.planting_date:
            raise ValueError("Harvest date cannot precede planting date")
        return self


class AnimalCreate(BaseModel):
    tag: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    species: str = Field(min_length=2, max_length=60)
    breed: str = ""
    sex: str = "unknown"
    date_of_birth: date | None = None

    @model_validator(mode="after")
    def birth_date_is_not_in_the_future(self):
        if self.date_of_birth and self.date_of_birth > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return self


class HealthEventCreate(BaseModel):
    event_type: str = Field(min_length=2, max_length=60)
    occurred_on: date
    summary: str = Field(min_length=4, max_length=3000)
    observations: dict = Field(default_factory=dict)
    follow_up_on: date | None = None
    verify_record: bool = False

    @model_validator(mode="after")
    def follow_up_follows_event(self):
        if self.follow_up_on and self.follow_up_on < self.occurred_on:
            raise ValueError("Follow-up date cannot precede the health event")
        return self


class HealthFollowUpCreate(BaseModel):
    follow_up_status: Literal["completed", "missed", "unable_to_reach"]
    occurred_on: date
    clinical_outcome: Literal["resolved", "improving", "unchanged", "worsened", "referred", "deceased", "not_assessed"] | None = None
    case_disposition: Literal["closed_recovered", "continue_follow_up", "referred", "closed_other"] | None = None
    treatment_adherence: Literal["as_directed", "partially_followed", "not_started", "unknown"] = "unknown"
    care_plan_summary: str = Field(default="", max_length=2000)
    next_follow_up_on: date | None = None
    case_cost_to_date_kes: Decimal | None = Field(default=None, ge=0, le=9999999999.99)
    milk_price_kes_per_liter: Decimal | None = Field(default=None, gt=0, le=100000)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def outcome_and_next_step_are_consistent(self):
        if self.follow_up_status == "completed":
            if self.clinical_outcome is None or self.case_disposition is None:
                raise ValueError("A completed follow-up requires a clinical outcome and case disposition")
            if self.clinical_outcome == "deceased" and self.case_disposition != "closed_other":
                raise ValueError("A deceased outcome must be closed as a non-recovery")
            if self.case_disposition == "closed_other" and self.clinical_outcome != "deceased":
                raise ValueError("Close as non-recovery only when the recorded outcome is deceased")
            if self.case_disposition == "closed_recovered" and self.clinical_outcome != "resolved":
                raise ValueError("A recovered case can be closed only with a resolved outcome")
            if self.case_disposition == "referred" and self.clinical_outcome != "referred":
                raise ValueError("A referred case must record a referred clinical outcome")
            if self.clinical_outcome == "referred" and self.case_disposition != "referred":
                raise ValueError("A referred clinical outcome requires a referral disposition")
        elif self.clinical_outcome is not None or self.case_disposition is not None:
            raise ValueError("An incomplete follow-up cannot record a clinical outcome or disposition")
        elif len(self.notes.strip()) < 3:
            raise ValueError("Add a short note explaining why the follow-up was missed or not completed")

        needs_next_date = self.follow_up_status != "completed" or self.case_disposition in {"continue_follow_up", "referred"}
        if needs_next_date and self.next_follow_up_on is None:
            raise ValueError("Record the next follow-up date when the case remains open")
        if not needs_next_date and self.next_follow_up_on is not None:
            raise ValueError("A closed case cannot have another scheduled follow-up")
        if self.notes.strip() != self.notes:
            self.notes = self.notes.strip()
        if self.care_plan_summary.strip() != self.care_plan_summary:
            self.care_plan_summary = self.care_plan_summary.strip()
        return self


class FeedBatchCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    quantity_kg: float = Field(gt=0)
    batch_date: date
    plot_id: UUID | None = None
    ingredients: list[str] = Field(default_factory=list)
    storage_conditions: str = ""
    aflatoxin_status: str = "not_tested"


class FeedAllocationCreate(BaseModel):
    feed_batch_id: UUID
    animal_id: UUID
    allocated_kg: float = Field(gt=0)
    allocated_on: date


class ManureCreate(BaseModel):
    collected_on: date
    quantity_kg: float = Field(gt=0)
    source_notes: str = ""


class CompostCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    manure_record_id: UUID | None = None
    created_on: date
    quantity_kg: float = Field(gt=0)
    status: str = "curing"


class CompostApplicationCreate(BaseModel):
    compost_batch_id: UUID
    plot_id: UUID
    applied_on: date
    quantity_kg: float = Field(gt=0)


class ProductionCreate(BaseModel):
    product_type: str = Field(min_length=2, max_length=50)
    quantity: float = Field(gt=0)
    unit: str = Field(min_length=1, max_length=24)
    recorded_on: date
    animal_id: UUID | None = None
    plot_id: UUID | None = None
    quality_measurements: dict = Field(default_factory=dict)


class DeliveryCreate(BaseModel):
    production_record_id: UUID
    buyer_name: str = Field(min_length=2, max_length=160)
    delivery_date: date
    quantity: float = Field(gt=0)
    unit: str = Field(min_length=1, max_length=24)
    status: Literal["pending", "accepted", "rejected"] = "accepted"
    reference: str = ""


class ReconciliationReviewCreate(BaseModel):
    decision: Literal["confirmed", "follow_up"]
    note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def follow_up_requires_a_note(self):
        if self.decision == "follow_up" and len(self.note.strip()) < 3:
            raise ValueError("Add a short note describing the follow-up needed")
        return self


class SettlementReviewCreate(BaseModel):
    decision: Literal["accept_with_note", "follow_up"]
    note: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def normalize_note(self):
        self.note = self.note.strip()
        if len(self.note) < 3:
            raise ValueError("Add a short note explaining the exception review")
        return self


class SettlementApproveCreate(BaseModel):
    note: str = Field(min_length=5, max_length=500)

    @model_validator(mode="after")
    def normalize_note(self):
        self.note = self.note.strip()
        if len(self.note) < 5:
            raise ValueError("Add a close approval note of at least five characters")
        return self


class ConsentCreate(BaseModel):
    scope: Literal["delivery_summary"] = "delivery_summary"
    grantee_email: str | None = Field(default=None, max_length=255)
    grantee_org_id: UUID | None = None

    @model_validator(mode="after")
    def require_one_valid_recipient(self):
        has_email = bool(self.grantee_email and self.grantee_email.strip())
        if has_email == (self.grantee_org_id is not None):
            raise ValueError("Choose exactly one recipient email or cooperative organization")
        if has_email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", self.grantee_email.strip()):
            raise ValueError("Enter a valid recipient email address")
        return self


class AssistantRequest(BaseModel):
    animal_id: UUID
    question: str = Field(min_length=4, max_length=1200)
    allow_external_processing: bool = False


class VeterinaryContactRequestCreate(BaseModel):
    animal_id: UUID | None = None
    message: str = Field(default="", max_length=1200)
    urgency: Literal["routine", "urgent", "emergency"] = "routine"
    preferred_contact_method: Literal["phone_call", "whatsapp", "in_app"] = "phone_call"


class VeterinaryContactRequestUpdate(BaseModel):
    status: Literal["accepted", "declined", "contacted", "cancelled"]


class VeterinaryContactMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    client_message_id: UUID

    @field_validator("body")
    @classmethod
    def trim_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be blank")
        return value


class WhatsAppPairingCreate(BaseModel):
    consent_accepted: bool

    @model_validator(mode="after")
    def require_explicit_consent(self):
        if not self.consent_accepted:
            raise ValueError("WhatsApp consent is required to link this channel")
        return self


class FarmAssistantRequest(BaseModel):
    question: str = Field(min_length=4, max_length=1200)
    allow_external_processing: bool = False


class TerrasRouteRequest(BaseModel):
    message: str = Field(min_length=2, max_length=600)

    @model_validator(mode="after")
    def normalize_message(self):
        self.message = self.message.strip()
        if len(self.message) < 2:
            raise ValueError("Tell Terras what you want to do")
        return self


class ExtractedDocumentDraft(BaseModel):
    document_type: str | None = Field(default=None, max_length=120)
    animal_tag: str | None = Field(default=None, max_length=120)
    event_date: date | None = None
    provider: str | None = Field(default=None, max_length=180)
    key_values: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    extracted_text: str = Field(default="", max_length=30000)
    uncertainties: list[str] = Field(default_factory=list, max_length=30)
