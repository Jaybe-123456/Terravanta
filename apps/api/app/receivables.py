"""Server-authorized receivables register and counterparty response workflow."""

import csv
import hashlib
import io
import json
import logging
import re
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import PurePath
from statistics import median
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .config import settings
from .evidence_storage import (
    EvidenceMalwareDetected, EvidenceScannerUnavailable, delete_private,
    get_private, put_private, safe_key, scan_evidence, storage_ready,
)
from .models import (
    AuditLog, CashAllocation, CashReceipt, CounterpartyCaseEvidence, CounterpartyConfirmation,
    CounterpartyLineReview, CounterpartyRelationship,
    EvidenceArtifact, Organization, OrganizationMember, ReceivableCase, ReceivableCaseEvent,
    ReceivableCaseLine, ReceivableEvidenceLink, ReceivablesPilotDecision, SourceMappingProfile,
    SupplyContract, SupplyContractReviewEvent, User, UserRole,
)
from .receivables_schemas import (
    AllocationCreate, CaseCreate, CaseLineCreate, CounterpartyLineReviewCreate,
    CounterpartyResponseCreate, DueDateReviewCreate,
    InformationResponseCreate, PilotDecisionCreate, ReceiptCreate, RelationshipCreate,
    SourceImportApply, SourceImportPreviewCreate, SourceMappingProfileCreate, SupplyContractReviewCreate,
)
from .security import current_user, get_scoped_db, require_role

log = logging.getLogger("terravanta.receivables")
router = APIRouter(prefix="/api/v1", tags=["receivables"])


def _scan_uploaded_evidence(content: bytes) -> None:
    try:
        scan_evidence(content)
    except EvidenceMalwareDetected as exc:
        raise HTTPException(422, "Evidence upload was rejected by the malware scanner") from exc
    except EvidenceScannerUnavailable as exc:
        log.warning("Evidence upload blocked because malware scanning is unavailable")
        raise HTTPException(503, "Evidence uploads are paused until the private malware scanner is available") from exc
NBO = ZoneInfo("Africa/Nairobi")
ALLOWED_UPLOADS = {".pdf": ("application/pdf", b"%PDF-"), ".csv": ("text/csv", None)}
MAX_EXPORT_BYTES = 60_000_000
MAX_SOURCE_IMPORT_ROWS = 5_000


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


def _contract_fingerprint(contract: SupplyContract, artifact: EvidenceArtifact) -> str:
    snapshot = {
        "seller_organization_id": str(contract.organization_id),
        "relationship_id": str(contract.relationship_id),
        "contract_reference": contract.contract_reference,
        "version": contract.version,
        "effective_from": contract.effective_from.isoformat(),
        "effective_to": contract.effective_to.isoformat() if contract.effective_to else None,
        "currency": contract.currency,
        "terms_snapshot": contract.terms_snapshot or {},
        "terms_document_sha256": artifact.sha256,
    }
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _parse_source_csv(content: bytes) -> tuple[list[str], list[tuple[int, dict[str, str]]], str]:
    try:
        text = content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise HTTPException(415, "CSV import must be UTF-8 text") from exc
    if "\x00" in text:
        raise HTTPException(415, "CSV import contains invalid binary data")
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        raw_headers = reader.fieldnames or []
        headers = [header.strip() if header else "" for header in raw_headers]
        if not headers or len(headers) > 80 or any(not header or len(header) > 120 for header in headers):
            raise HTTPException(422, "CSV needs 1–80 named columns; each header must be at most 120 characters")
        normalized = [header.casefold() for header in headers]
        if len(set(normalized)) != len(normalized):
            raise HTTPException(422, "CSV contains duplicate column names after trimming spaces")
        reader.fieldnames = headers
        rows: list[tuple[int, dict[str, str]]] = []
        for record_number, row in enumerate(reader, start=1):
            if None in row:
                raise HTTPException(422, f"CSV record {record_number} has more values than header columns")
            if any(value is None for value in row.values()):
                raise HTTPException(422, f"CSV record {record_number} has fewer values than header columns")
            values = {header: (row.get(header) or "").strip() for header in headers}
            if not any(values.values()):
                continue
            rows.append((record_number, values))
            if len(rows) > MAX_SOURCE_IMPORT_ROWS:
                raise HTTPException(413, f"Import is limited to {MAX_SOURCE_IMPORT_ROWS:,} non-empty rows per claim")
    except csv.Error as exc:
        raise HTTPException(422, "CSV structure could not be read") from exc
    if not rows:
        raise HTTPException(422, "CSV contains no non-empty data records")
    fingerprint = hashlib.sha256(json.dumps(headers, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    return headers, rows, fingerprint


def _source_mapping_json(profile: SourceMappingProfile) -> dict:
    return {
        "id": str(profile.id), "organization_id": str(profile.organization_id),
        "source_system": profile.source_system, "record_type": profile.record_type,
        "schema_fingerprint": profile.schema_fingerprint, "version": profile.version,
        "status": profile.status, "mapping_definition": profile.mapping_definition or {},
        "created_by": str(profile.created_by), "approved_by": str(profile.approved_by) if profile.approved_by else None,
        "created_at": profile.created_at.isoformat(),
        "approved_at": profile.approved_at.isoformat() if profile.approved_at else None,
    }


def _contract_json(db: Session, contract: SupplyContract) -> dict:
    relationship = db.query(CounterpartyRelationship).filter_by(
        id=contract.relationship_id, organization_id=contract.organization_id,
    ).first()
    artifact = db.query(EvidenceArtifact).filter_by(
        id=contract.terms_artifact_id, organization_id=contract.organization_id,
    ).first() if contract.terms_artifact_id else None
    if not relationship:
        raise HTTPException(409, "Contract record is missing its relationship")
    events = db.query(SupplyContractReviewEvent).filter_by(
        contract_id=contract.id, organization_id=contract.organization_id,
    ).order_by(SupplyContractReviewEvent.created_at).all()
    return {
        "id": str(contract.id),
        "organization_id": str(contract.organization_id),
        "relationship_id": str(contract.relationship_id),
        "counterparty_name": relationship.counterparty_name,
        "counterparty_organization_id": str(relationship.counterparty_organization_id) if relationship.counterparty_organization_id else None,
        "contract_reference": contract.contract_reference,
        "version": contract.version,
        "effective_from": contract.effective_from.isoformat(),
        "effective_to": contract.effective_to.isoformat() if contract.effective_to else None,
        "currency": contract.currency,
        "payment_due_days": (contract.terms_snapshot or {}).get("payment_due_days"),
        "terms_snapshot": contract.terms_snapshot or {},
        "terms_review_status": contract.terms_review_status,
        "status": contract.status,
        "terms_sha256": _contract_fingerprint(contract, artifact) if artifact else None,
        "terms_document": {
            "id": str(artifact.id), "filename": artifact.filename,
            "sha256": artifact.sha256, "size_bytes": (artifact.source_metadata or {}).get("size_bytes"),
        } if artifact else None,
        "review_events": [{
            "id": str(event.id), "decision": event.decision,
            "terms_sha256": event.terms_sha256, "note": event.note,
            "created_at": event.created_at.isoformat(),
        } for event in events],
        "created_at": contract.created_at.isoformat(),
    }


def _workflow_snapshot(case: ReceivableCase, evidence: list[dict], lines: list[ReceivableCaseLine], confirmations: list[CounterpartyConfirmation], relationship: CounterpartyRelationship | None, information_response_after_request: bool = False) -> dict:
    """Explain claim progress and surface missing proof without changing the asserted facts."""
    status = case.status
    latest_response = confirmations[-1] if confirmations else None
    if status == "submitted" and latest_response and latest_response.response_status == "needs_information" and not information_response_after_request:
        stage, label = "information_requested", "Processor requested information"
        next_action = "Review the processor request, attach the requested source, then respond through the cooperative workflow."
    elif status == "submitted" and latest_response and latest_response.response_status == "needs_information" and information_response_after_request:
        stage, label = "processor_review", "Information sent · awaiting review"
        next_action = "The cooperative response is recorded. Wait for the processor to review it or add a new response."
    else:
        stages = {
            "draft": ("draft", "Prepare claim", "Attach source evidence, add itemized components, and review the date basis."),
            "asserted": ("asserted", "Ready to submit", "Submit the cooperative assertion to the registered processor workspace."),
            "submitted": ("processor_review", "Processor review", "Record the processor response and any reference against this claim."),
            "counterparty_confirmed": ("response_recorded", "Processor accepted", "Track the expected settlement and attach reviewed payment evidence when received."),
            "partially_confirmed": ("partial_response", "Partial acceptance", "Review the accepted and disputed portions, then document the next action."),
            "disputed": ("exception_resolution", "Resolve response", "Review the processor's stated basis and attach evidence for the remaining exception."),
            "partially_paid": ("balance_tracking", "Track remaining balance", "Allocate any new receipt and retain evidence for the outstanding balance."),
            "paid": ("settled", "Payment recorded", "Review the final evidence and close the claim file when the cooperative is ready."),
            "closed": ("closed", "Claim file closed", "The claim workflow is complete."),
        }
        stage, label, next_action = stages.get(status, ("review", status.replace("_", " ").title(), "Review the claim record and choose the next accountable action."))

    due_date_supported = any(item.get("evidence_role") == "due_date_support" for item in evidence)
    blockers: list[dict] = []
    if not evidence:
        blockers.append({"code": "source_evidence_missing", "severity": "required", "message": "Attach a source document before asserting this claim."})
    if not lines:
        blockers.append({"code": "claim_not_itemized", "severity": "review", "message": "No claim components are itemized. Add source-linked lines to make the amount easier to review."})
    if not relationship or relationship.status != "active" or not relationship.counterparty_organization_id:
        blockers.append({"code": "processor_not_linked", "severity": "required" if status in {"draft", "asserted"} else "review", "message": "An active processor workspace is not linked to this claim."})
    if case.due_date is None or case.due_date_basis == "unknown":
        blockers.append({"code": "due_date_unknown", "severity": "review", "message": "Past-due aging is unavailable until a reviewer records a due date and its source."})
    elif not due_date_supported:
        blockers.append({"code": "due_date_source_missing", "severity": "review", "message": "A due date is recorded, but no supporting document is linked to its review."})
    if status == "disputed":
        blockers.append({"code": "processor_exception", "severity": "review", "message": "The processor recorded a dispute or rejection that needs a documented resolution."})
    if status == "submitted" and not confirmations:
        blockers.append({"code": "response_pending", "severity": "waiting", "message": "No processor response has been recorded yet."})

    submitted = status in {"submitted", "counterparty_confirmed", "partially_confirmed", "disputed", "partially_paid", "paid", "closed"}
    responded = bool(confirmations)
    payment_reviewed = status in {"partially_paid", "paid", "closed"}
    steps = [
        {"key": "draft", "label": "Claim drafted", "complete": True},
        {"key": "evidence", "label": "Source evidence attached", "complete": bool(evidence)},
        {"key": "assertion", "label": "Cooperative assertion", "complete": status != "draft"},
        {"key": "submission", "label": "Sent to processor", "complete": submitted},
        {"key": "response", "label": "Processor response", "complete": responded},
        {"key": "payment", "label": "Payment evidence reviewed", "complete": payment_reviewed},
        {"key": "closure", "label": "Claim file closed", "complete": status == "closed"},
    ]
    return {
        "stage": stage, "label": label, "next_action": next_action,
        "steps": steps, "blockers": blockers,
        "due_date_source_supported": due_date_supported,
    }


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
    counterparty_evidence_links = db.query(CounterpartyCaseEvidence).filter_by(case_id=case.id).order_by(CounterpartyCaseEvidence.created_at).all()
    for link in counterparty_evidence_links:
        artifact = db.query(EvidenceArtifact).filter_by(
            id=link.artifact_id, organization_id=link.counterparty_organization_id,
        ).first()
        if artifact:
            evidence.append({
                "id": str(artifact.id), "filename": artifact.filename,
                "artifact_type": artifact.artifact_type, "media_type": artifact.media_type,
                "sha256": artifact.sha256, "source_party": artifact.source_party,
                "source_reference": artifact.source_reference, "size_bytes": (artifact.source_metadata or {}).get("size_bytes"),
                "evidence_role": "counterparty_support", "source_locator": link.source_locator,
                "created_at": artifact.created_at.isoformat(),
            })
    confirmations = db.query(CounterpartyConfirmation).filter_by(case_id=case.id).order_by(CounterpartyConfirmation.confirmed_at).all()
    line_reviews = db.query(CounterpartyLineReview).filter_by(case_id=case.id).order_by(
        CounterpartyLineReview.reviewed_at, CounterpartyLineReview.created_at,
    ).all()
    reviewer_names = {}
    reviewer_ids = {row.reviewed_by_user_id for row in line_reviews}
    if reviewer_ids:
        reviewer_names = {
            str(row.id): row.display_name
            for row in db.query(User.id, User.display_name).filter(User.id.in_(reviewer_ids)).all()
        }
    relationship = db.query(CounterpartyRelationship).filter_by(id=case.relationship_id, organization_id=case.organization_id).first()
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
    info_response_after_request = False
    if case.status == "submitted" and confirmations and confirmations[-1].response_status == "needs_information":
        info_reply = db.query(ReceivableCaseEvent).filter_by(
            case_id=case.id, organization_id=case.organization_id, event_type="claim_information_submitted",
        ).order_by(ReceivableCaseEvent.created_at.desc()).first()
        info_response_after_request = bool(info_reply and _as_utc(info_reply.created_at) > _as_utc(confirmations[-1].confirmed_at))
    workflow = _workflow_snapshot(case, evidence, lines, confirmations, relationship, info_response_after_request)
    latest_line_reviews = {}
    for review in line_reviews:
        latest_line_reviews[review.case_line_id] = review
    confirmed_amount = latest.confirmed_amount if latest and latest.confirmed_amount is not None else None
    contract = db.query(SupplyContract).filter_by(
        id=case.contract_id, organization_id=case.organization_id,
    ).first() if case.contract_id else None
    return {
        "id": str(case.id), "organization_id": str(case.organization_id),
        "relationship_id": str(case.relationship_id),
        "counterparty_organization_id": str(case.counterparty_organization_id) if case.counterparty_organization_id else None,
        "contract_id": str(case.contract_id) if case.contract_id else None,
        "contract": _contract_json(db, contract) if contract else None,
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
        "aging": aging, "workflow": workflow,
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
            "id": str(row.id), "line_number": row.line_number,
            "mapping_profile_id": str(row.mapping_profile_id) if row.mapping_profile_id else None,
            "line_type": row.line_type,
            "direction": row.direction, "source_reference": row.source_reference,
            "occurred_on": row.occurred_on.isoformat() if row.occurred_on else None,
            "quantity": str(row.quantity) if row.quantity is not None else None,
            "unit": row.unit, "amount": str(row.amount), "currency": row.currency,
            "source_locator": row.source_locator, "provenance_class": row.provenance_class,
            "evidence_artifact_id": str(row.evidence_artifact_id) if row.evidence_artifact_id else None,
        } for row in lines],
        "line_review_summary": {
            "reviewed_lines": len(latest_line_reviews),
            "unreviewed_lines": max(0, len(lines) - len(latest_line_reviews)),
            "matched_lines": sum(1 for row in latest_line_reviews.values() if row.review_status == "matched"),
            "value_difference_lines": sum(1 for row in latest_line_reviews.values() if row.review_status == "value_differs"),
            "missing_from_processor_record_lines": sum(1 for row in latest_line_reviews.values() if row.review_status == "missing_from_processor_record"),
        },
        "line_reviews": [{
            "id": str(row.id), "case_line_id": str(row.case_line_id),
            "review_status": row.review_status,
            "seller_amount_snapshot": str(row.seller_amount_snapshot),
            "processor_amount": str(row.processor_amount) if row.processor_amount is not None else None,
            "processor_direction": row.processor_direction,
            "seller_direction_snapshot": row.seller_direction_snapshot,
            "currency": row.currency, "processor_reference": row.processor_reference,
            "source_locator": row.source_locator, "review_note": row.review_note,
            "reviewer_name": reviewer_names.get(str(row.reviewed_by_user_id), "Former member"),
            "evidence_artifact_id": str(row.evidence_artifact_id) if row.evidence_artifact_id else None,
            "reviewed_at": row.reviewed_at.isoformat(),
        } for row in line_reviews],
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
        "to_status": event.to_status, "note": event.note,
        "evidence_artifact_id": str(event.evidence_artifact_id) if event.evidence_artifact_id else None,
        "created_at": event.created_at.isoformat(),
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


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _median_or_none(values: list[float], digits: int = 1) -> float | None:
    return round(float(median(values)), digits) if values else None


@router.get("/cooperative/receivables/performance")
def seller_performance(
    window_days: int = Query(default=90, ge=30, le=365),
    user: User = Depends(current_user), db: Session = Depends(get_scoped_db),
):
    """Report actual claim handling time and rework, grouped by claims opened in the window."""
    org = _seller_org(db, user)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    cases = db.query(ReceivableCase).filter_by(organization_id=org.id).all()
    cohort = [case for case in cases if _as_utc(case.created_at) >= cutoff]
    cohort_ids = [case.id for case in cohort]

    events_by_case: dict[UUID, list[ReceivableCaseEvent]] = {}
    confirmations_by_case: dict[UUID, list[CounterpartyConfirmation]] = {}
    if cohort_ids:
        for event in db.query(ReceivableCaseEvent).filter(
            ReceivableCaseEvent.organization_id == org.id,
            ReceivableCaseEvent.case_id.in_(cohort_ids),
        ).order_by(ReceivableCaseEvent.created_at).all():
            events_by_case.setdefault(event.case_id, []).append(event)
        for response in db.query(CounterpartyConfirmation).filter(
            CounterpartyConfirmation.organization_id == org.id,
            CounterpartyConfirmation.case_id.in_(cohort_ids),
        ).order_by(CounterpartyConfirmation.confirmed_at).all():
            confirmations_by_case.setdefault(response.case_id, []).append(response)

    prep_hours: list[float] = []
    response_hours: list[float] = []
    resolution_days: list[float] = []
    submitted_ids: set[UUID] = set()
    responded_ids: set[UUID] = set()
    resolved_ids: set[UUID] = set()
    rework_ids: set[UUID] = set()
    response_mix: dict[str, int] = {}
    for case in cohort:
        case_events = events_by_case.get(case.id, [])
        submitted = next((event for event in case_events if event.event_type == "claim_submitted"), None)
        responses = confirmations_by_case.get(case.id, [])
        for response in responses:
            response_mix[response.response_status] = response_mix.get(response.response_status, 0) + 1
            if response.response_status in {"needs_information", "disputed", "rejected"}:
                rework_ids.add(case.id)
        if not submitted:
            continue
        submitted_ids.add(case.id)
        submitted_at = _as_utc(submitted.created_at)
        prep_hours.append(max(0.0, (submitted_at - _as_utc(case.created_at)).total_seconds() / 3600))
        first_response = next((response for response in responses if _as_utc(response.confirmed_at) >= submitted_at), None)
        if first_response:
            responded_ids.add(case.id)
            response_hours.append(max(0.0, (_as_utc(first_response.confirmed_at) - submitted_at).total_seconds() / 3600))
        resolution = next((event for event in case_events if event.to_status in {"paid", "closed"}), None)
        if resolution:
            resolved_ids.add(case.id)
            resolution_days.append(max(0.0, (_as_utc(resolution.created_at) - submitted_at).total_seconds() / 86400))

    active_cases = [case for case in cases if case.status not in {"paid", "closed"}]
    stage_counts: dict[str, int] = {}
    latest_response_by_case: dict[UUID, CounterpartyConfirmation] = {}
    latest_info_reply_at_by_case: dict[UUID, datetime] = {}
    active_ids = [case.id for case in active_cases]
    if active_ids:
        for response in db.query(CounterpartyConfirmation).filter(
            CounterpartyConfirmation.organization_id == org.id,
            CounterpartyConfirmation.case_id.in_(active_ids),
        ).order_by(CounterpartyConfirmation.confirmed_at).all():
            latest_response_by_case[response.case_id] = response
        for event in db.query(ReceivableCaseEvent).filter(
            ReceivableCaseEvent.organization_id == org.id,
            ReceivableCaseEvent.case_id.in_(active_ids),
            ReceivableCaseEvent.event_type == "claim_information_submitted",
        ).order_by(ReceivableCaseEvent.created_at).all():
            latest_info_reply_at_by_case[event.case_id] = event.created_at
    evidence_case_ids = {
        row[0] for row in db.query(ReceivableEvidenceLink.case_id).filter(
            ReceivableEvidenceLink.organization_id == org.id,
            ReceivableEvidenceLink.case_id.in_([case.id for case in active_cases] or [UUID(int=0)]),
        ).distinct().all()
    }
    line_case_ids = {
        row[0] for row in db.query(ReceivableCaseLine.case_id).filter(
            ReceivableCaseLine.organization_id == org.id,
            ReceivableCaseLine.case_id.in_([case.id for case in active_cases] or [UUID(int=0)]),
        ).distinct().all()
    }
    due_date_support_case_ids = {
        row[0] for row in db.query(ReceivableEvidenceLink.case_id).filter(
            ReceivableEvidenceLink.organization_id == org.id,
            ReceivableEvidenceLink.evidence_role == "due_date_support",
            ReceivableEvidenceLink.case_id.in_(active_ids or [UUID(int=0)]),
        ).distinct().all()
    }
    for case in active_cases:
        stage = "awaiting_processor" if case.status == "submitted" else "resolve_exception" if case.status == "disputed" else "track_balance" if case.status in {"partially_confirmed", "counterparty_confirmed", "partially_paid"} else "ready_to_submit" if case.status == "asserted" else "prepare_claim"
        latest_response = latest_response_by_case.get(case.id)
        reply_at = latest_info_reply_at_by_case.get(case.id)
        request_is_open = latest_response and latest_response.response_status == "needs_information" and (
            not reply_at or _as_utc(reply_at) <= _as_utc(latest_response.confirmed_at)
        )
        if case.status == "submitted" and request_is_open:
            stage = "information_requested"
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    missing_due_date = sum(1 for case in active_cases if case.due_date is None or case.due_date_basis == "unknown" or case.id not in due_date_support_case_ids)
    missing_evidence = sum(1 for case in active_cases if case.id not in evidence_case_ids)
    missing_itemization = sum(1 for case in active_cases if case.id not in line_case_ids)
    return {
        "organization_id": str(org.id),
        "window_days": window_days,
        "cohort_basis": "claims opened during the selected period; later responses and resolutions are included as they arrive",
        "period_start": cutoff.date().isoformat(),
        "as_of_utc": now.isoformat(),
        "cohort": {
            "claims_opened": len(cohort), "claims_submitted": len(submitted_ids),
            "claims_with_processor_response": len(responded_ids), "claims_paid_or_closed": len(resolved_ids),
        },
        "timing": {
            "median_draft_to_submission_hours": _median_or_none(prep_hours),
            "submission_timing_sample_size": len(prep_hours),
            "median_submission_to_first_response_hours": _median_or_none(response_hours),
            "first_response_sample_size": len(response_hours),
            "median_submission_to_paid_or_closed_days": _median_or_none(resolution_days),
            "resolution_sample_size": len(resolution_days),
        },
        "rework": {
            "claims_with_rework_or_exception": len(rework_ids),
            "rate_percent": round(len(rework_ids) * 100 / len(submitted_ids), 1) if submitted_ids else None,
            "basis": "claim had at least one processor request for information, dispute, or rejection",
            "processor_response_counts": response_mix,
        },
        "current_queue": {
            "open_claims": len(active_cases), "stage_counts": stage_counts,
            "missing_due_date_support": missing_due_date,
            "missing_source_evidence": missing_evidence,
            "missing_itemization": missing_itemization,
        },
    }


@router.get("/cooperative/receivables/relationships")
def seller_relationships(user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    org = _seller_org(db, user)
    rows = db.query(CounterpartyRelationship).filter_by(organization_id=org.id).order_by(CounterpartyRelationship.counterparty_name).all()
    return [{"id": str(r.id), "counterparty_name": r.counterparty_name, "relationship_type": r.relationship_type,
             "counterparty_organization_id": str(r.counterparty_organization_id) if r.counterparty_organization_id else None,
             "external_reference": r.external_reference, "status": r.status} for r in rows]


@router.get("/cooperative/receivables/contracts")
def seller_contracts(
    relationship_id: UUID | None = Query(default=None),
    user: User = Depends(current_user), db: Session = Depends(get_scoped_db),
):
    organization = _seller_org(db, user)
    query = db.query(SupplyContract).filter_by(organization_id=organization.id)
    if relationship_id:
        query = query.filter_by(relationship_id=relationship_id)
    rows = query.order_by(SupplyContract.contract_reference, SupplyContract.version.desc()).all()
    return [_contract_json(db, row) for row in rows]


@router.post("/cooperative/receivables/relationships/{relationship_id}/contracts", status_code=201)
def create_supply_contract(
    relationship_id: UUID,
    contract_reference: Annotated[str, Form(min_length=2, max_length=120)],
    effective_from: Annotated[date, Form()],
    payment_due_days: Annotated[int, Form(ge=0, le=365)],
    file: Annotated[UploadFile, File()],
    effective_to: Annotated[date | None, Form()] = None,
    currency: Annotated[str, Form(min_length=3, max_length=3)] = "KES",
    user: User = Depends(current_user), db: Session = Depends(get_scoped_db),
):
    organization = _seller_org(db, user)
    relationship = db.query(CounterpartyRelationship).filter_by(
        id=relationship_id, organization_id=organization.id,
    ).first()
    if not relationship or relationship.relationship_type != "processor" or not relationship.counterparty_organization_id:
        raise HTTPException(422, "Link this supply contract to a registered processor relationship first")
    if relationship.status != "active":
        raise HTTPException(422, "The processor relationship must be active before contract review")
    if effective_to and effective_to < effective_from:
        raise HTTPException(422, "Contract end date cannot precede its start date")
    currency = currency.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise HTTPException(422, "Currency must be a three-letter code")
    if not storage_ready():
        raise HTTPException(503, "Private evidence storage is not configured")

    filename = PurePath((file.filename or "supply-contract.pdf").replace("\\", "/")).name[:255]
    if PurePath(filename).suffix.lower() != ".pdf":
        raise HTTPException(415, "Supply contract evidence must be a PDF")
    content = file.file.read(settings.evidence_max_file_bytes + 1)
    file.file.close()
    if not content or len(content) > settings.evidence_max_file_bytes:
        raise HTTPException(413, f"Contract PDF must be 1 byte to {settings.evidence_max_file_bytes} bytes")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(415, "File contents do not match the PDF format")
    _scan_uploaded_evidence(content)

    reference = contract_reference.strip()
    if len(reference) < 2:
        raise HTTPException(422, "Contract reference must contain at least two non-space characters")
    contract_id = uuid4()
    artifact_id = uuid4()
    key = safe_key(organization.id, contract_id, artifact_id, ".pdf")
    sha256 = hashlib.sha256(content).hexdigest()
    try:
        put_private(key, content, "application/pdf")
    except Exception as exc:
        log.exception("Private contract upload failed (%s)", type(exc).__name__)
        raise HTTPException(503, "Contract document storage is temporarily unavailable") from exc

    artifact = EvidenceArtifact(
        id=artifact_id, organization_id=organization.id, uploaded_by=user.id,
        source_party="seller", source_system="manual_upload", source_reference=reference,
        filename=filename, media_type="application/pdf", artifact_type="contract_terms",
        sha256=sha256, storage_key=key, sensitivity="confidential",
        source_metadata={"size_bytes": len(content), "validation": "pdf_magic", "contract_reference": reference},
    )
    try:
        # Serialize version allocation per cooperative after the file upload so
        # concurrent submissions cannot select the same next version.
        db.query(Organization.id).filter_by(id=organization.id).with_for_update().first()
        existing = db.query(func.max(SupplyContract.version)).filter_by(
            organization_id=organization.id, contract_reference=reference,
        ).scalar()
        contract = SupplyContract(
            id=contract_id, organization_id=organization.id, relationship_id=relationship.id,
            terms_artifact_id=artifact.id, contract_reference=reference,
            version=int(existing or 0) + 1, effective_from=effective_from, effective_to=effective_to,
            currency=currency, terms_review_status="under_review", status="draft",
            terms_snapshot={"payment_term_basis": "calendar_days_after_invoice", "payment_due_days": payment_due_days},
            created_by=user.id,
        )
        db.add_all([artifact, contract])
        db.flush()
        db.add(AuditLog(
            user_id=user.id, action="receivable.supply_contract_created", entity_type="supply_contract",
            entity_id=str(contract.id), metadata_json={"organization_id": str(organization.id), "version": contract.version, "terms_sha256": _contract_fingerprint(contract, artifact)},
        ))
        db.commit()
    except Exception:
        db.rollback()
        try:
            delete_private(key)
        except Exception:
            log.exception("Could not remove orphaned contract file after database failure")
        raise
    return _contract_json(db, contract)


@router.get("/processor/receivables/contracts")
def processor_contracts(user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    processor = _processor_org(db, user)
    rows = db.query(SupplyContract).join(
        CounterpartyRelationship,
        (CounterpartyRelationship.id == SupplyContract.relationship_id)
        & (CounterpartyRelationship.organization_id == SupplyContract.organization_id),
    ).filter(CounterpartyRelationship.counterparty_organization_id == processor.id).order_by(
        SupplyContract.created_at.desc(), SupplyContract.version.desc(),
    ).all()
    return [_contract_json(db, row) for row in rows]


@router.post("/processor/receivables/contracts/{contract_id}/review")
def review_supply_contract(
    contract_id: UUID, body: SupplyContractReviewCreate,
    user: User = Depends(current_user), db: Session = Depends(get_scoped_db),
):
    processor = _processor_org(db, user)
    contract = db.query(SupplyContract).join(
        CounterpartyRelationship,
        (CounterpartyRelationship.id == SupplyContract.relationship_id)
        & (CounterpartyRelationship.organization_id == SupplyContract.organization_id),
    ).filter(
        SupplyContract.id == contract_id,
        CounterpartyRelationship.counterparty_organization_id == processor.id,
    ).with_for_update().first()
    if not contract:
        raise HTTPException(404, "Supply contract was not found for this processor")
    if contract.terms_review_status != "under_review" or contract.status != "draft":
        raise HTTPException(409, "Only an unreviewed contract version can receive a decision")
    if not contract.terms_artifact_id:
        raise HTTPException(409, "This contract version has no source document")
    artifact = _artifact(db, contract.organization_id, contract.terms_artifact_id)
    current_hash = _contract_fingerprint(contract, artifact)
    if body.terms_sha256 != current_hash:
        raise HTTPException(409, "The terms changed after this review was opened; reload the contract version")
    previous_status = contract.status
    event = SupplyContractReviewEvent(
        organization_id=contract.organization_id, contract_id=contract.id,
        counterparty_organization_id=processor.id, actor_user_id=user.id,
        decision=body.decision, terms_sha256=current_hash, note=body.note,
    )
    contract.terms_review_status = "counterparty_confirmed" if body.decision == "confirmed" else "seller_asserted"
    contract.status = "active" if body.decision == "confirmed" else "draft"
    db.add(event)
    db.add(AuditLog(
        user_id=user.id, action=f"receivable.supply_contract_{body.decision}", entity_type="supply_contract",
        entity_id=str(contract.id), metadata_json={"organization_id": str(processor.id), "terms_sha256": current_hash},
    ))
    db.commit()
    return _contract_json(db, contract)


@router.get("/receivables/contracts/{contract_id}/terms")
def download_contract_terms(
    contract_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db),
):
    contract = db.query(SupplyContract).filter_by(id=contract_id).first()
    if not contract:
        raise HTTPException(404, "Supply contract was not found")
    allowed = False
    try:
        allowed = _seller_org(db, user).id == contract.organization_id
    except HTTPException:
        pass
    if not allowed:
        relationship = db.query(CounterpartyRelationship).filter_by(
            id=contract.relationship_id, organization_id=contract.organization_id,
        ).first()
        if relationship and relationship.counterparty_organization_id:
            try:
                allowed = _processor_org(db, user).id == relationship.counterparty_organization_id
            except HTTPException:
                pass
    if not allowed:
        raise HTTPException(404, "Supply contract was not found")
    if not contract.terms_artifact_id:
        raise HTTPException(404, "Contract source PDF was not found")
    artifact = _artifact(db, contract.organization_id, contract.terms_artifact_id)
    content = _verified_artifact_bytes(artifact)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", artifact.filename)[:120] or "supply-contract.pdf"
    return Response(content, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{safe_name}"',
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
    })


@router.get("/cooperative/receivables/source-mappings")
def seller_source_mappings(
    schema_fingerprint: str | None = Query(default=None, pattern=r"^[0-9a-f]{64}$"),
    user: User = Depends(current_user), db: Session = Depends(get_scoped_db),
):
    organization = _seller_org(db, user)
    query = db.query(SourceMappingProfile).filter_by(
        organization_id=organization.id, record_type="receivable_lines",
    )
    if schema_fingerprint:
        query = query.filter_by(schema_fingerprint=schema_fingerprint)
    rows = query.order_by(SourceMappingProfile.source_system, SourceMappingProfile.version.desc()).all()
    return [_source_mapping_json(row) for row in rows]


@router.post("/cooperative/receivables/source-mappings", status_code=201)
def create_source_mapping(
    body: SourceMappingProfileCreate,
    user: User = Depends(current_user), db: Session = Depends(get_scoped_db),
):
    organization = _seller_org(db, user)
    db.query(Organization.id).filter_by(id=organization.id).with_for_update().first()
    existing = db.query(func.max(SourceMappingProfile.version)).filter_by(
        organization_id=organization.id, source_system=body.source_system,
        record_type=body.record_type,
    ).scalar()
    profile = SourceMappingProfile(
        organization_id=organization.id, source_system=body.source_system,
        record_type=body.record_type, schema_fingerprint=body.schema_fingerprint,
        version=int(existing or 0) + 1, status="draft",
        mapping_definition=body.mapping_definition, created_by=user.id,
    )
    db.add(profile)
    db.flush()
    db.add(AuditLog(
        user_id=user.id, action="receivable.source_mapping_created", entity_type="source_mapping_profile",
        entity_id=str(profile.id), metadata_json={
            "organization_id": str(organization.id), "version": profile.version,
            "source_system": profile.source_system, "schema_fingerprint": profile.schema_fingerprint,
        },
    ))
    db.commit()
    return _source_mapping_json(profile)


@router.post("/cooperative/receivables/source-mappings/{profile_id}/approve")
def approve_source_mapping(
    profile_id: UUID,
    user: User = Depends(current_user), db: Session = Depends(get_scoped_db),
):
    organization = _seller_org(db, user)
    profile = db.query(SourceMappingProfile).filter_by(
        id=profile_id, organization_id=organization.id, record_type="receivable_lines",
    ).with_for_update().first()
    if not profile:
        raise HTTPException(404, "Source mapping was not found")
    if profile.status != "draft":
        raise HTTPException(409, "Only a draft source mapping can be approved")
    profile.status = "approved"
    profile.approved_by = user.id
    profile.approved_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        user_id=user.id, action="receivable.source_mapping_approved", entity_type="source_mapping_profile",
        entity_id=str(profile.id), metadata_json={
            "organization_id": str(organization.id), "version": profile.version,
            "schema_fingerprint": profile.schema_fingerprint,
        },
    ))
    db.commit()
    return _source_mapping_json(profile)


@router.post("/cooperative/receivables/cases/{case_id}/source-import/preview")
def preview_case_source_import(
    case_id: UUID, body: SourceImportPreviewCreate,
    user: User = Depends(current_user), db: Session = Depends(get_scoped_db),
):
    case = _seller_case(db, user, case_id)
    if case.status != "draft":
        raise HTTPException(409, "Source rows can be mapped only while the claim is a draft")
    artifact = _artifact(db, case.organization_id, body.evidence_artifact_id)
    linked = db.query(ReceivableEvidenceLink.id).filter_by(
        organization_id=case.organization_id, case_id=case.id, artifact_id=artifact.id,
    ).first()
    if not linked:
        raise HTTPException(422, "Attach the CSV to this claim before previewing it")
    if not artifact.filename.lower().endswith(".csv") or artifact.media_type != "text/csv":
        raise HTTPException(415, "Choose a CSV evidence file")
    headers, rows, fingerprint = _parse_source_csv(_verified_artifact_bytes(artifact))
    return {
        "evidence_artifact_id": str(artifact.id), "filename": artifact.filename,
        "sha256": artifact.sha256, "schema_fingerprint": fingerprint,
        "headers": headers, "row_count": len(rows), "max_rows": MAX_SOURCE_IMPORT_ROWS,
        "data_preview": "Values stay in the cooperative workspace; only column names and row count are returned here.",
    }


@router.post("/cooperative/receivables/cases/{case_id}/source-import/apply")
def apply_case_source_import(
    case_id: UUID, body: SourceImportApply,
    user: User = Depends(current_user), db: Session = Depends(get_scoped_db),
):
    case = _seller_case(db, user, case_id)
    case = db.query(ReceivableCase).filter_by(
        id=case.id, organization_id=case.organization_id,
    ).with_for_update().first()
    if not case:
        raise HTTPException(404, "Receivable claim was not found")
    if case.status != "draft":
        raise HTTPException(409, "Rows can be imported only while the claim is a draft")
    if db.query(ReceivableCaseLine.id).filter_by(
        organization_id=case.organization_id, case_id=case.id,
    ).first():
        raise HTTPException(409, "This claim already has line items; import into a fresh draft to avoid duplicating or replacing them")
    profile = db.query(SourceMappingProfile).filter_by(
        id=body.mapping_profile_id, organization_id=case.organization_id,
        record_type="receivable_lines", status="approved",
    ).first()
    if not profile:
        raise HTTPException(422, "Choose an approved cooperative source mapping")
    artifact = _artifact(db, case.organization_id, body.evidence_artifact_id)
    if not artifact.filename.lower().endswith(".csv") or artifact.media_type != "text/csv":
        raise HTTPException(415, "Choose a CSV evidence file")
    linked = db.query(ReceivableEvidenceLink.id).filter_by(
        organization_id=case.organization_id, case_id=case.id, artifact_id=artifact.id,
    ).first()
    if not linked:
        raise HTTPException(422, "The source CSV must be attached to this claim")
    if db.query(ReceivableEvidenceLink.id).filter_by(
        organization_id=case.organization_id, case_id=case.id, artifact_id=artifact.id,
        evidence_role="line_import",
    ).first():
        raise HTTPException(409, "This CSV has already been imported into the claim")

    headers, rows, fingerprint = _parse_source_csv(_verified_artifact_bytes(artifact))
    if profile.schema_fingerprint != fingerprint:
        raise HTTPException(409, "The CSV columns changed since this mapping was reviewed; preview and map this schema again")
    mapping = profile.mapping_definition or {}
    columns = mapping.get("columns", {})
    defaults = mapping.get("defaults", {})
    if any(header not in headers for header in columns.values()):
        raise HTTPException(409, "A mapped column is missing from this CSV; create a new mapping version")

    def field_value(row: dict[str, str], field: str) -> str:
        column = columns.get(field)
        value = row.get(column, "") if column else ""
        if not value:
            value = defaults.get(field, "")
        return str(value).strip()

    parsed_lines: list[CaseLineCreate] = []
    signed_total = Decimal("0")
    for record_number, row in rows:
        try:
            amount_value = Decimal(field_value(row, "amount"))
            quantity_text = field_value(row, "quantity")
            quantity_value = Decimal(quantity_text) if quantity_text else None
            date_text = field_value(row, "occurred_on")
            occurred_on = date.fromisoformat(date_text) if date_text else None
            line = CaseLineCreate.model_validate({
                "line_type": field_value(row, "line_type"),
                "direction": field_value(row, "direction"),
                "amount": amount_value,
                "source_reference": field_value(row, "source_reference"),
                "occurred_on": occurred_on,
                "quantity": quantity_value,
                "unit": field_value(row, "unit"),
                "source_locator": f"{artifact.filename[:120]}#record-{record_number}",
                "evidence_artifact_id": artifact.id,
            })
        except ValidationError as exc:
            issue = exc.errors()[0] if exc.errors() else {}
            field_name = str((issue.get("loc") or ("line",))[0])
            raise HTTPException(422, f"CSV record {record_number} field {field_name}: {issue.get('msg', 'value does not fit the approved mapping')}") from exc
        except InvalidOperation as exc:
            raise HTTPException(422, f"CSV record {record_number} contains an invalid decimal value") from exc
        except ValueError as exc:
            raise HTTPException(422, f"CSV record {record_number} contains a date that is not ISO YYYY-MM-DD") from exc
        if not line.amount.is_finite() or (line.quantity is not None and not line.quantity.is_finite()):
            raise HTTPException(422, f"CSV record {record_number} contains a non-finite amount or quantity")
        if line.direction == "increase":
            signed_total += line.amount
        elif line.direction == "decrease":
            signed_total -= line.amount
        parsed_lines.append(line)

    if abs(signed_total - case.asserted_amount) > Decimal("0.01"):
        raise HTTPException(422, f"Mapped line total {signed_total:.2f} {case.currency} does not equal claim amount {case.asserted_amount:.2f} {case.currency}; no rows were imported")

    for line_number, line in enumerate(parsed_lines, start=1):
        db.add(ReceivableCaseLine(
            organization_id=case.organization_id, case_id=case.id,
            mapping_profile_id=profile.id, line_number=line_number,
            line_type=line.line_type, direction=line.direction,
            source_reference=line.source_reference, occurred_on=line.occurred_on,
            quantity=line.quantity, unit=line.unit, amount=line.amount,
            currency=case.currency, evidence_artifact_id=artifact.id,
            source_locator=line.source_locator, provenance_class="seller_attested",
            created_by=user.id,
        ))
    db.add(ReceivableEvidenceLink(
        organization_id=case.organization_id, case_id=case.id, artifact_id=artifact.id,
        evidence_role="line_import", source_locator=f"mapping:{profile.id}:v{profile.version}", linked_by=user.id,
    ))
    previous_status = case.status
    case.updated_at = datetime.now(timezone.utc)
    _event(
        db, case, user, "source_lines_imported", previous_status, previous_status,
        f"Imported {len(parsed_lines)} source rows using {profile.source_system} mapping v{profile.version}; "
        f"schema {fingerprint}; source file SHA-256 {artifact.sha256}.", artifact.id,
    )
    db.add(AuditLog(
        user_id=user.id, action="receivable.source_rows_imported", entity_type="receivable_case",
        entity_id=str(case.id), metadata_json={
            "organization_id": str(case.organization_id), "artifact_id": str(artifact.id),
            "mapping_profile_id": str(profile.id), "mapping_version": profile.version,
            "row_count": len(parsed_lines), "schema_fingerprint": fingerprint,
            "signed_total": str(signed_total), "currency": case.currency,
        },
    ))
    db.commit()
    return {
        "case": _case_with_events(db, case), "rows_imported": len(parsed_lines),
        "signed_total": str(signed_total), "currency": case.currency,
        "mapping_profile": _source_mapping_json(profile),
        "source_sha256": artifact.sha256,
    }


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
    contract = None
    if body.due_date_basis == "contract":
        if not body.contract_id:
            raise HTTPException(422, "Select the reviewed supply contract supporting the due date")
        contract = db.query(SupplyContract).filter_by(id=body.contract_id, organization_id=org.id, relationship_id=relation.id).first()
        if not contract or contract.terms_review_status != "counterparty_confirmed" or contract.status != "active":
            raise HTTPException(422, "Only an active, counterparty-confirmed contract can set a contract due date")
        if not body.invoice_date or not body.due_date:
            raise HTTPException(422, "Contract-based aging needs both an invoice date and its due date")
        if body.invoice_date < contract.effective_from or (contract.effective_to and body.invoice_date > contract.effective_to):
            raise HTTPException(422, "The invoice date falls outside this contract version's effective period")
        due_days = (contract.terms_snapshot or {}).get("payment_due_days")
        if not isinstance(due_days, int) or due_days < 0 or body.due_date != body.invoice_date + timedelta(days=due_days):
            raise HTTPException(422, "The recorded due date must match the confirmed invoice payment term")
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
    if body.due_date_basis == "contract" and contract and contract.terms_artifact_id:
        db.add(ReceivableEvidenceLink(
            organization_id=org.id, case_id=case.id, artifact_id=contract.terms_artifact_id,
            evidence_role="due_date_support",
            source_locator=f"contract:{contract.contract_reference}:v{contract.version}", linked_by=user.id,
        ))
    contract_event_note = "Seller-asserted claim draft created"
    contract_event_artifact = None
    if body.due_date_basis == "contract" and contract:
        contract_event_note = (
            f"Contract-based due date recorded from {contract.contract_reference} v{contract.version}; "
            f"{(contract.terms_snapshot or {}).get('payment_due_days')} calendar days after invoice."
        )
        contract_event_artifact = contract.terms_artifact_id
    _event(db, case, user, "case_created", "", "draft", contract_event_note, contract_event_artifact)
    db.commit()
    return _case_with_events(db, case)


@router.get("/cooperative/receivables/cases/{case_id}")
def seller_case(case_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    return _case_with_events(db, _seller_case(db, user, case_id))


@router.post("/cooperative/receivables/cases/{case_id}/due-date-review")
def review_case_due_date(
    case_id: UUID, body: DueDateReviewCreate,
    user: User = Depends(current_user), db: Session = Depends(get_scoped_db),
):
    case = _seller_case(db, user, case_id)
    if case.status in {"paid", "closed"}:
        raise HTTPException(409, "The due-date basis cannot be changed after the claim is closed")
    if case.invoice_date and body.due_date < case.invoice_date:
        raise HTTPException(422, "The reviewed due date cannot precede the invoice date")
    artifact = _artifact(db, case.organization_id, body.evidence_artifact_id)
    previous_date = case.due_date.isoformat() if case.due_date else "unknown"
    previous_basis = case.due_date_basis
    case.due_date = body.due_date
    case.due_date_basis = "manual_review"
    case.due_date_reviewed_by = user.id
    case.due_date_reviewed_at = datetime.now(timezone.utc)
    case.updated_at = datetime.now(timezone.utc)
    existing_link = db.query(ReceivableEvidenceLink.id).filter_by(
        organization_id=case.organization_id, case_id=case.id, artifact_id=artifact.id,
        evidence_role="due_date_support", source_locator="due-date-review",
    ).first()
    if not existing_link:
        db.add(ReceivableEvidenceLink(
            organization_id=case.organization_id, case_id=case.id, artifact_id=artifact.id,
            evidence_role="due_date_support", source_locator="due-date-review", linked_by=user.id,
        ))
    _event(
        db, case, user, "due_date_reviewed", case.status, case.status,
        f"Due date reviewed: {previous_date} ({previous_basis}) → {body.due_date.isoformat()} (manual_review). "
        f"Evidence {artifact.filename} [{artifact.sha256[:12]}]. Reviewer note: {body.review_note}", artifact.id,
    )
    db.commit()
    return _case_with_events(db, case)


@router.post("/cooperative/receivables/cases/{case_id}/information-response")
def submit_requested_information(
    case_id: UUID, body: InformationResponseCreate,
    user: User = Depends(current_user), db: Session = Depends(get_scoped_db),
):
    case = _seller_case(db, user, case_id)
    if case.status != "submitted":
        raise HTTPException(409, "Requested information can be sent only while the claim is with the processor")
    latest_response = db.query(CounterpartyConfirmation).filter_by(
        case_id=case.id, organization_id=case.organization_id,
    ).order_by(CounterpartyConfirmation.confirmed_at.desc(), CounterpartyConfirmation.created_at.desc()).first()
    if not latest_response or latest_response.response_status != "needs_information":
        raise HTTPException(409, "The processor has not requested additional information on this claim")
    linked_ids = {
        row[0] for row in db.query(ReceivableEvidenceLink.artifact_id).filter(
            ReceivableEvidenceLink.case_id == case.id,
            ReceivableEvidenceLink.organization_id == case.organization_id,
            ReceivableEvidenceLink.artifact_id.in_(body.evidence_artifact_ids),
        ).all()
    }
    if linked_ids != set(body.evidence_artifact_ids):
        raise HTTPException(422, "Every response file must already be attached to this claim")
    artifacts = [_artifact(db, case.organization_id, artifact_id) for artifact_id in body.evidence_artifact_ids]
    case.updated_at = datetime.now(timezone.utc)
    references = ", ".join(f"{artifact.filename} [{artifact.sha256[:12]}]" for artifact in artifacts)
    _event(
        db, case, user, "claim_information_submitted", "submitted", "submitted",
        f"Cooperative response to processor information request: {body.response_note}. Supporting files: {references}",
        artifacts[0].id,
    )
    db.commit()
    return _case_with_events(db, case)


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
    await run_in_threadpool(_scan_uploaded_evidence, content)
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
    ).order_by(ReceivableCase.updated_at.desc(), ReceivableCase.created_at.desc()).all()
    return [_case_json(db, row, include_private=False) for row in rows]


@router.get("/processor/receivables/cases/{case_id}")
def processor_case(case_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    return _case_with_events(db, _processor_case(db, user, case_id))


@router.post("/processor/receivables/cases/{case_id}/evidence", status_code=201)
async def upload_processor_case_evidence(
    case_id: UUID,
    file: UploadFile = File(...),
    artifact_type: str = Form("processor_statement"),
    source_reference: str = Form(""),
    source_locator: str = Form(""),
    user: User = Depends(current_user), db: Session = Depends(get_scoped_db),
):
    case = _processor_case(db, user, case_id)
    if case.status in {"paid", "closed"}:
        raise HTTPException(409, "Processor evidence cannot be added to a paid or closed claim")
    if not storage_ready():
        raise HTTPException(503, "Private evidence storage is not configured")
    filename = PurePath((file.filename or "evidence").replace("\\", "/")).name[:255]
    suffix = PurePath(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOADS:
        raise HTTPException(415, "Only PDF and UTF-8 CSV evidence files are accepted")
    content = await file.read(settings.evidence_max_file_bytes + 1)
    await file.close()
    if not content or len(content) > settings.evidence_max_file_bytes:
        raise HTTPException(413, f"Evidence file must be 1 byte to {settings.evidence_max_file_bytes} bytes")
    declared, signature = ALLOWED_UPLOADS[suffix]
    if signature and not content.startswith(signature):
        raise HTTPException(415, "File contents do not match the declared PDF format")
    if suffix == ".csv":
        try:
            decoded = content.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError as exc:
            raise HTTPException(415, "CSV evidence must be valid UTF-8 text") from exc
        if "\x00" in decoded:
            raise HTTPException(415, "CSV evidence contains invalid binary data")
    await run_in_threadpool(_scan_uploaded_evidence, content)
    allowed_artifact_types = {"processor_statement", "settlement_advice", "quality_report", "payment_advice", "other"}
    if artifact_type not in allowed_artifact_types:
        raise HTTPException(422, "Choose a supported processor evidence type")

    processor = _processor_org(db, user)
    sha256 = hashlib.sha256(content).hexdigest()
    artifact = db.query(EvidenceArtifact).filter_by(organization_id=processor.id, sha256=sha256).first()
    created_object_key = None
    if artifact is None:
        artifact_id = uuid4()
        key = safe_key(processor.id, case.id, artifact_id, suffix)
        try:
            put_private(key, content, declared)
        except Exception as exc:
            log.exception("Processor evidence write failed (%s)", type(exc).__name__)
            raise HTTPException(503, "Evidence storage is temporarily unavailable") from exc
        created_object_key = key
        artifact = EvidenceArtifact(
            id=artifact_id, organization_id=processor.id, uploaded_by=user.id,
            source_party="counterparty", source_system="processor_upload",
            source_reference=source_reference.strip()[:160], filename=filename,
            media_type=declared, artifact_type=artifact_type, sha256=sha256,
            storage_key=key, sensitivity="confidential",
            source_metadata={"size_bytes": len(content), "validation": "extension_magic_utf8"},
        )
        db.add(artifact)
        db.flush()
    existing_link = db.query(CounterpartyCaseEvidence.id).filter_by(
        case_id=case.id, artifact_id=artifact.id, source_locator=source_locator.strip()[:180],
    ).first()
    if existing_link:
        if created_object_key:
            db.rollback()
            delete_private(created_object_key)
        return JSONResponse(status_code=200, content={
            "id": str(artifact.id), "filename": artifact.filename,
            "media_type": artifact.media_type, "artifact_type": artifact.artifact_type,
            "sha256": artifact.sha256, "source_party": artifact.source_party,
            "size_bytes": (artifact.source_metadata or {}).get("size_bytes"),
            "created_at": artifact.created_at.isoformat(), "already_attached": True,
        })

    db.add(CounterpartyCaseEvidence(
        organization_id=case.organization_id, case_id=case.id,
        counterparty_organization_id=processor.id, artifact_id=artifact.id,
        source_locator=source_locator.strip()[:180], linked_by=user.id,
    ))
    case.updated_at = datetime.now(timezone.utc)
    _event(
        db, case, user, "processor_evidence_attached", case.status, case.status,
        f"Processor source evidence attached: {filename} [{sha256[:12]}]",
        artifact.id,
    )
    db.add(AuditLog(
        user_id=user.id, action="receivable.processor_evidence_attached", entity_type="receivable_case",
        entity_id=str(case.id), metadata_json={
            "organization_id": str(case.organization_id), "counterparty_organization_id": str(processor.id),
            "artifact_id": str(artifact.id), "sha256": sha256,
        },
    ))
    try:
        db.commit()
    except Exception:
        db.rollback()
        if created_object_key:
            try:
                delete_private(created_object_key)
            except Exception:
                log.exception("Could not remove orphaned processor evidence after database failure")
        raise
    return {
        "id": str(artifact.id), "filename": artifact.filename,
        "media_type": artifact.media_type, "artifact_type": artifact.artifact_type,
        "sha256": artifact.sha256, "source_party": artifact.source_party,
        "size_bytes": (artifact.source_metadata or {}).get("size_bytes"),
        "created_at": artifact.created_at.isoformat(),
    }


@router.post("/processor/receivables/cases/{case_id}/lines/{line_id}/review", status_code=201)
def review_processor_case_line(
    case_id: UUID, line_id: UUID, body: CounterpartyLineReviewCreate,
    user: User = Depends(current_user), db: Session = Depends(get_scoped_db),
):
    case = _processor_case(db, user, case_id)
    if case.status in {"paid", "closed"}:
        raise HTTPException(409, "A paid or closed claim no longer accepts line reviews")
    processor = _processor_org(db, user)
    line = db.query(ReceivableCaseLine).filter_by(
        id=line_id, case_id=case.id, organization_id=case.organization_id,
    ).first()
    if not line:
        raise HTTPException(404, "Claim line was not found")
    same_value = body.processor_amount == line.amount and body.processor_direction == line.direction
    if body.review_status == "matched" and not same_value:
        raise HTTPException(422, "A matched line must have the same amount and direction as the seller's source line")
    if body.review_status == "value_differs" and same_value:
        raise HTTPException(422, "Use matched when the processor-side amount and direction equal the seller's line")
    if body.evidence_artifact_id is not None and not db.query(CounterpartyCaseEvidence.id).filter_by(
        case_id=case.id, counterparty_organization_id=processor.id,
        artifact_id=body.evidence_artifact_id,
    ).first():
        raise HTTPException(422, "Attach processor evidence to this claim before citing it in a line review")

    review = CounterpartyLineReview(
        organization_id=case.organization_id, case_id=case.id, case_line_id=line.id,
        counterparty_organization_id=processor.id, reviewed_by_user_id=user.id,
        review_status=body.review_status, seller_amount_snapshot=line.amount,
        processor_amount=body.processor_amount, processor_direction=body.processor_direction,
        seller_direction_snapshot=line.direction,
        currency=case.currency, processor_reference=body.processor_reference,
        source_locator=body.source_locator, review_note=body.review_note,
        evidence_artifact_id=body.evidence_artifact_id,
    )
    db.add(review)
    case.updated_at = datetime.now(timezone.utc)
    _event(
        db, case, user, "processor_line_review_recorded", case.status, case.status,
        f"Processor line review recorded for line {line.line_number}: {body.review_status}; "
        f"processor reference {body.processor_reference or 'not supplied'}.", body.evidence_artifact_id,
    )
    db.add(AuditLog(
        user_id=user.id, action="receivable.processor_line_review", entity_type="receivable_case_line",
        entity_id=str(line.id), metadata_json={
            "organization_id": str(case.organization_id), "case_id": str(case.id),
            "counterparty_organization_id": str(processor.id), "review_status": body.review_status,
            "seller_amount": str(line.amount),
            "processor_amount": str(body.processor_amount) if body.processor_amount is not None else None,
            "processor_direction": body.processor_direction,
            "evidence_artifact_id": str(body.evidence_artifact_id) if body.evidence_artifact_id else None,
        },
    ))
    db.commit()
    return _case_with_events(db, case)


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
    seller_link = db.query(ReceivableEvidenceLink.id).filter_by(
        case_id=case.id, organization_id=org_id, artifact_id=artifact_id,
    ).first()
    counterparty_link = db.query(CounterpartyCaseEvidence.id).filter_by(
        case_id=case.id, artifact_id=artifact_id,
    ).first()
    line_review_link = db.query(CounterpartyLineReview.id).filter_by(
        case_id=case.id, evidence_artifact_id=artifact_id,
    ).first()
    if not (seller_link or counterparty_link or line_review_link):
        raise HTTPException(404, "Evidence is not linked to this claim")
    artifact = db.query(EvidenceArtifact).filter_by(id=artifact_id).first()
    if not artifact:
        raise HTTPException(404, "Evidence is not available to this account")
    content = _verified_artifact_bytes(artifact)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", artifact.filename)[:120] or "evidence"
    return Response(content, media_type=artifact.media_type, headers={"Content-Disposition": f'attachment; filename="{safe_name}"', "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router.get("/cooperative/receivables/cases/{case_id}/evidence-export")
def evidence_export(case_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    case = _seller_case(db, user, case_id)
    data = _case_with_events(db, case)
    artifacts = []
    for item in data["evidence"]:
        artifact = db.query(EvidenceArtifact).filter_by(id=UUID(item["id"])).first()
        if not artifact:
            raise HTTPException(409, "A linked evidence file is not available for this export")
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
            archive.writestr("processor-line-reviews.csv", _csv_text(data["line_reviews"]))
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
