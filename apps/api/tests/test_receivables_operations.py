from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.models import (
    CounterpartyConfirmation, EvidenceArtifact, Organization, OrganizationMember,
    ReceivableCase, ReceivableCaseEvent, User, UserRole,
)
from app.receivables import _workflow_snapshot


def _cooperative_headers(client):
    token = client.post("/api/v1/auth/demo-login?role=cooperative_admin").json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_workflow_marks_partially_paid_as_reviewed_payment():
    snapshot = _workflow_snapshot(
        SimpleNamespace(status="partially_paid", due_date=None, due_date_basis="unknown"),
        evidence=[], lines=[], confirmations=[], relationship=None,
    )

    payment_step = next(step for step in snapshot["steps"] if step["key"] == "payment")
    assert payment_step["label"] == "Payment evidence reviewed"
    assert payment_step["complete"] is True


def _source_backed_case(client, db_session):
    headers = _cooperative_headers(client)
    cooperative = db_session.query(Organization).filter_by(kind="cooperative").first()
    cooperative_member = db_session.query(OrganizationMember).filter_by(organization_id=cooperative.id).first()
    processor_user = User(id=uuid4(), display_name="Processor reviewer", email="processor-reviewer@example.test")
    processor = Organization(id=uuid4(), name="Test processor", kind="processor")
    db_session.add_all([processor_user, processor])
    db_session.flush()
    db_session.add_all([
        UserRole(user_id=processor_user.id, role="processor_admin"),
        OrganizationMember(organization_id=processor.id, user_id=processor_user.id, role="processor_admin"),
    ])
    artifact = EvidenceArtifact(
        id=uuid4(), organization_id=cooperative.id, uploaded_by=cooperative_member.user_id,
        source_party="seller", source_system="test_fixture", source_reference="STMT-2026-17",
        filename="processor-statement.csv", media_type="text/csv", artifact_type="processor_statement",
        sha256="a" * 64, storage_key=f"test/{uuid4()}.csv", sensitivity="confidential",
        source_metadata={"size_bytes": 32, "validation": "test fixture"},
    )
    db_session.add(artifact)
    db_session.commit()

    relationship = client.post("/api/v1/cooperative/receivables/relationships", headers=headers, json={
        "counterparty_name": "Test processor", "relationship_type": "processor",
        "external_reference": f"SUPPLY-{uuid4()}", "counterparty_organization_id": str(processor.id),
    })
    assert relationship.status_code == 201
    created = client.post("/api/v1/cooperative/receivables/cases", headers=headers, json={
        "relationship_id": relationship.json()["id"], "source_document_type": "processor_statement",
        "source_reference": f"CLAIM-{uuid4()}", "invoice_date": (date.today() - timedelta(days=15)).isoformat(),
        "currency": "KES", "asserted_amount": "1234.00", "description": "Source-backed claim review",
        "lines": [{
            "line_type": "accepted_supply", "direction": "increase", "source_reference": "ROW-17",
            "amount": "1234.00", "source_locator": "processor-statement.csv:row-17",
            "evidence_artifact_id": str(artifact.id),
        }],
        "evidence_artifact_ids": [str(artifact.id)],
    })
    assert created.status_code == 201, created.text
    return headers, cooperative, processor, processor_user, artifact, created.json()


def test_claim_date_review_and_processor_information_loop_are_source_linked(client, db_session):
    headers, cooperative, processor, processor_user, artifact, claim = _source_backed_case(client, db_session)
    claim_id = claim["id"]

    reviewed = client.post(f"/api/v1/cooperative/receivables/cases/{claim_id}/due-date-review", headers=headers, json={
        "due_date": (date.today() - timedelta(days=12)).isoformat(),
        "evidence_artifact_id": str(artifact.id),
        "review_note": "Statement page 1 gives the payment due date.",
    })
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["workflow"]["due_date_source_supported"] is True
    assert any(item["evidence_role"] == "due_date_support" for item in reviewed.json()["evidence"])

    asserted = client.post(f"/api/v1/cooperative/receivables/cases/{claim_id}/assert", headers=headers)
    assert asserted.status_code == 200
    submitted = client.post(f"/api/v1/cooperative/receivables/cases/{claim_id}/submit", headers=headers)
    assert submitted.status_code == 200

    case = db_session.get(ReceivableCase, UUID(claim_id))
    now = datetime.now(timezone.utc)
    case.created_at = now - timedelta(days=4)
    submission = db_session.query(ReceivableCaseEvent).filter_by(case_id=case.id, event_type="claim_submitted").one()
    submission.created_at = now - timedelta(days=3)
    response_at = now - timedelta(days=2)
    db_session.add(CounterpartyConfirmation(
        organization_id=cooperative.id, case_id=case.id, counterparty_organization_id=processor.id,
        confirmed_by_user_id=processor_user.id, response_status="needs_information",
        asserted_amount_snapshot=Decimal("1234.00"), currency="KES", response_reference="AP-CASE-17",
        response_note="Please provide the signed intake row.", confirmed_at=response_at, created_at=response_at,
    ))
    db_session.add(ReceivableCaseEvent(
        organization_id=cooperative.id, case_id=case.id, actor_user_id=processor_user.id,
        event_type="processor_response_recorded", from_status="submitted", to_status="submitted",
        note="Processor requested a signed intake row.", created_at=response_at,
    ))
    db_session.commit()

    case_detail = client.get(f"/api/v1/cooperative/receivables/cases/{claim_id}", headers=headers)
    assert case_detail.status_code == 200
    assert case_detail.json()["workflow"]["stage"] == "information_requested"
    assert any(line["source_locator"] == "processor-statement.csv:row-17" for line in case_detail.json()["lines"])

    performance = client.get("/api/v1/cooperative/receivables/performance?window_days=90", headers=headers)
    assert performance.status_code == 200, performance.text
    metrics = performance.json()
    assert metrics["cohort"]["claims_opened"] == 1
    assert metrics["cohort"]["claims_submitted"] == 1
    assert metrics["timing"]["submission_timing_sample_size"] == 1
    assert metrics["timing"]["first_response_sample_size"] == 1
    assert metrics["rework"]["rate_percent"] == 100.0
    assert metrics["current_queue"]["stage_counts"]["information_requested"] == 1

    reply = client.post(f"/api/v1/cooperative/receivables/cases/{claim_id}/information-response", headers=headers, json={
        "evidence_artifact_ids": [str(artifact.id)],
        "response_note": "The attached statement row includes the signed intake reference.",
    })
    assert reply.status_code == 200, reply.text
    assert reply.json()["workflow"]["stage"] == "processor_review"
    assert any(event["event_type"] == "claim_information_submitted" for event in reply.json()["events"])

    current_performance = client.get("/api/v1/cooperative/receivables/performance?window_days=90", headers=headers).json()
    assert current_performance["current_queue"]["stage_counts"]["awaiting_processor"] == 1
