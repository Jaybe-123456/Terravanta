import hashlib
import hmac
import json

import pytest

from app.config import settings
from app.models import (
    CommunicationOutbox,
    FarmDomainEvent,
    MetaWebhookEvent,
    Notification,
    VeterinaryContactMessage,
    WhatsAppLinkChallenge,
    WhatsAppPreference,
)
from app.seed import FARMER_ID, FARM_ID, VET_ID


WEBHOOK_PATH = "/api/v1/integrations/meta/whatsapp/webhook"
APP_SECRET = "local-test-meta-secret"
VERIFY_TOKEN = "local-test-verify-token"
PHONE_NUMBER_ID = "test-phone-number-id"


def configure_meta(monkeypatch):
    monkeypatch.setattr(settings, "meta_wa_app_secret", APP_SECRET)
    monkeypatch.setattr(settings, "meta_wa_verify_token", VERIFY_TOKEN)
    monkeypatch.setattr(settings, "meta_wa_phone_number_id", PHONE_NUMBER_ID)
    monkeypatch.setattr(settings, "meta_wa_business_number", "+254700000000")
    monkeypatch.setattr(settings, "whatsapp_pairing_secret", "local-pairing-hmac-secret")
    monkeypatch.setattr(settings, "meta_wa_send_enabled", False)


def signed_post(client, payload):
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return client.post(
        WEBHOOK_PATH,
        content=raw_body,
        headers={"content-type": "application/json", "x-hub-signature-256": f"sha256={signature}"},
    )


def message_payload(phone, message_id, body):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": PHONE_NUMBER_ID},
                    "messages": [{
                        "from": phone,
                        "id": message_id,
                        "timestamp": "1760000000",
                        "type": "text",
                        "text": {"body": body},
                    }],
                },
            }],
        }],
    }


def pair_farmer_number(client, farmer_headers, phone):
    created = client.post(
        "/api/v1/me/whatsapp/pairing",
        headers=farmer_headers,
        json={"consent_accepted": True},
    )
    assert created.status_code == 201
    code = created.json()["pairing_code"]
    response = signed_post(client, message_payload(phone, f"wamid.pair-{phone}", f"TVLINK {code}"))
    assert response.status_code == 200
    return code


def test_meta_webhook_get_handshake_and_reject_bad_verify_token(client, monkeypatch):
    configure_meta(monkeypatch)

    accepted = client.get(WEBHOOK_PATH, params={
        "hub.mode": "subscribe",
        "hub.verify_token": VERIFY_TOKEN,
        "hub.challenge": "challenge-value-123",
    })
    assert accepted.status_code == 200
    assert accepted.text == "challenge-value-123"
    assert accepted.headers["content-type"].startswith("text/plain")

    rejected = client.get(WEBHOOK_PATH, params={
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong-token",
        "hub.challenge": "challenge-value-123",
    })
    assert rejected.status_code == 403


def test_meta_webhook_requires_signature_and_rejects_oversized_payload(client, monkeypatch):
    configure_meta(monkeypatch)

    unsigned = client.post(WEBHOOK_PATH, content=b'{"entry":[]}', headers={"content-type": "application/json"})
    assert unsigned.status_code == 401

    too_large = client.post(WEBHOOK_PATH, content=b"x" * 1_000_001)
    assert too_large.status_code == 413


def test_pairing_requires_consent_and_signed_inbound_message_links_number(
    client, farmer_headers, whatsapp_db_session_factory, monkeypatch,
):
    configure_meta(monkeypatch)

    denied = client.post(
        "/api/v1/me/whatsapp/pairing",
        headers=farmer_headers,
        json={"consent_accepted": False},
    )
    assert denied.status_code == 422
    with whatsapp_db_session_factory() as db:
        assert db.query(WhatsAppLinkChallenge).count() == 0

    code = pair_farmer_number(client, farmer_headers, "254712345678")
    status = client.get("/api/v1/me/whatsapp", headers=farmer_headers)
    assert status.status_code == 200
    assert status.json()["linked"] is True
    assert status.json()["phone_masked"].endswith("678")

    with whatsapp_db_session_factory() as db:
        preference = db.get(WhatsAppPreference, FARMER_ID)
        challenge = db.query(WhatsAppLinkChallenge).one()
        assert preference.phone_e164 == "+254712345678"
        assert preference.verified_at is not None
        assert preference.consent_granted_at is not None
        assert preference.consent_revoked_at is None
        assert challenge.consumed_at is not None
        assert challenge.code_hash != code
        assert db.query(MetaWebhookEvent).filter_by(event_type="inbound_message").one().processing_status == "processed"


def test_inbound_conversation_message_is_linked_and_idempotent(
    client, farmer_headers, whatsapp_db_session_factory, monkeypatch,
):
    configure_meta(monkeypatch)
    request = client.post(
        f"/api/v1/farms/{FARM_ID}/veterinary-contact-requests",
        headers=farmer_headers,
        json={"message": "Please contact me about the animal", "urgency": "routine"},
    )
    assert request.status_code == 201
    conversation_code = request.json()["conversation_code"]
    pair_farmer_number(client, farmer_headers, "254712345678")

    payload = message_payload("254712345678", "wamid.conversation-1", f"TV {conversation_code} The animal is eating again.")
    first = signed_post(client, payload)
    repeated = signed_post(client, payload)
    assert first.status_code == 200
    assert repeated.status_code == 200

    with whatsapp_db_session_factory() as db:
        saved = db.query(VeterinaryContactMessage).filter_by(external_message_id="wamid.conversation-1").all()
        assert len(saved) == 1
        assert saved[0].source_channel == "whatsapp"
        assert saved[0].body == "The animal is eating again."
        assert saved[0].request_id.hex == request.json()["id"].replace("-", "")
        assert db.query(FarmDomainEvent).filter_by(idempotency_key="whatsapp-message:wamid.conversation-1:event").count() == 1
        assert db.query(Notification).filter_by(
            recipient_user_id=VET_ID,
            idempotency_key="whatsapp-message:wamid.conversation-1:notification:" + str(VET_ID),
        ).count() == 1
        assert db.query(MetaWebhookEvent).filter_by(provider_event_id="message:wamid.conversation-1").one().processing_status == "processed"


def test_unlinked_number_cannot_post_into_private_conversation(
    client, farmer_headers, whatsapp_db_session_factory, monkeypatch,
):
    configure_meta(monkeypatch)
    request = client.post(
        f"/api/v1/farms/{FARM_ID}/veterinary-contact-requests",
        headers=farmer_headers,
        json={"message": "Please contact me", "urgency": "routine"},
    )
    assert request.status_code == 201
    payload = message_payload(
        "254799999999", "wamid.unlinked-1",
        f"TV {request.json()['conversation_code']} private message from unlinked phone",
    )

    response = signed_post(client, payload)
    assert response.status_code == 200
    with whatsapp_db_session_factory() as db:
        assert db.query(VeterinaryContactMessage).filter_by(external_message_id="wamid.unlinked-1").count() == 0
        event = db.query(MetaWebhookEvent).filter_by(provider_event_id="message:wamid.unlinked-1").one()
        assert event.processing_status == "ignored"
        assert event.safe_error_code == "sender_not_linked_or_consent_inactive"


def test_signed_delivery_receipt_updates_outbox_idempotently(
    client, whatsapp_db_session_factory, monkeypatch,
):
    configure_meta(monkeypatch)
    outbox = CommunicationOutbox(
        recipient_user_id=FARMER_ID,
        body="Delivery test",
        status="sent",
        provider_message_id="wamid.outbound-1",
        idempotency_key="test-outbox-status-1",
    )
    with whatsapp_db_session_factory() as db:
        db.add(outbox)
        db.commit()

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": PHONE_NUMBER_ID},
            "statuses": [{"id": "wamid.outbound-1", "status": "delivered", "timestamp": "1760000001"}],
        }}]}],
    }
    assert signed_post(client, payload).status_code == 200
    assert signed_post(client, payload).status_code == 200

    with whatsapp_db_session_factory() as db:
        saved_outbox = db.get(CommunicationOutbox, outbox.id)
        assert saved_outbox.status == "delivered"
        assert db.query(MetaWebhookEvent).filter_by(provider_event_id="status:wamid.outbound-1:delivered").count() == 1


def test_unsupported_signed_json_shape_is_rejected(client, monkeypatch):
    configure_meta(monkeypatch)
    raw_body = b'{"object":"whatsapp_business_account","entry":{}}'
    signature = hmac.new(APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    response = client.post(
        WEBHOOK_PATH,
        content=raw_body,
        headers={"content-type": "application/json", "x-hub-signature-256": f"sha256={signature}"},
    )
    assert response.status_code == 400


def test_worker_does_not_send_when_delivery_is_disabled(monkeypatch):
    from app import worker

    configure_meta(monkeypatch)
    assert worker.process_whatsapp_outbox_once() == 0


def test_worker_one_shot_runs_one_bounded_pass(monkeypatch):
    from app import worker

    calls = {"workflows": 0, "whatsapp": 0}
    monkeypatch.setattr(settings, "service_mode", "worker")

    def process_workflows():
        calls["workflows"] += 1
        return 2

    def process_whatsapp():
        calls["whatsapp"] += 1
        return 1

    monkeypatch.setattr(worker, "process_due_workflows_once", process_workflows)
    monkeypatch.setattr(worker, "process_whatsapp_outbox_once", process_whatsapp)
    worker.main(["--once"])

    assert calls == {"workflows": 1, "whatsapp": 1}


def test_sender_uses_approved_template_outside_service_window(monkeypatch):
    from app import whatsapp

    monkeypatch.setattr(settings, "meta_wa_send_enabled", True)
    monkeypatch.setattr(settings, "meta_wa_access_token", "test-only-token")
    monkeypatch.setattr(settings, "meta_wa_phone_number_id", PHONE_NUMBER_ID)
    monkeypatch.setattr(settings, "meta_wa_graph_api_version", "v22.0")
    monkeypatch.setattr(settings, "meta_wa_notification_template", "vet_contact_update")
    captured = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"messages": [{"id": "wamid.mocked-send"}]}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, *, headers, json):
            captured.update({"url": url, "headers": headers, "payload": json})
            return FakeResponse()

    monkeypatch.setattr(whatsapp.httpx, "Client", FakeClient)
    result = whatsapp.send_whatsapp_message(
        to_phone="+254712345678",
        body="Private message body must not be sent in a template notification.",
        conversation_code="A1B2C3D4E5F6",
        in_service_window=False,
    )

    assert result.provider_message_id == "wamid.mocked-send"
    assert captured["payload"]["type"] == "template"
    assert captured["payload"]["template"]["name"] == "vet_contact_update"
    assert captured["payload"]["template"]["components"][0]["parameters"][0]["text"] == "A1B2C3D4E5F6"
    assert "Private message body" not in json.dumps(captured["payload"])


def test_sender_marks_meta_rate_limit_as_retryable(monkeypatch):
    from app import whatsapp

    monkeypatch.setattr(settings, "meta_wa_send_enabled", True)
    monkeypatch.setattr(settings, "meta_wa_access_token", "test-only-token")
    monkeypatch.setattr(settings, "meta_wa_phone_number_id", PHONE_NUMBER_ID)
    monkeypatch.setattr(settings, "meta_wa_graph_api_version", "v22.0")
    monkeypatch.setattr(settings, "meta_wa_notification_template", "vet_contact_update")

    class FakeResponse:
        status_code = 429

        @staticmethod
        def json():
            return {"error": {"code": 131047}}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def post(*_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(whatsapp.httpx, "Client", FakeClient)
    with pytest.raises(whatsapp.WhatsAppSendError) as raised:
        whatsapp.send_whatsapp_message(
            to_phone="+254712345678",
            body="A private message",
            conversation_code="A1B2C3D4E5F6",
            in_service_window=False,
        )

    assert raised.value.retryable is True
    assert raised.value.safe_code == "meta_131047"
