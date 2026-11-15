from datetime import date, timedelta
from uuid import uuid4

from app.config import settings
from app.main import app
from app.security import current_identity

FARM_ID = "8b1199df-8901-4ba2-9e33-c191f20d43ea"
ANIMAL_ID = "8b1199df-8901-4ba2-9e33-c191f20d4401"


def test_real_onboarding_creates_private_farmer_account(client, monkeypatch):
    from app import main

    user_id = str(uuid4())
    identity = {"sub": user_id, "email": "unverified@example.test", "user_metadata": {"full_name": "New Farmer", "role": "platform_admin"}, "demo": False}
    monkeypatch.setattr(settings, "supabase_url", "https://terravanta-test.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "test-publishable-key")
    monkeypatch.setattr(main, "verified_supabase_user", lambda token, subject: {
        "id": str(subject), "email": "new.farmer@example.test", "email_confirmed_at": "2026-01-01T00:00:00Z",
        "user_metadata": {"full_name": "New Farmer", "role": "platform_admin"},
    })
    app.dependency_overrides[current_identity] = lambda: identity
    try:
        created = client.post("/api/v1/auth/onboard", headers={"Authorization": "Bearer confirmed-session"})
        assert created.status_code == 200
        assert created.json()["role"] == "farmer"
        assert created.json()["roles"] == ["farmer"]
        assert created.json()["created"] is True
        assert client.get("/api/v1/farms", headers={"Authorization": "Bearer onboarding-test"}).json() == []
        repeated = client.post("/api/v1/auth/onboard", headers={"Authorization": "Bearer confirmed-session"})
        assert repeated.status_code == 200
        assert repeated.json()["created"] is False
    finally:
        app.dependency_overrides.pop(current_identity, None)


def test_real_onboarding_does_not_provision_unconfirmed_email(client, monkeypatch):
    from fastapi import HTTPException
    from app import main

    user_id = str(uuid4())
    identity = {"sub": user_id, "email": "farmer@example.test", "demo": False}
    monkeypatch.setattr(settings, "supabase_url", "https://terravanta-test.supabase.co")

    def unconfirmed_provider_user(token, subject):
        raise HTTPException(status_code=403, detail="Confirm your email address before creating a Terravanta account")

    monkeypatch.setattr(main, "verified_supabase_user", unconfirmed_provider_user)
    app.dependency_overrides[current_identity] = lambda: identity
    try:
        response = client.post("/api/v1/auth/onboard", headers={"Authorization": "Bearer unconfirmed-session"})
        assert response.status_code == 403
        assert response.json()["detail"].startswith("Confirm your email")
        assert client.get("/api/v1/farms", headers={"Authorization": "Bearer unconfirmed-session"}).status_code == 401
    finally:
        app.dependency_overrides.pop(current_identity, None)


def test_demo_login_requires_explicit_synthetic_data_flag(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_synthetic_data", False)
    assert client.post("/api/v1/auth/demo-login?role=farmer").status_code == 404


def test_demo_data_and_farm_access(client, farmer_headers):
    dashboard = client.get("/api/v1/dashboard", headers=farmer_headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["synthetic"] is True
    assert dashboard.json()["stats"]["animals"] == 4
    assert client.get(f"/api/v1/farms/{FARM_ID}/animals", headers=farmer_headers).status_code == 200


def test_server_enforces_farm_membership(client):
    token = client.post("/api/v1/auth/demo-login?role=cooperative_admin").json()["access_token"]
    response = client.get(f"/api/v1/farms/{FARM_ID}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404


def test_vet_record_is_verified_and_visible(client, vet_headers):
    response = client.post(f"/api/v1/animals/{ANIMAL_ID}/health-events", headers=vet_headers, json={
        "event_type": "clinical_observation", "occurred_on": date.today().isoformat(),
        "summary": "Follow-up examination note recorded.", "observations": {"appetite": "improved"}, "verify_record": True,
    })
    assert response.status_code == 201
    assert response.json()["verified"] is True
    history = client.get(f"/api/v1/animals/{ANIMAL_ID}/health-events", headers=vet_headers).json()
    assert any(row["id"] == response.json()["id"] for row in history)


def test_veterinarian_can_verify_farmer_submitted_record(client, farmer_headers, vet_headers):
    created = client.post(f"/api/v1/animals/{ANIMAL_ID}/health-events", headers=farmer_headers, json={
        "event_type": "clinical_observation", "occurred_on": date.today().isoformat(),
        "summary": "Farmer note awaiting veterinary review.", "observations": {"appetite": "not recorded"},
    })
    assert created.status_code == 201
    assert created.json()["verified"] is False
    verified = client.post(f"/api/v1/health-events/{created.json()['id']}/verify", headers=vet_headers)
    assert verified.status_code == 200
    assert verified.json()["verified"] is True
    assert verified.json()["verified_by"]
    assert client.post(f"/api/v1/health-events/{created.json()['id']}/verify", headers=farmer_headers).status_code == 403


def test_veterinarian_cannot_write_farmer_production(client, vet_headers):
    response = client.post(f"/api/v1/farms/{FARM_ID}/production-records", headers=vet_headers, json={
        "product_type": "milk", "quantity": 3, "unit": "L", "recorded_on": date.today().isoformat(),
    })
    assert response.status_code == 403


def test_delivery_sharing_and_revocation(client, farmer_headers):
    coop_token = client.post("/api/v1/auth/demo-login?role=cooperative_admin").json()["access_token"]
    coop_headers = {"Authorization": f"Bearer {coop_token}"}
    assert len(client.get("/api/v1/cooperative/deliveries", headers=coop_headers).json()) >= 1
    consent = client.get(f"/api/v1/farms/{FARM_ID}/passport", headers=farmer_headers).json()["sharing"][0]
    revoked = client.delete(f"/api/v1/consents/{consent['id']}", headers=farmer_headers)
    assert revoked.status_code == 200
    assert client.get("/api/v1/cooperative/deliveries", headers=coop_headers).json() == []


def cooperative_headers(client):
    token = client.post("/api/v1/auth/demo-login?role=cooperative_admin").json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def collection_csv(quantity="20.7", reference="DEMO-DEL-014", farm_code="TV-KBU-0042"):
    return f"farm_code,collection_date,milk_litres,receipt_reference\n{farm_code},{date.today().isoformat()},{quantity},{reference}\n".encode()


def test_cooperative_intake_is_linked_to_auditable_trace(client):
    headers = cooperative_headers(client)
    imported = client.post("/api/v1/cooperative/reconciliation/runs", headers=headers,
                           files={"file": ("today.csv", collection_csv(), "text/csv")})
    assert imported.status_code == 201
    body = imported.json()
    assert body["run"]["matched_rows"] == 1
    assert body["items"][0]["status"] == "matched"
    assert body["items"][0]["farm_name"] == "Greenridge Mixed Farm"
    assert [node["type"] for node in body["items"][0]["trace_graph"]] == [
        "farm", "production_record", "product_lot", "delivery", "cooperative_intake",
    ]
    duplicate = client.post("/api/v1/cooperative/reconciliation/runs", headers=headers,
                            files={"file": ("today-again.csv", collection_csv(), "text/csv")})
    assert duplicate.status_code == 409
    assert client.get(f"/api/v1/cooperative/reconciliation/runs/{body['run']['id']}", headers=headers).status_code == 200


def test_cooperative_reviewer_must_resolve_linked_exception(client):
    headers = cooperative_headers(client)
    imported = client.post("/api/v1/cooperative/reconciliation/runs", headers=headers,
                           files={"file": ("quantity-gap.csv", collection_csv(quantity="21.7"), "text/csv")})
    assert imported.status_code == 201
    item = imported.json()["items"][0]
    assert item["status"] == "quantity_mismatch"
    assert item["matched_delivery"] is not None
    missing_note = client.post(f"/api/v1/cooperative/reconciliation/items/{item['id']}/review", headers=headers,
                               json={"decision": "follow_up", "note": "  "})
    assert missing_note.status_code == 422
    reviewed = client.post(f"/api/v1/cooperative/reconciliation/items/{item['id']}/review", headers=headers,
                           json={"decision": "confirmed", "note": "Checked paper intake receipt"})
    assert reviewed.status_code == 200
    assert reviewed.json()["items"][0]["review_status"] == "confirmed"
    assert reviewed.json()["run"]["resolved_rows"] == 1


def test_consent_revocation_hides_farm_delivery_and_blocks_confirmation(client, farmer_headers):
    headers = cooperative_headers(client)
    imported_before_revoke = client.post("/api/v1/cooperative/reconciliation/runs", headers=headers,
                                         files={"file": ("before-revoke.csv", collection_csv(quantity="21.7"), "text/csv")})
    assert imported_before_revoke.status_code == 201
    previously_matched = imported_before_revoke.json()["items"][0]
    assert previously_matched["farm_name"] == "Greenridge Mixed Farm"
    grants = client.get(f"/api/v1/farms/{FARM_ID}/passport", headers=farmer_headers).json()["sharing"]
    for grant in grants:
        if grant["status"] == "active":
            assert client.delete(f"/api/v1/consents/{grant['id']}", headers=farmer_headers).status_code == 200
    after_revoke = client.get(
        f"/api/v1/cooperative/reconciliation/runs/{imported_before_revoke.json()['run']['id']}", headers=headers,
    ).json()["items"][0]
    assert after_revoke["status"] == "consent_revoked"
    assert after_revoke["farm_name"] is None
    assert after_revoke["matched_delivery"] is None
    blocked_review = client.post(
        f"/api/v1/cooperative/reconciliation/items/{previously_matched['id']}/review", headers=headers,
        json={"decision": "confirmed", "note": "Checked"},
    )
    assert blocked_review.status_code == 403
    imported = client.post("/api/v1/cooperative/reconciliation/runs", headers=headers,
                           files={"file": ("not-shared.csv", collection_csv(reference="R-UNSHARED"), "text/csv")})
    assert imported.status_code == 201
    item = imported.json()["items"][0]
    assert item["status"] == "not_shared"
    assert item["farm_name"] is None
    assert item["matched_delivery"] is None
    assert item["trace_graph"][-1]["type"] == "exception"
    assert client.get("/api/v1/cooperative/deliveries", headers=headers).json() == []


def test_reconciliation_is_cooperative_role_only(client, farmer_headers):
    response = client.get("/api/v1/cooperative/reconciliation/runs", headers=farmer_headers)
    assert response.status_code == 403


def test_delivery_consent_can_target_verified_cooperative_email(client, farmer_headers):
    coop_token = client.post("/api/v1/auth/demo-login?role=cooperative_admin").json()["access_token"]
    coop_headers = {"Authorization": f"Bearer {coop_token}"}
    existing = client.get(f"/api/v1/farms/{FARM_ID}/passport", headers=farmer_headers).json()["sharing"]
    for grant in existing:
        if grant["status"] == "active":
            client.delete(f"/api/v1/consents/{grant['id']}", headers=farmer_headers)

    granted = client.post(f"/api/v1/farms/{FARM_ID}/consents", headers=farmer_headers, json={
        "scope": "delivery_summary", "grantee_email": "cooperative@terravanta.demo",
    })
    assert granted.status_code == 201
    deliveries = client.get("/api/v1/cooperative/deliveries", headers=coop_headers)
    assert deliveries.status_code == 200
    assert deliveries.json()
    assert all(row["scope"] == "delivery_summary" for row in deliveries.json())


def test_cooperative_directory_and_duplicate_consent_guard(client, farmer_headers):
    cooperatives = client.get("/api/v1/cooperatives", headers=farmer_headers)
    assert cooperatives.status_code == 200
    cooperative = next(row for row in cooperatives.json() if row["name"] == "Githunguri Demo Dairy Cooperative")
    duplicate = client.post(f"/api/v1/farms/{FARM_ID}/consents", headers=farmer_headers, json={
        "scope": "delivery_summary", "grantee_org_id": cooperative["id"],
    })
    assert duplicate.status_code == 409


def test_ai_requires_explicit_external_processing(client, farmer_headers):
    response = client.post("/api/v1/ai/veterinary-assistant", headers=farmer_headers, json={"animal_id": ANIMAL_ID, "question": "Summarize the recorded case history", "allow_external_processing": False})
    assert response.status_code == 200
    assert response.json()["status"] == "consent_required"
    assert response.json()["model_generated"] is False


def test_follow_up_alert_has_explainable_trigger(client, farmer_headers):
    alerts = client.get("/api/v1/alerts", headers=farmer_headers).json()
    assert any("follow-up" in row["title"].lower() and row["trigger"] for row in alerts)


def test_farm_registration_can_add_plot_and_animal(client, farmer_headers):
    created = client.post("/api/v1/farms", headers=farmer_headers, json={
        "name": "Test mixed holding", "owner_name": "Test Farmer", "county": "Kiambu",
        "subcounty": "Githunguri", "size_acres": 2.0, "farming_system": "mixed",
        "production_activities": ["Dairy", "Fodder"],
    })
    assert created.status_code == 201
    farm_id = created.json()["id"]
    plot = client.post(f"/api/v1/farms/{farm_id}/plots", headers=farmer_headers, json={"name": "Fodder plot", "area_acres": 0.5, "crop_type": "Napier", "is_feed_crop": True})
    animal = client.post(f"/api/v1/farms/{farm_id}/animals", headers=farmer_headers, json={"tag": "TEST-01", "name": "Test cow", "species": "Cattle", "breed": "Cross", "sex": "female"})
    assert plot.status_code == animal.status_code == 201
    assert client.get(f"/api/v1/farms/{farm_id}/animals", headers=farmer_headers).json()[0]["tag"] == "TEST-01"


def test_feed_allocation_reduces_batch_inventory(client, farmer_headers):
    plots = client.get(f"/api/v1/farms/{FARM_ID}/plots", headers=farmer_headers).json()
    animals = client.get(f"/api/v1/farms/{FARM_ID}/animals", headers=farmer_headers).json()
    batch = client.post(f"/api/v1/farms/{FARM_ID}/feed-batches", headers=farmer_headers, json={
        "name": "Test fodder batch", "quantity_kg": 10, "batch_date": date.today().isoformat(), "plot_id": plots[0]["id"], "ingredients": ["Napier"],
    })
    assert batch.status_code == 201
    allocation = client.post(f"/api/v1/farms/{FARM_ID}/feed-allocations", headers=farmer_headers, json={
        "feed_batch_id": batch.json()["id"], "animal_id": animals[0]["id"], "allocated_kg": 2, "allocated_on": date.today().isoformat(),
    })
    assert allocation.status_code == 201
    excessive = client.post(f"/api/v1/farms/{FARM_ID}/feed-allocations", headers=farmer_headers, json={
        "feed_batch_id": batch.json()["id"], "animal_id": animals[0]["id"], "allocated_kg": 9, "allocated_on": date.today().isoformat(),
    })
    assert excessive.status_code == 422
    updated = client.get(f"/api/v1/farms/{FARM_ID}/feed-batches", headers=farmer_headers).json()
    assert next(row for row in updated if row["id"] == batch.json()["id"])["quantity_kg"] == 8


def test_compost_application_cannot_exceed_batch_quantity(client, farmer_headers):
    plots = client.get(f"/api/v1/farms/{FARM_ID}/plots", headers=farmer_headers).json()
    compost = client.post(f"/api/v1/farms/{FARM_ID}/compost-batches", headers=farmer_headers, json={
        "name": "Test compost batch", "quantity_kg": 3, "created_on": date.today().isoformat(),
    })
    assert compost.status_code == 201
    def apply(quantity):
        return client.post(f"/api/v1/farms/{FARM_ID}/compost-applications", headers=farmer_headers, json={
            "compost_batch_id": compost.json()["id"], "plot_id": plots[0]["id"],
            "quantity_kg": quantity, "applied_on": date.today().isoformat(),
        })
    assert apply(2).status_code == 201
    assert apply(2).status_code == 422


def test_delivery_traces_to_source_production(client, farmer_headers):
    records = client.get(f"/api/v1/farms/{FARM_ID}/production-records", headers=farmer_headers).json()
    deliveries = client.get(f"/api/v1/farms/{FARM_ID}/deliveries", headers=farmer_headers).json()
    already_used = {row["lot"]["production_record_id"] for row in deliveries}
    source = next(row for row in records if row["id"] not in already_used)
    result = client.post(f"/api/v1/farms/{FARM_ID}/deliveries", headers=farmer_headers, json={
        "production_record_id": source["id"], "buyer_name": "Test Cooperative", "delivery_date": date.today().isoformat(),
        "quantity": source["quantity"], "unit": source["unit"], "reference": "TEST-LOT",
    })
    assert result.status_code == 201
    assert result.json()["product_lot"]["production_record_id"] == source["id"]


def test_invalid_document_signature_is_rejected(client, farmer_headers):
    response = client.post(f"/api/v1/documents/extract?farm_id={FARM_ID}", headers=farmer_headers, files={"file": ("record.png", b"not-a-png", "image/png")})
    assert response.status_code == 415


def test_nvidia_provider_failure_returns_safe_fallback(client, farmer_headers, monkeypatch):
    from app import main

    monkeypatch.setattr(main.settings, "nvidia_api_key", "test-key")

    async def unavailable(*args, **kwargs):
        raise RuntimeError("simulated provider outage")

    monkeypatch.setattr(main.nvidia, "chat", unavailable)
    response = client.post("/api/v1/ai/veterinary-assistant", headers=farmer_headers, json={
        "animal_id": ANIMAL_ID, "question": "Summarize the recorded case history", "allow_external_processing": True,
    })
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["model_generated"] is False
