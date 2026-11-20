"""Server-authorized receivables register and counterparty response workflow."""

import csv
import hashlib
import io
import json
import logging
import re
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import PurePath
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import settings
from .evidence_storage import delete_private, get_private, put_private, safe_key, storage_ready
from .models import (
    AuditLog, CashAllocation, CashReceipt, CounterpartyConfirmation, CounterpartyRelationship,
    EvidenceArtifact, Organization, OrganizationMember, ReceivableCase, ReceivableCaseEvent,
    ReceivableCaseLine, ReceivableEvidenceLink, ReceivablesPilotDecision, SupplyContract, User, UserRole,
)
from .receivables_schemas import (
    AllocationCreate, CaseCreate, CounterpartyResponseCreate, PilotDecisionCreate, ReceiptCreate, RelationshipCreate,
)
from .security import current_user, get_scoped_db, require_role

log = logging.getLogger("terravanta.receivables")
router = APIRouter(prefix="/api/v1", tags=["receivables"])
NBO = ZoneInfo("Africa/Nairobi")
ALLOWED_UPLOADS = {".pdf": ("application/pdf", b"%PDF-"), ".csv": ("text/csv", None)}
MAX_EXPORT_BYTES = 60_000_000


def _member_org(db: Session, user: User, *, role: str, kind: str) -> Organization:
    require_role(db, user, role)
    rows = db.query(Organization).join(
        OrganizationMember, OrganizationMember.organization_id == Organization.id,
    ).filter(
        OrganizationMember.user_id == user.id,
        OrganizationMember.role == role,
        Organization.kind == kind,
    ).distinct().all()
    if len(rows) != 1:
        raise HTTPException(403, f"Account must belong to exactly one {kind} organization")
    return rows[0]


def _seller_org(db: Session, user: User) -> Organization:
    return _member_org(db, user, role="cooperative_admin", kind="cooperative")


def _processor_org(db: Session, user: User) -> Organization:
    return _member_org(db, user, role="processor_admin", kind="processor")


def _event(db: Session, case: ReceivableCase, actor: User | None, event_type: str,
           from_status: str = "", to_status: str = "", note: str = "", evidence_id: UUID | None = None):
    db.add(ReceivableCaseEvent(
        organization_id=case.organization_id, case_id=case.id,
        actor_user_id=actor.id if actor else None, event_type=event_type,
        from_status=from_status, to_status=to_status, note=note,
        evidence_artifact_id=evidence_id,
    ))
    if actor:
        db.add(AuditLog(
            user_id=actor.id, action=f"receivable.{event_type}", entity_type="receivable_case",
            entity_id=str(case.id), metadata_json={"organization_id": str(case.organization_id)},
        ))


def _seller_case(db: Session, user: User, case_id: UUID) -> ReceivableCase:
    organization = _seller_org(db, user)
    case = db.query(ReceivableCase).filter_by(id=case_id, organization_id=organization.id).first()
    if not case:
        raise HTTPException(404, "Claim was not found in this cooperative workspace")
    return case


def _processor_case(db: Session, user: User, case_id: UUID) -> ReceivableCase:
    organization = _processor_org(db, user)
    case = db.query(ReceivableCase).filter_by(
        id=case_id, counterparty_organization_id=organization.id,
    ).filter(ReceivableCase.status != "draft").first()
    if not case or case.status == "asserted":
        raise HTTPException(404, "Submitted claim was not found for this processor")
    return case


def _latest_confirmation(db: Session, case_id: UUID):
    return db.query(CounterpartyConfirmation).filter(
        CounterpartyConfirmation.case_id == case_id,
        CounterpartyConfirmation.response_status != "needs_information",
    ).order_by(
        CounterpartyConfirmation.confirmed_at.desc(), CounterpartyConfirmation.created_at.desc(),
    ).first()


def _apply_reviewed_receipt_status(db: Session, case: ReceivableCase) -> None:
    reviewed = db.query(func.coalesce(func.sum(CashAllocation.amount), 0)).join(
        CashReceipt, CashReceipt.id == CashAllocation.receipt_id,
    ).filter(
        CashAllocation.case_id == case.id,
        CashAllocation.organization_id == case.organization_id,
        CashReceipt.verification_status.in_(("bank_evidence_reviewed", "counterparty_confirmed")),
    ).scalar()
    reviewed_total = Decimal(str(reviewed or 0))
    if reviewed_total >= case.asserted_amount:
        case.status = "paid"
    elif reviewed_total > 0 and case.status in {"submitted", "counterparty_confirmed", "partially_confirmed"}:
        case.status = "partially_paid"


def _aging(case: ReceivableCase, today: date) -> dict:
    if case.due_date is None or case.due_date_basis == "unknown":
        if case.invoice_date is None:
            return {"as_of": today.isoformat(), "bucket": "date_unknown", "days_past_due": None, "days_since_invoice": None}
        if case.invoice_date > today:
            return {"as_of": today.isoformat(), "bucket": "invoice_not_yet_issued", "days_past_due": None, "days_since_invoice": 0}
        days = max(0, (today - case.invoice_date).days)
        bucket = "invoice_today" if days == 0 else "invoice_1_30" if days <= 30 else "invoice_31_60" if days <= 60 else "invoice_61_90" if days <= 90 else "invoice_90_plus"
        return {"as_of": today.isoformat(), "bucket": bucket, "days_past_due": None, "days_since_invoice": days}
    if case.due_date > today:
        return {"as_of": today.isoformat(), "bucket": "not_yet_due", "days_past_due": 0, "days_since_invoice": max(0, (today - case.invoice_date).days) if case.invoice_date else None}
    days = (today - case.due_date).days
    bucket = "due_today" if days == 0 else "overdue_1_30" if days <= 30 else "overdue_31_60" if days <= 60 else "overdue_61_90" if days <= 90 else "overdue_90_plus"
    return {"as_of": today.isoformat(), "bucket": bucket, "days_past_due": days, "days_since_invoice": max(0, (today - case.invoice_date).days) if case.invoice_date else None}


def _case_json(db: Session, case: ReceivableCase, *, include_private: bool = True) -> dict:
    lines = db.query(ReceivableCaseLine).filter_by(case_id=case.id, organization_id=case.organization_id).order_by(ReceivableCaseLine.line_number).all()
    links = db.query(ReceivableEvidenceLink).filter_by(case_id=case.id, organization_id=case.organization_id).all()
    evidence = []
    for link in links:
        artifact = db.query(EvidenceArtifact).filter_by(id=link.artifact_id, organization_id=case.organization_id).first()
        if artifact:
            evidence.append({
                "id": str(artifact.id), "filename": artifact.filename,
                "artifact_type": artifact.artifact_type, "media_type": artifact.media_type,
                "sha256": artifact.sha256, "source_party": artifact.source_party,
                "source_reference": artifact.source_reference, "size_bytes": (artifact.source_metadata or {}).get("size_bytes"),
                "evidence_role": link.evidence_role, "source_locator": link.source_locator,
                "created_at": artifact.created_at.isoformat(),
            })
    confirmations = db.query(CounterpartyConfirmation).filter_by(case_id=case.id).order_by(CounterpartyConfirmation.confirmed_at).all()
    decisions = db.query(ReceivablesPilotDecision).filter_by(case_id=case.id, organization_id=case.organization_id).order_by(ReceivablesPilotDecision.created_at).all()
    receipts = db.query(CashReceipt).join(CashAllocation, CashAllocation.receipt_id == CashReceipt.id).filter(
        CashAllocation.case_id == case.id, CashAllocation.organization_id == case.organization_id,
    ).distinct().all()
    allocations = db.query(CashAllocation).filter_by(case_id=case.id, organization_id=case.organization_id).all()
    latest = next((row for row in reversed(confirmations) if row.response_status != "needs_information"), None)
    receipt_by_id = {row.id: row for row in receipts}
    reported_received = sum((allocation.amount for allocation in allocations), Decimal("0.00"))
    verified_received = sum((allocation.amount for allocation in allocations if receipt_by_id.get(allocation.receipt_id) and receipt_by_id[allocation.receipt_id].verification_status in {"bank_evidence_reviewed", "counterparty_confirmed"}), Decimal("0.00"))
    today = datetime.now(NBO).date()
    aging = _aging(case, today)
    confirmed_amount = latest.confirmed_amount if latest and latest.confirmed_amount is not None else None
    return {
        "id": str(case.id), "organization_id": str(case.organization_id),
        "relationship_id": str(case.relationship_id),
        "counterparty_organization_id": str(case.counterparty_organization_id) if case.counterparty_organization_id else None,
        "contract_id": str(case.contract_id) if case.contract_id else None,
        "source_document_type": case.source_document_type, "source_reference": case.source_reference,
        "period_start": case.period_start.isoformat() if case.period_start else None,
        "period_end": case.period_end.isoformat() if case.period_end else None,
        "invoice_date": case.invoice_date.isoformat() if case.invoice_date else None,
        "due_date": case.due_date.isoformat() if case.due_date else None,
        "due_date_basis": case.due_date_basis,
        "due_date_reviewed_at": case.due_date_reviewed_at.isoformat() if case.due_date_reviewed_at else None,
        "currency": case.currency, "asserted_amount": str(case.asserted_amount),
        "status": case.status, "description": case.description,
        "created_at": case.created_at.isoformat(), "updated_at": case.updated_at.isoformat(),
        "aging": aging,
        "amounts": {
            "seller_asserted": str(case.asserted_amount),
            "latest_processor_confirmed": str(confirmed_amount) if confirmed_amount is not None else None,
            "latest_processor_disputed": str(latest.disputed_amount) if latest and latest.disputed_amount is not None else None,
            "seller_reported_receipts_allocated": str(reported_received),
            "evidence_reviewed_receipts_allocated": str(verified_received),
            "seller_asserted_less_reported_receipts": str(max(Decimal("0.00"), case.asserted_amount - reported_received)),
            "processor_confirmed_less_reviewed_receipts": str(max(Decimal("0.00"), confirmed_amount - verified_received)) if confirmed_amount is not None else None,
        },
        "lines": [{
            "id": str(row.id), "line_number": row.line_number, "line_type": row.line_type,
            "direction": row.direction, "source_reference": row.source_reference,
            "occurred_on": row.occurred_on.isoformat() if row.occurred_on else None,
            "quantity": str(row.quantity) if row.quantity is not None else None,
            "unit": row.unit, "amount": str(row.amount), "currency": row.currency,
            "source_locator": row.source_locator, "provenance_class": row.provenance_class,
            "evidence_artifact_id": str(row.evidence_artifact_id) if row.evidence_artifact_id else None,
        } for row in lines],
        "evidence": evidence if include_private else [{k: v for k, v in item.items() if k not in {"source_reference"}} for item in evidence],
        "confirmations": [{
            "id": str(row.id), "response_status": row.response_status,
            "asserted_amount_snapshot": str(row.asserted_amount_snapshot),
            "confirmed_amount": str(row.confirmed_amount) if row.confirmed_amount is not None else None,
            "disputed_amount": str(row.disputed_amount) if row.disputed_amount is not None else None,
            "currency": row.currency, "response_reference": row.response_reference,
            "response_note": row.response_note, "confirmed_at": row.confirmed_at.isoformat(),
        } for row in confirmations],
        "pilot_decisions": [{
            "id": str(row.id), "budget_owner_name": row.budget_owner_name,
            "budget_owner_title": row.budget_owner_title,
            "budget_owner_organization": row.budget_owner_organization,
            "decision": row.decision, "decision_source": row.decision_source,
            "price_amount": str(row.price_amount) if row.price_amount is not None else None,
            "currency": row.currency, "price_unit": row.price_unit,
            "decision_note": row.decision_note, "next_step": row.next_step,
            "evidence_artifact_id": str(row.evidence_artifact_id) if row.evidence_artifact_id else None,
            "decided_on": row.decided_on.isoformat(), "created_at": row.created_at.isoformat(),
        } for row in decisions],
        "receipts": [{
            "id": str(row.id), "source_reference": row.source_reference,
            "received_on": row.received_on.isoformat(), "amount": str(row.amount),
            "currency": row.currency, "payment_rail": row.payment_rail,
            "verification_status": row.verification_status,
        } for row in receipts],
        "allocations": [{"id": str(row.id), "receipt_id": str(row.receipt_id), "amount": str(row.amount), "allocated_on": row.allocated_on.isoformat(), "allocation_reference": row.allocation_reference} for row in allocations],
    }


def _case_with_events(db: Session, case: ReceivableCase) -> dict:
    result = _case_json(db, case)
    events = db.query(ReceivableCaseEvent).filter_by(case_id=case.id, organization_id=case.organization_id).order_by(ReceivableCaseEvent.created_at).all()
    result["events"] = [{
        "id": str(event.id), "event_type": event.event_type, "from_status": event.from_status,
        "to_status": event.to_status, "note": event.note, "created_at": event.created_at.isoformat(),
    } for event in events]
    return result


def _artifact(db: Session, org_id: UUID, artifact_id: UUID) -> EvidenceArtifact:
    artifact = db.query(EvidenceArtifact).filter_by(id=artifact_id, organization_id=org_id).first()
    if not artifact:
        raise HTTPException(404, "Evidence file was not found in this organization")
    return artifact


def _verified_artifact_bytes(artifact: EvidenceArtifact) -> bytes:
    try:
        content = get_private(artifact.storage_key)
    except Exception as exc:
        log.exception("Private evidence read failed (%s)", type(exc).__name__)
        raise HTTPException(503, "Evidence file is temporarily unavailable") from exc
    if hashlib.sha256(content).hexdigest() != artifact.sha256:
        log.error("Evidence integrity mismatch for artifact %s", artifact.id)
        raise HTTPException(503, "Evidence integrity check failed; the file was withheld")
    return content


def _csv_text(rows: list[dict]) -> str:
    if not rows:
        return ""
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        safe = {}
        for key, value in row.items():
            text = "" if value is None else str(value)
            if text.startswith(("=", "+", "-", "@", "\t", "\r")):
                text = "'" + text
            safe[key] = text
        writer.writerow(safe)
    return stream.getvalue()


@router.get("/cooperative/receivables/summary")
def seller_summary(user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    org = _seller_org(db, user)
    cases = db.query(ReceivableCase).filter_by(organization_id=org.id).all()
    buckets: dict[str, int] = {}
    seller_balance_by_bucket: dict[str, Decimal] = {}
    confirmed_balance_by_bucket: dict[str, Decimal] = {}
    asserted_total = Decimal("0.00")
    seller_outstanding_total = Decimal("0.00")
    confirmed_total = Decimal("0.00")
    confirmed_outstanding_total = Decimal("0.00")
    for case in cases:
        if case.status in {"draft", "paid", "closed"}:
            continue
        aging = _aging(case, datetime.now(NBO).date())
        buckets[aging["bucket"]] = buckets.get(aging["bucket"], 0) + 1
        reported_receipts = db.query(func.coalesce(func.sum(CashAllocation.amount), 0)).filter_by(
            case_id=case.id, organization_id=org.id,
        ).scalar()
        seller_balance = max(Decimal("0.00"), case.asserted_amount - Decimal(str(reported_receipts or 0)))
        seller_balance_by_bucket[aging["bucket"]] = seller_balance_by_bucket.get(aging["bucket"], Decimal("0.00")) + seller_balance
        asserted_total += case.asserted_amount
        seller_outstanding_total += seller_balance
        latest = _latest_confirmation(db, case.id)
        if latest and latest.confirmed_amount is not None:
            reviewed_receipts = db.query(func.coalesce(func.sum(CashAllocation.amount), 0)).join(
                CashReceipt, CashReceipt.id == CashAllocation.receipt_id,
            ).filter(
                CashAllocation.case_id == case.id, CashAllocation.organization_id == org.id,
                CashReceipt.verification_status.in_(("bank_evidence_reviewed", "counterparty_confirmed")),
            ).scalar()
            confirmed_balance = max(Decimal("0.00"), latest.confirmed_amount - Decimal(str(reviewed_receipts or 0)))
            confirmed_balance_by_bucket[aging["bucket"]] = confirmed_balance_by_bucket.get(aging["bucket"], Decimal("0.00")) + confirmed_balance
            confirmed_total += latest.confirmed_amount
            confirmed_outstanding_total += confirmed_balance
    return {
        "organization_id": str(org.id), "claim_count": len(cases), "open_claim_count": sum(buckets.values()),
        "seller_asserted_total": str(asserted_total), "seller_reported_outstanding_total": str(seller_outstanding_total),
        "latest_processor_confirmed_total": str(confirmed_total), "processor_confirmed_outstanding_total": str(confirmed_outstanding_total),
        "aging_buckets": buckets,
        "seller_asserted_balance_by_age_bucket": {key: str(value) for key, value in seller_balance_by_bucket.items()},
        "processor_confirmed_balance_by_age_bucket": {key: str(value) for key, value in confirmed_balance_by_bucket.items()},
        "as_of": datetime.now(NBO).date().isoformat(),
    }


@router.get("/cooperative/receivables/relationships")
def seller_relationships(user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    org = _seller_org(db, user)
    rows = db.query(CounterpartyRelationship).filter_by(organization_id=org.id).order_by(CounterpartyRelationship.counterparty_name).all()
    return [{"id": str(r.id), "counterparty_name": r.counterparty_name, "relationship_type": r.relationship_type,
             "counterparty_organization_id": str(r.counterparty_organization_id) if r.counterparty_organization_id else None,
             "external_reference": r.external_reference, "status": r.status} for r in rows]


@router.post("/cooperative/receivables/relationships", status_code=201)
def create_relationship(body: RelationshipCreate, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    org = _seller_org(db, user)
    counterparty = db.get(Organization, body.counterparty_organization_id) if body.counterparty_organization_id else None
    if body.counterparty_organization_id and not counterparty:
        raise HTTPException(404, "Counterparty organization not found")
    if body.relationship_type == "processor" and counterparty and counterparty.kind != "processor":
        raise HTTPException(422, "Select a registered processor organization")
    if db.query(CounterpartyRelationship.id).filter_by(organization_id=org.id, external_reference=body.external_reference).first():
        raise HTTPException(409, "That processor account reference is already linked in this cooperative")
    row = CounterpartyRelationship(
        organization_id=org.id, counterparty_organization_id=body.counterparty_organization_id,
        counterparty_name=body.counterparty_name, relationship_type=body.relationship_type,
        external_reference=body.external_reference,
        status="active" if body.counterparty_organization_id else "pending", created_by=user.id,
    )
    db.add(row)
    db.flush()
    db.add(AuditLog(user_id=user.id, action="receivable.relationship_created", entity_type="counterparty_relationship", entity_id=str(row.id), metadata_json={"organization_id": str(org.id)}))
    db.commit()
    return {"id": str(row.id), "counterparty_name": row.counterparty_name, "relationship_type": row.relationship_type,
            "counterparty_organization_id": str(row.counterparty_organization_id) if row.counterparty_organization_id else None,
            "external_reference": row.external_reference, "status": row.status}


@router.get("/cooperative/receivables/cases")
def seller_cases(user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    org = _seller_org(db, user)
    rows = db.query(ReceivableCase).filter_by(organization_id=org.id).order_by(ReceivableCase.created_at.desc()).all()
    return [_case_json(db, row) for row in rows]


@router.post("/cooperative/receivables/cases", status_code=201)
def create_case(body: CaseCreate, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    org = _seller_org(db, user)
    relation = db.query(CounterpartyRelationship).filter_by(id=body.relationship_id, organization_id=org.id).first()
    if not relation:
        raise HTTPException(404, "Processor relationship was not found in this cooperative")
    if relation.relationship_type != "processor":
        raise HTTPException(422, "Receivables claims must be linked to a processor relationship")
    if db.query(ReceivableCase.id).filter_by(organization_id=org.id, source_reference=body.source_reference).first():
        raise HTTPException(409, "That statement or invoice reference is already in this cooperative's claim register")
    if body.due_date_basis == "contract":
        if not body.contract_id:
            raise HTTPException(422, "Select the reviewed supply contract supporting the due date")
        contract = db.query(SupplyContract).filter_by(id=body.contract_id, organization_id=org.id, relationship_id=relation.id).first()
        if not contract or contract.terms_review_status != "counterparty_confirmed" or contract.status != "active":
            raise HTTPException(422, "Only an active, counterparty-confirmed contract can set a contract due date")
    elif body.contract_id:
        contract = db.query(SupplyContract).filter_by(id=body.contract_id, organization_id=org.id, relationship_id=relation.id).first()
        if not contract:
            raise HTTPException(404, "Supply contract was not found for this relationship")
    for artifact_id in body.evidence_artifact_ids:
        _artifact(db, org.id, artifact_id)
    for line in body.lines:
        if line.evidence_artifact_id:
            _artifact(db, org.id, line.evidence_artifact_id)
    case = ReceivableCase(
        organization_id=org.id, relationship_id=relation.id, contract_id=body.contract_id,
        counterparty_organization_id=relation.counterparty_organization_id,
        source_document_type=body.source_document_type, source_reference=body.source_reference,
        period_start=body.period_start, period_end=body.period_end, invoice_date=body.invoice_date,
        due_date=body.due_date, due_date_basis=body.due_date_basis,
        due_date_reviewed_by=user.id if body.due_date else None,
        due_date_reviewed_at=datetime.now(timezone.utc) if body.due_date else None,
        currency=body.currency, asserted_amount=body.asserted_amount,
        description=body.description.strip(), status="draft", created_by=user.id,
    )
    db.add(case)
    db.flush()
    for index, line in enumerate(body.lines, start=1):
        db.add(ReceivableCaseLine(
            organization_id=org.id, case_id=case.id, line_number=index,
            line_type=line.line_type, direction=line.direction, source_reference=line.source_reference,
            occurred_on=line.occurred_on, quantity=line.quantity, unit=line.unit,
            amount=line.amount, currency=body.currency, evidence_artifact_id=line.evidence_artifact_id,
            source_locator=line.source_locator, provenance_class="seller_attested", created_by=user.id,
        ))
        if line.evidence_artifact_id:
            db.add(ReceivableEvidenceLink(
                organization_id=org.id, case_id=case.id, artifact_id=line.evidence_artifact_id,
                evidence_role="line_support", source_locator=line.source_locator or f"line:{index}", linked_by=user.id,
            ))
    for artifact_id in body.evidence_artifact_ids:
        artifact = _artifact(db, org.id, artifact_id)
        db.add(ReceivableEvidenceLink(organization_id=org.id, case_id=case.id, artifact_id=artifact.id,
                                      evidence_role="claim_support", linked_by=user.id))
    _event(db, case, user, "case_created", "", "draft", "Seller-asserted claim draft created")
    db.commit()
    return _case_with_events(db, case)


@router.get("/cooperative/receivables/cases/{case_id}")
def seller_case(case_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    return _case_with_events(db, _seller_case(db, user, case_id))


@router.post("/cooperative/receivables/cases/{case_id}/evidence", status_code=201)
async def upload_case_evidence(
    case_id: UUID,
    file: UploadFile = File(...),
    artifact_type: str = Form("processor_statement"),
    source_reference: str = Form(""),
    user: User = Depends(current_user), db: Session = Depends(get_scoped_db),
):
    case = _seller_case(db, user, case_id)
    if case.status in {"paid", "closed"}:
        raise HTTPException(409, "Evidence cannot be added to a closed claim")
    if not storage_ready():
        raise HTTPException(503, "Private production evidence storage is not configured; set S3-compatible storage before upload")
    filename = PurePath((file.filename or "evidence").replace("\\", "/")).name[:255]
    suffix = PurePath(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOADS:
        raise HTTPException(415, "Only PDF and CSV evidence files are accepted")
    content = await file.read(settings.evidence_max_file_bytes + 1)
    await file.close()
    if not content or len(content) > settings.evidence_max_file_bytes:
        raise HTTPException(413, f"Evidence file must be 1 byte to {settings.evidence_max_file_bytes} bytes")
    declared, signature = ALLOWED_UPLOADS[suffix]
    if signature and not content.startswith(signature):
        raise HTTPException(415, "File contents do not match the declared PDF format")
    if suffix == ".csv":
        try:
            text = content.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError as exc:
            raise HTTPException(415, "CSV evidence must be valid UTF-8 text") from exc
        if "\x00" in text:
            raise HTTPException(415, "CSV evidence contains invalid binary data")
    artifact_id = uuid4()
    key = safe_key(case.organization_id, case.id, artifact_id, suffix)
    sha256 = hashlib.sha256(content).hexdigest()
    try:
        put_private(key, content, declared)
    except Exception as exc:
        log.exception("Private evidence write failed (%s)", type(exc).__name__)
        raise HTTPException(503, "Evidence storage is temporarily unavailable") from exc
    row = EvidenceArtifact(
        id=artifact_id, organization_id=case.organization_id, uploaded_by=user.id,
        source_party="seller", source_system="manual_upload", source_reference=source_reference.strip()[:160],
        filename=filename, media_type=declared, artifact_type=artifact_type.strip()[:60] or "source_document",
        sha256=sha256, storage_key=key, sensitivity="confidential",
        source_metadata={"size_bytes": len(content), "validation": "extension_magic_utf8"},
    )
    db.add(row)
    db.add(ReceivableEvidenceLink(organization_id=case.organization_id, case_id=case.id,
                                  artifact_id=artifact_id, evidence_role="claim_support", linked_by=user.id))
    _event(db, case, user, "evidence_attached", case.status, case.status, "Private evidence file attached", artifact_id)
    try:
        db.commit()
    except Exception:
        db.rollback()
        try:
            delete_private(key)
        except Exception:
            log.exception("Could not remove orphaned evidence object after database failure")
        raise
    return {"id": str(row.id), "filename": row.filename, "media_type": row.media_type,
            "artifact_type": row.artifact_type, "sha256": row.sha256,
            "size_bytes": len(content), "created_at": row.created_at.isoformat()}


@router.post("/cooperative/receivables/cases/{case_id}/assert")
def assert_case(case_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    case = _seller_case(db, user, case_id)
    if case.status != "draft":
        raise HTTPException(409, "Only a draft claim can be asserted")
    if not db.query(ReceivableEvidenceLink.id).filter_by(case_id=case.id, organization_id=case.organization_id).first():
        raise HTTPException(422, "Attach at least one source document before asserting the claim")
    case.status = "asserted"
    case.updated_at = datetime.now(timezone.utc)
    _event(db, case, user, "claim_asserted", "draft", "asserted", "Cooperative asserted the amount and attached its supporting records")
    db.commit()
    return _case_with_events(db, case)


@router.post("/cooperative/receivables/cases/{case_id}/submit")
def submit_case(case_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    case = _seller_case(db, user, case_id)
    if case.status != "asserted":
        raise HTTPException(409, "Assert the claim before submitting it to the processor")
    relation = db.query(CounterpartyRelationship).filter_by(id=case.relationship_id, organization_id=case.organization_id).first()
    processor = db.get(Organization, relation.counterparty_organization_id) if relation and relation.counterparty_organization_id else None
    if not relation or relation.status != "active" or not processor or processor.kind != "processor":
        raise HTTPException(422, "Link an active, registered processor organization before submission")
    case.counterparty_organization_id = processor.id
    case.status = "submitted"
    case.updated_at = datetime.now(timezone.utc)
    _event(db, case, user, "claim_submitted", "asserted", "submitted", "Claim submitted to processor workspace")
    db.commit()
    return _case_with_events(db, case)


@router.get("/processor/receivables/cases")
def processor_cases(user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    org = _processor_org(db, user)
    rows = db.query(ReceivableCase).filter(
        ReceivableCase.counterparty_organization_id == org.id,
        ReceivableCase.status != "draft", ReceivableCase.status != "asserted",
    ).order_by(ReceivableCase.created_at.desc()).all()
    return [_case_json(db, row, include_private=False) for row in rows]


@router.get("/processor/receivables/cases/{case_id}")
def processor_case(case_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    return _case_with_events(db, _processor_case(db, user, case_id))


@router.post("/processor/receivables/cases/{case_id}/responses", status_code=201)
def respond_to_case(case_id: UUID, body: CounterpartyResponseCreate, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    case = _processor_case(db, user, case_id)
    if case.status in {"paid", "closed"}:
        raise HTTPException(409, "This claim is paid or closed and no longer accepts processor responses")
    case = db.query(ReceivableCase).filter_by(id=case.id).with_for_update().one()
    if body.confirmed_amount is not None and body.confirmed_amount > case.asserted_amount:
        raise HTTPException(422, "Confirmed amount cannot exceed the amount asserted by the cooperative")
    if body.disputed_amount is not None and body.disputed_amount > case.asserted_amount:
        raise HTTPException(422, "Disputed amount cannot exceed the amount asserted by the cooperative")
    if body.response_status == "accepted" and body.confirmed_amount != case.asserted_amount:
        raise HTTPException(422, "For a full acceptance, confirmed amount must equal the claim amount")
    if body.response_status == "partially_accepted" and (body.confirmed_amount is None or body.confirmed_amount >= case.asserted_amount):
        raise HTTPException(422, "A partial acceptance must be less than the claim amount")
    if body.confirmed_amount is not None and body.disputed_amount is not None and body.confirmed_amount + body.disputed_amount > case.asserted_amount:
        raise HTTPException(422, "Confirmed and disputed amounts cannot exceed the seller-asserted total")
    response = CounterpartyConfirmation(
        organization_id=case.organization_id, case_id=case.id,
        counterparty_organization_id=case.counterparty_organization_id, confirmed_by_user_id=user.id,
        response_status=body.response_status, asserted_amount_snapshot=case.asserted_amount,
        confirmed_amount=body.confirmed_amount, disputed_amount=body.disputed_amount,
        currency=case.currency, response_reference=body.response_reference.strip(),
        response_note=body.response_note.strip(),
    )
    previous = case.status
    if body.response_status == "accepted":
        case.status = "counterparty_confirmed"
    elif body.response_status == "partially_accepted":
        case.status = "partially_confirmed"
    elif body.response_status in {"disputed", "rejected"}:
        case.status = "disputed"
    db.add(response)
    case.updated_at = datetime.now(timezone.utc)
    _event(db, case, user, "processor_response_recorded", previous, case.status,
           f"Processor response recorded: {body.response_status}; reference {body.response_reference.strip()[:160]}")
    db.add(AuditLog(user_id=user.id, action="receivable.processor_response", entity_type="receivable_case",
                    entity_id=str(case.id), metadata_json={"counterparty_organization_id": str(case.counterparty_organization_id), "response_status": body.response_status}))
    db.commit()
    return _case_with_events(db, case)


@router.post("/cooperative/receivables/cases/{case_id}/receipts", status_code=201)
def record_receipt(case_id: UUID, body: ReceiptCreate, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    organization = _seller_org(db, user)
    case = db.query(ReceivableCase).filter_by(id=case_id, organization_id=organization.id).with_for_update().first()
    if not case:
        raise HTTPException(404, "Claim was not found in this cooperative workspace")
    if case.status in {"paid", "closed"}:
        raise HTTPException(409, "This claim is paid or closed")
    if body.allocate_amount is None:
        raise HTTPException(422, "Allocate at least part of this receipt to the selected claim")
    if body.currency != case.currency:
        raise HTTPException(422, "Receipt and claim currencies must match")
    if body.evidence_artifact_id:
        _artifact(db, case.organization_id, body.evidence_artifact_id)
    if db.query(CashReceipt.id).filter_by(organization_id=case.organization_id, source_reference=body.source_reference).first():
        raise HTTPException(409, "That receipt reference is already recorded in this cooperative")
    if body.allocate_amount is not None:
        allocated = db.query(func.coalesce(func.sum(CashAllocation.amount), 0)).filter_by(case_id=case.id, organization_id=case.organization_id).scalar()
        if body.allocate_amount > body.amount:
            raise HTTPException(422, "Allocation cannot exceed the receipt amount")
        if Decimal(str(allocated)) + body.allocate_amount > case.asserted_amount:
            raise HTTPException(422, "Allocation exceeds the unallocated seller-asserted claim balance")
    row = CashReceipt(
        organization_id=case.organization_id, source_reference=body.source_reference,
        received_on=body.received_on, amount=body.amount, currency=body.currency,
        payment_rail=body.payment_rail, verification_status=body.verification_status,
        verified_by=user.id if body.verification_status == "bank_evidence_reviewed" else None,
        verified_at=datetime.now(timezone.utc) if body.verification_status == "bank_evidence_reviewed" else None,
        evidence_artifact_id=body.evidence_artifact_id, recorded_by=user.id,
    )
    db.add(row)
    db.flush()
    if body.evidence_artifact_id:
        db.add(ReceivableEvidenceLink(
            organization_id=case.organization_id, case_id=case.id, artifact_id=body.evidence_artifact_id,
            evidence_role="receipt_support", source_locator=body.source_reference, linked_by=user.id,
        ))
    if body.allocate_amount is not None:
        db.add(CashAllocation(
            organization_id=case.organization_id, receipt_id=row.id, case_id=case.id,
            amount=body.allocate_amount, allocated_on=body.received_on, allocated_by=user.id,
            allocation_reference=body.source_reference,
        ))
    previous_status = case.status
    db.flush()
    _apply_reviewed_receipt_status(db, case)
    _event(db, case, user, "receipt_recorded", previous_status, case.status,
           f"Cash receipt recorded ({body.verification_status}); source {body.source_reference}", body.evidence_artifact_id)
    db.commit()
    return {"id": str(row.id), "source_reference": row.source_reference, "amount": str(row.amount),
            "currency": row.currency, "received_on": row.received_on.isoformat(), "verification_status": row.verification_status}


@router.post("/cooperative/receivables/cases/{case_id}/allocations", status_code=201)
def allocate_receipt(case_id: UUID, body: AllocationCreate, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    organization = _seller_org(db, user)
    case = db.query(ReceivableCase).filter_by(id=case_id, organization_id=organization.id).with_for_update().first()
    if not case:
        raise HTTPException(404, "Claim was not found in this cooperative workspace")
    if case.status in {"paid", "closed"}:
        raise HTTPException(409, "This claim is paid or closed")
    receipt = db.query(CashReceipt).filter_by(id=body.receipt_id, organization_id=case.organization_id).with_for_update().first()
    if not receipt:
        raise HTTPException(404, "Receipt not found for this cooperative")
    if receipt.currency != case.currency:
        raise HTTPException(422, "Receipt and claim currencies must match")
    receipt_used = db.query(func.coalesce(func.sum(CashAllocation.amount), 0)).filter_by(receipt_id=receipt.id, organization_id=case.organization_id).scalar()
    case_used = db.query(func.coalesce(func.sum(CashAllocation.amount), 0)).filter_by(case_id=case.id, organization_id=case.organization_id).scalar()
    if Decimal(str(receipt_used)) + body.amount > receipt.amount:
        raise HTTPException(422, "Allocation exceeds the unallocated receipt balance")
    if Decimal(str(case_used)) + body.amount > case.asserted_amount:
        raise HTTPException(422, "Allocation exceeds the unallocated seller-asserted claim balance")
    row = CashAllocation(
        organization_id=case.organization_id, receipt_id=receipt.id, case_id=case.id,
        amount=body.amount, allocated_on=body.allocated_on, allocated_by=user.id,
        allocation_reference=body.allocation_reference.strip(),
    )
    previous_status = case.status
    db.add(row)
    db.flush()
    _apply_reviewed_receipt_status(db, case)
    _event(db, case, user, "receipt_allocated", previous_status, case.status,
           f"Receipt allocation {body.amount} {case.currency}; receipt {receipt.source_reference}")
    db.commit()
    return {"id": str(row.id), "receipt_id": str(row.receipt_id), "case_id": str(row.case_id), "amount": str(row.amount), "allocated_on": row.allocated_on.isoformat()}


@router.post("/cooperative/receivables/cases/{case_id}/pilot-decisions", status_code=201)
def record_pilot_decision(case_id: UUID, body: PilotDecisionCreate, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    case = _seller_case(db, user, case_id)
    if not db.query(CounterpartyConfirmation.id).filter_by(case_id=case.id, organization_id=case.organization_id).first():
        raise HTTPException(409, "Record the processor's response before evaluating a paid repeat")
    if body.evidence_artifact_id:
        _artifact(db, case.organization_id, body.evidence_artifact_id)
    row = ReceivablesPilotDecision(
        organization_id=case.organization_id, case_id=case.id, recorded_by=user.id,
        budget_owner_name=body.budget_owner_name, budget_owner_title=body.budget_owner_title.strip(),
        budget_owner_organization=body.budget_owner_organization, decision=body.decision,
        decision_source=body.decision_source, price_amount=body.price_amount,
        currency=body.currency, price_unit=body.price_unit.strip(), decision_note=body.decision_note.strip(),
        next_step=body.next_step.strip(), evidence_artifact_id=body.evidence_artifact_id,
        decided_on=body.decided_on,
    )
    db.add(row)
    db.flush()
    if body.evidence_artifact_id:
        db.add(ReceivableEvidenceLink(
            organization_id=case.organization_id, case_id=case.id, artifact_id=body.evidence_artifact_id,
            evidence_role="budget_decision", source_locator=f"decision:{row.id}", linked_by=user.id,
        ))
    _event(db, case, user, "budget_owner_decision_recorded", case.status, case.status,
           f"Budget owner decision recorded: {body.decision}; source {body.decision_source}", body.evidence_artifact_id)
    db.commit()
    return _case_with_events(db, case)


@router.get("/receivables/cases/{case_id}/evidence/{artifact_id}")
def download_evidence(case_id: UUID, artifact_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    try:
        case = _seller_case(db, user, case_id)
        org_id = case.organization_id
    except HTTPException as seller_error:
        if seller_error.status_code != 403 and seller_error.status_code != 404:
            raise
        case = _processor_case(db, user, case_id)
        org_id = case.organization_id
    link = db.query(ReceivableEvidenceLink).filter_by(case_id=case.id, organization_id=org_id, artifact_id=artifact_id).first()
    if not link:
        raise HTTPException(404, "Evidence is not linked to this claim")
    artifact = _artifact(db, org_id, artifact_id)
    content = _verified_artifact_bytes(artifact)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", artifact.filename)[:120] or "evidence"
    return Response(content, media_type=artifact.media_type, headers={"Content-Disposition": f'attachment; filename="{safe_name}"', "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router.get("/cooperative/receivables/cases/{case_id}/evidence-export")
def evidence_export(case_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    case = _seller_case(db, user, case_id)
    data = _case_with_events(db, case)
    artifacts = []
    for item in data["evidence"]:
        artifact = _artifact(db, case.organization_id, UUID(item["id"]))
        artifacts.append(artifact)
    total_bytes = sum(int((item.source_metadata or {}).get("size_bytes") or 0) for item in artifacts)
    if total_bytes > MAX_EXPORT_BYTES:
        raise HTTPException(413, "Evidence bundle exceeds the 60 MB export limit; export fewer source files at a time")
    output = io.BytesIO()
    try:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("claim.json", json.dumps(data, ensure_ascii=False, indent=2))
            archive.writestr("claim-lines.csv", _csv_text(data["lines"]))
            archive.writestr("processor-responses.csv", _csv_text(data["confirmations"]))
            archive.writestr("budget-owner-decisions.csv", _csv_text(data["pilot_decisions"]))
            archive.writestr("cash-receipts.csv", _csv_text(data["receipts"]))
            archive.writestr("cash-allocations.csv", _csv_text(data["allocations"]))
            archive.writestr("case-events.csv", _csv_text(data["events"]))
            manifest = []
            for artifact in artifacts:
                safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", PurePath(artifact.filename).name)[:120] or "evidence"
                content = _verified_artifact_bytes(artifact)
                if len(content) > settings.evidence_max_file_bytes:
                    raise HTTPException(413, "A source file exceeds the configured evidence limit")
                archive.writestr(f"evidence/{artifact.id}_{safe_name}", content)
                manifest.append({"artifact_id": str(artifact.id), "filename": artifact.filename, "sha256": artifact.sha256, "size_bytes": len(content), "path": f"evidence/{artifact.id}_{safe_name}"})
            archive.writestr("evidence-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Evidence ZIP build failed (%s)", type(exc).__name__)
        raise HTTPException(500, "Evidence export could not be built") from exc
    safe_ref = re.sub(r"[^A-Za-z0-9_-]", "_", case.source_reference)[:60] or str(case.id)
    return Response(output.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="terravanta-claim-{safe_ref}.zip"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
