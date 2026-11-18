import re
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class RelationshipCreate(BaseModel):
    counterparty_name: str = Field(min_length=2, max_length=180)
    relationship_type: Literal["processor", "buyer", "aggregator", "other"] = "processor"
    external_reference: str = Field(min_length=2, max_length=120)
    counterparty_organization_id: UUID | None = None

    @model_validator(mode="after")
    def normalize(self):
        self.counterparty_name = self.counterparty_name.strip()
        self.external_reference = self.external_reference.strip()
        return self


class CaseLineCreate(BaseModel):
    line_type: Literal["accepted_supply", "quality_adjustment", "deduction", "credit_note", "other"]
    direction: Literal["increase", "decrease", "informational"] = "increase"
    source_reference: str = Field(default="", max_length=160)
    occurred_on: date | None = None
    quantity: Decimal | None = Field(default=None, ge=0)
    unit: str = Field(default="", max_length=24)
    amount: Decimal = Field(ge=0, max_digits=16, decimal_places=2)
    source_locator: str = Field(default="", max_length=180)
    evidence_artifact_id: UUID | None = None


class CaseCreate(BaseModel):
    relationship_id: UUID
    contract_id: UUID | None = None
    source_document_type: Literal["invoice", "processor_statement", "delivery_statement", "payout_statement", "other"]
    source_reference: str = Field(min_length=2, max_length=160)
    period_start: date | None = None
    period_end: date | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    due_date_basis: Literal["unknown", "manual_review", "contract"] = "unknown"
    currency: str = Field(default="KES", min_length=3, max_length=3)
    asserted_amount: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    description: str = Field(default="", max_length=4000)
    lines: list[CaseLineCreate] = Field(default_factory=list, max_length=200)
    evidence_artifact_ids: list[UUID] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def check_values(self):
        self.source_reference = self.source_reference.strip()
        self.currency = self.currency.upper()
        if not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise ValueError("Currency must be a three-letter ISO-style code")
        if (self.period_start and self.period_end and self.period_end < self.period_start):
            raise ValueError("Statement period end cannot precede its start")
        if self.due_date is None and self.due_date_basis != "unknown":
            raise ValueError("A due-date basis requires a due date")
        if self.due_date is not None and self.due_date_basis == "unknown":
            raise ValueError("Review the due date and select its basis before recording it")
        if self.invoice_date and self.due_date and self.due_date < self.invoice_date:
            raise ValueError("Due date cannot precede invoice date")
        if self.lines:
            signed_total = sum((line.amount if line.direction == "increase" else -line.amount if line.direction == "decrease" else Decimal("0")) for line in self.lines)
            if abs(signed_total - self.asserted_amount) > Decimal("0.01"):
                raise ValueError("Claim line total must equal the seller-asserted total")
        if len(set(self.evidence_artifact_ids)) != len(self.evidence_artifact_ids):
            raise ValueError("Evidence file IDs must be unique")
        return self


class CounterpartyResponseCreate(BaseModel):
    response_status: Literal["accepted", "partially_accepted", "disputed", "rejected", "needs_information"]
    confirmed_amount: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=2)
    disputed_amount: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=2)
    response_reference: str = Field(default="", max_length=160)
    response_note: str = Field(min_length=2, max_length=4000)

    @model_validator(mode="after")
    def require_response_amounts(self):
        if self.response_status == "accepted" and self.confirmed_amount is None:
            raise ValueError("An accepted response must state the amount accepted")
        if self.response_status == "partially_accepted" and self.confirmed_amount is None:
            raise ValueError("A partially accepted response must state the amount accepted")
        return self


class ReceiptCreate(BaseModel):
    source_reference: str = Field(min_length=2, max_length=160)
    received_on: date
    amount: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    currency: str = Field(default="KES", min_length=3, max_length=3)
    payment_rail: str = Field(default="unknown", max_length=40)
    verification_status: Literal["seller_attested", "bank_evidence_reviewed"] = "seller_attested"
    evidence_artifact_id: UUID | None = None
    allocate_amount: Decimal | None = Field(default=None, gt=0, max_digits=16, decimal_places=2)

    @model_validator(mode="after")
    def check_verification(self):
        self.source_reference = self.source_reference.strip()
        self.currency = self.currency.upper()
        if self.verification_status == "bank_evidence_reviewed" and self.evidence_artifact_id is None:
            raise ValueError("Reviewed bank evidence requires an attached bank or payment record")
        if not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise ValueError("Currency must be a three-letter code")
        return self

class AllocationCreate(BaseModel):
    receipt_id: UUID
    amount: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    allocated_on: date
    allocation_reference: str = Field(default="", max_length=160)


class PilotDecisionCreate(BaseModel):
    budget_owner_name: str = Field(min_length=2, max_length=180)
    budget_owner_title: str = Field(default="", max_length=120)
    budget_owner_organization: str = Field(min_length=2, max_length=180)
    decision: Literal["approved_paid_repeat", "conditional_paid_repeat", "declined", "not_decided"]
    decision_source: Literal["direct_statement", "email", "meeting_notes", "other"]
    price_amount: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=2)
    currency: str = Field(default="KES", min_length=3, max_length=3)
    price_unit: str = Field(default="", max_length=120)
    decision_note: str = Field(min_length=3, max_length=4000)
    next_step: str = Field(default="", max_length=500)
    evidence_artifact_id: UUID | None = None
    decided_on: date

    @model_validator(mode="after")
    def approved_repeat_needs_pricing(self):
        self.budget_owner_name = self.budget_owner_name.strip()
        self.budget_owner_organization = self.budget_owner_organization.strip()
        self.currency = self.currency.upper()
        if self.decision == "approved_paid_repeat" and (self.price_amount is None or not self.price_unit.strip()):
            raise ValueError("Record the approved repeat price and its unit")
        if self.decision == "approved_paid_repeat" and self.evidence_artifact_id is None:
            raise ValueError("Attach an approval artifact such as a signed quote, purchase order, or decision email")
        if not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise ValueError("Currency must be a three-letter code")
        return self
