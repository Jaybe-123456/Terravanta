"""Authenticated WhatsApp pairing and signed Meta Cloud API webhook routes."""
import hashlib
import hmac
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text, update
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .config import settings
from .db import WhatsAppWebhookSessionLocal
from .models import (
    AuditLog, CommunicationOutbox, FarmMember, FarmDomainEvent, MetaWebhookEvent,
    Notification, User, VeterinaryContactMessage, VeterinaryContactRequest,
    WhatsAppLinkChallenge, WhatsAppPreference,
)
from .schemas import WhatsAppPairingCreate
from .security import current_user, get_scoped_db
from .whatsapp import (
    PAIRING_TERMS_VERSION,
    MAX_META_WEBHOOK_BYTES,
    normalize_phone_e164,
    pairing_code_hash,
    new_pairing_code,
    make_link_url,
)

router = APIRouter(tags=["WhatsApp integration"])
log = logging.getLogger("terravanta.whatsapp")


def _active_consent(row: WhatsAppPreference | None) -> bool:
    return bool(row and row.phone_e164 and row.verified_at and row.consent_granted_at and not row.consent_revoked_at)


def _masked_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    return f"{phone[:4]}••••{phone[-3:]}"


@router.get("/api/v1/me/whatsapp")
def get_whatsapp_status(user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    preference = db.get(WhatsAppPreference, user.id)
    return {
        "linked": _active_consent(preference),
        "phone_masked": _masked_phone(preference.phone_e164) if preference and _active_consent(preference) else None,
        "verified_at": preference.verified_at.isoformat() if preference and preference.verified_at else None,
        "consent_granted_at": preference.consent_granted_at.isoformat() if preference and preference.consent_granted_at else None,
        "consent_revoked_at": preference.consent_revoked_at.isoformat() if preference and preference.consent_revoked_at else None,
        "pairing_available": settings.whatsapp_pairing_configured,
        "delivery_available": settings.whatsapp_delivery_enabled,
        "notification_template_available": bool(settings.meta_wa_notification_template),
    }


@router.get("/api/v1/me/whatsapp/deliveries")
def get_whatsapp_deliveries(user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    rows = db.query(CommunicationOutbox).filter_by(recipient_user_id=user.id).order_by(
        CommunicationOutbox.created_at.desc(),
    ).limit(8).all()
    return [{
        "id": str(row.id),
        "status": row.status,
        "attempts": row.attempts,
        "error_code": row.last_error_code or None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    } for row in rows]


@router.post("/api/v1/me/whatsapp/pairing", status_code=201)
def create_whatsapp_pairing(
    body: WhatsAppPairingCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_scoped_db),
):
    if not settings.whatsapp_pairing_configured:
        raise HTTPException(503, "WhatsApp pairing is not enabled for this Terravanta deployment")
    preference = db.get(WhatsAppPreference, user.id)
    if _active_consent(preference):
        raise HTTPException(409, "A WhatsApp number is already linked. Revoke it before pairing another number.")

    now = datetime.now(timezone.utc)
    recent_count = db.query(WhatsAppLinkChallenge).filter(
        WhatsAppLinkChallenge.user_id == user.id,
        WhatsAppLinkChallenge.created_at >= now - timedelta(hours=1),
    ).count()
    if recent_count >= 3:
        raise HTTPException(429, "Too many pairing requests. Try again later.")

    code = new_pairing_code()
    challenge = WhatsAppLinkChallenge(
        user_id=user.id,
        code_hash=pairing_code_hash(code),
        consent_version=PAIRING_TERMS_VERSION,
        consent_accepted_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    db.add(challenge)
    db.flush()
    db.add(AuditLog(
        user_id=user.id,
        farm_id=None,
        action="whatsapp.pairing_started",
        entity_type="whatsapp_link_challenge",
        entity_id=str(challenge.id),
        metadata_json={"consent_version": PAIRING_TERMS_VERSION, "expires_in_minutes": 15},
    ))
    db.commit()
    return {
        "pairing_code": code,
        "whatsapp_link": make_link_url(code),
        "expires_at": challenge.expires_at.isoformat(),
        "instructions": "Open the link and press Send in WhatsApp to verify that you control this number. The code expires in 15 minutes and can be used once.",
    }


@router.delete("/api/v1/me/whatsapp")
def revoke_whatsapp(user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    if db.get_bind().dialect.name == "postgresql":
        revoked = bool(db.execute(
            text("SELECT terravanta_private.revoke_whatsapp_consent()")
        ).scalar_one())
    else:
        preference = db.get(WhatsAppPreference, user.id)
        revoked = bool(_active_consent(preference))
        if revoked and preference:
            preference.phone_e164 = None
            preference.verified_at = None
            preference.consent_revoked_at = datetime.now(timezone.utc)
            preference.updated_at = datetime.now(timezone.utc)
            db.query(CommunicationOutbox).filter(
                CommunicationOutbox.recipient_user_id == user.id,
                CommunicationOutbox.status.in_(("queued", "sending")),
            ).update({"status": "cancelled", "last_error_code": "consent_revoked"}, synchronize_session=False)
    if revoked:
        db.add(AuditLog(
            user_id=user.id,
            farm_id=None,
            action="whatsapp.consent_revoked",
            entity_type="whatsapp_channel_preference",
            entity_id=str(user.id),
            metadata_json={"channel": "whatsapp"},
        ))
    db.commit()
    return {"revoked": revoked}


def _verify_signature(raw_body: bytes, signature: str | None) -> bool:
    if not signature or not signature.startswith("sha256=") or not settings.meta_wa_app_secret:
        return False
    expected = "sha256=" + hmac.new(
        settings.meta_wa_app_secret.encode("utf-8"), raw_body, hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.get("/api/v1/integrations/meta/whatsapp/webhook")
def verify_meta_webhook(request: Request):
    if not settings.whatsapp_webhook_configured:
        raise HTTPException(503, "Meta WhatsApp webhook verification is not configured")
    mode = request.query_params.get("hub.mode", "")
    verify_token = request.query_params.get("hub.verify_token", "")
    challenge = request.query_params.get("hub.challenge", "")
    if mode != "subscribe" or not hmac.compare_digest(verify_token, settings.meta_wa_verify_token):
        raise HTTPException(403, "Webhook verification failed")
    return Response(content=challenge, media_type="text/plain")


@router.post(
    "/api/v1/integrations/meta/whatsapp/webhook",
    max_body_size=MAX_META_WEBHOOK_BYTES,
)
async def receive_meta_webhook(request: Request):
    if not settings.whatsapp_webhook_configured:
        raise HTTPException(503, "Meta WhatsApp webhook processing is not configured")
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_META_WEBHOOK_BYTES:
                raise HTTPException(413, "Webhook payload is too large")
        except ValueError as exc:
            raise HTTPException(400, "Invalid Content-Length") from exc
    raw_body = await request.body()
    if len(raw_body) > MAX_META_WEBHOOK_BYTES:
        raise HTTPException(413, "Webhook payload is too large")
    if not _verify_signature(raw_body, request.headers.get("x-hub-signature-256")):
        raise HTTPException(401, "Invalid Meta webhook signature")
    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(400, "Webhook payload must be valid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("entry"), list):
        raise HTTPException(400, "Unsupported Meta webhook payload")

    try:
        # SQLAlchemy and psycopg are synchronous. Keep DB work off the ASGI
        # event loop so a webhook batch cannot stall unrelated API requests.
        await run_in_threadpool(_process_meta_webhook_payload, payload)
    except HTTPException:
        raise
    except Exception as exc:
        log.error("WhatsApp webhook event processing failed (%s)", type(exc).__name__)
        raise HTTPException(503, "Webhook event could not be processed; Meta may retry") from exc
    return {"received": True}


def _process_meta_webhook_payload(payload: dict) -> None:
    for entry in payload["entry"]:
        changes = entry.get("changes", []) if isinstance(entry, dict) else []
        if not isinstance(changes, list):
            continue
        for change in changes:
            value = change.get("value", {}) if isinstance(change, dict) else {}
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata")
            if not isinstance(metadata, dict) or metadata.get("phone_number_id") != settings.meta_wa_phone_number_id:
                log.warning("Ignored signed WhatsApp event for an unconfigured business phone")
                continue
            statuses = value.get("statuses", [])
            if isinstance(statuses, list):
                for status in statuses:
                    _process_status(status)
            messages = value.get("messages", [])
            if isinstance(messages, list):
                for message in messages:
                    _process_inbound_message(message)


def _reserve_event(db, provider_event_id: str, event_type: str) -> MetaWebhookEvent | None:
    event = db.query(MetaWebhookEvent).filter_by(provider_event_id=provider_event_id).with_for_update().first()
    if event and event.processing_status in {"processed", "ignored"}:
        return None
    if event is None:
        event = MetaWebhookEvent(provider_event_id=provider_event_id, event_type=event_type)
        db.add(event)
        db.flush()
    event.processing_status = "received"
    event.safe_error_code = ""
    return event


def _process_status(status: object) -> None:
    if not isinstance(status, dict):
        return
    provider_id = status.get("id")
    provider_status = status.get("status")
    if not isinstance(provider_id, str) or provider_status not in {"sent", "delivered", "read", "failed"}:
        return
    event_key = f"status:{provider_id}:{provider_status}"
    with WhatsAppWebhookSessionLocal() as db:
        try:
            event = _reserve_event(db, event_key, "delivery_status")
            if event is None:
                db.rollback()
                return
            row = db.query(CommunicationOutbox.id, CommunicationOutbox.status).filter_by(
                provider_message_id=provider_id,
            ).with_for_update().first()
            if row is None:
                event.processing_status = "failed"
                event.safe_error_code = "outbox_message_not_yet_found"
                db.commit()
                raise HTTPException(503, "Delivery status arrived before its send record; retry requested")
            next_status = row.status
            update_values = {"updated_at": datetime.now(timezone.utc)}
            if provider_status == "failed":
                errors = status.get("errors") or []
                error_code = str(errors[0].get("code", "meta_failed")) if errors and isinstance(errors[0], dict) else "meta_failed"
                update_values["last_error_code"] = error_code[:80]
                next_status = "failed"
            elif provider_status == "read":
                next_status = "read"
            elif provider_status == "delivered" and row.status != "read":
                next_status = "delivered"
            elif provider_status == "sent" and row.status not in {"delivered", "read"}:
                next_status = "sent"
            update_values["status"] = next_status
            db.execute(update(CommunicationOutbox).where(
                CommunicationOutbox.id == row.id,
            ).values(**update_values))
            event.processing_status = "processed"
            event.processed_at = datetime.now(timezone.utc)
            db.commit()
        except HTTPException:
            raise
        except IntegrityError:
            db.rollback()
            return
        except Exception:
            db.rollback()
            raise


def _process_inbound_message(message: object) -> None:
    if not isinstance(message, dict) or not isinstance(message.get("id"), str):
        return
    message_id = message["id"]
    with WhatsAppWebhookSessionLocal() as db:
        try:
            event = _reserve_event(db, f"message:{message_id}", "inbound_message")
            if event is None:
                db.rollback()
                return
            message_type = message.get("type")
            raw_phone = message.get("from")
            text_body = ((message.get("text") or {}).get("body") if message_type == "text" else None)
            if not isinstance(raw_phone, str) or not isinstance(text_body, str):
                event.processing_status = "ignored"
                event.safe_error_code = "unsupported_message_type"
                event.processed_at = datetime.now(timezone.utc)
                db.commit()
                return
            try:
                phone = normalize_phone_e164(raw_phone)
            except ValueError:
                event.processing_status = "ignored"
                event.safe_error_code = "invalid_sender_phone"
                event.processed_at = datetime.now(timezone.utc)
                db.commit()
                return

            link_match = re.fullmatch(r"\s*TVLINK\s+([A-F0-9]{12})\s*", text_body, re.IGNORECASE)
            if link_match:
                _complete_pairing(db, event, phone, link_match.group(1).upper())
                db.commit()
                return

            message_match = re.fullmatch(r"\s*TV\s+([A-F0-9]{12})\s+(.{1,4000})\s*", text_body, re.IGNORECASE | re.DOTALL)
            if not message_match:
                event.processing_status = "ignored"
                event.safe_error_code = "message_command_not_recognized"
                event.processed_at = datetime.now(timezone.utc)
                db.commit()
                return

            _add_thread_message(
                db,
                event=event,
                phone=phone,
                conversation_code=message_match.group(1).upper(),
                text_body=message_match.group(2).strip(),
                provider_message_id=message_id,
            )
            db.commit()
        except IntegrityError:
            db.rollback()
            with WhatsAppWebhookSessionLocal() as duplicate_check:
                existing = duplicate_check.query(MetaWebhookEvent).filter_by(provider_event_id=f"message:{message_id}").first()
                if existing and existing.processing_status in {"processed", "ignored"}:
                    return
            raise
        except Exception as exc:
            db.rollback()
            with WhatsAppWebhookSessionLocal() as error_db:
                event = error_db.query(MetaWebhookEvent).filter_by(provider_event_id=f"message:{message_id}").first()
                if event is None:
                    event = MetaWebhookEvent(provider_event_id=f"message:{message_id}", event_type="inbound_message")
                    error_db.add(event)
                event.processing_status = "failed"
                event.safe_error_code = "processing_error"
                error_db.commit()
            log.error("WhatsApp inbound message processing failed (%s)", type(exc).__name__)
            raise


def _complete_pairing(db, event: MetaWebhookEvent, phone: str, code: str) -> None:
    if not settings.whatsapp_pairing_configured:
        event.processing_status = "ignored"
        event.safe_error_code = "pairing_disabled"
        event.processed_at = datetime.now(timezone.utc)
        return
    challenge = db.query(WhatsAppLinkChallenge).filter_by(code_hash=pairing_code_hash(code)).with_for_update().first()
    now = datetime.now(timezone.utc)
    expires_at = challenge.expires_at if challenge else None
    # SQLite strips timezone metadata from DateTime(timezone=True); treat naive
    # values as UTC so local/offline development follows PostgreSQL semantics.
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not challenge or challenge.consumed_at or expires_at <= now:
        event.processing_status = "ignored"
        event.safe_error_code = "pairing_code_invalid_or_expired"
        event.processed_at = now
        return
    existing_phone = db.query(WhatsAppPreference).filter_by(phone_e164=phone).with_for_update().first()
    if existing_phone and existing_phone.user_id != challenge.user_id:
        event.processing_status = "ignored"
        event.safe_error_code = "phone_already_linked"
        event.processed_at = now
        return
    preference = db.get(WhatsAppPreference, challenge.user_id)
    if preference and _active_consent(preference) and preference.phone_e164 != phone:
        event.processing_status = "ignored"
        event.safe_error_code = "revoke_existing_link_first"
        event.processed_at = now
        return
    if preference is None:
        preference = WhatsAppPreference(user_id=challenge.user_id)
        db.add(preference)
    preference.phone_e164 = phone
    preference.verified_at = now
    preference.consent_granted_at = challenge.consent_accepted_at
    preference.consent_revoked_at = None
    preference.consent_version = challenge.consent_version
    preference.consent_source = "signed_in_app_and_user_initiated_whatsapp_message"
    preference.last_inbound_at = now
    preference.updated_at = now
    challenge.consumed_at = now
    db.add(AuditLog(
        user_id=challenge.user_id,
        farm_id=None,
        action="whatsapp.number_linked",
        entity_type="whatsapp_channel_preference",
        entity_id=str(challenge.user_id),
        metadata_json={"consent_version": challenge.consent_version, "verification": "signed_meta_inbound"},
    ))
    if settings.whatsapp_delivery_enabled:
        db.add(CommunicationOutbox(
            recipient_user_id=challenge.user_id,
            body="Terravanta WhatsApp is linked. Open a vet request and use its case code to reply here. You can disconnect WhatsApp in Terravanta Settings.",
            conversation_code=None,
            status="queued",
            idempotency_key=f"wa-pair-confirm:{challenge.id}",
        ))
    event.processing_status = "processed"
    event.processed_at = now


def _add_thread_message(db, *, event: MetaWebhookEvent, phone: str, conversation_code: str, text_body: str, provider_message_id: str) -> None:
    now = datetime.now(timezone.utc)
    preference = db.query(WhatsAppPreference).filter_by(phone_e164=phone).with_for_update().first()
    if not _active_consent(preference):
        event.processing_status = "ignored"
        event.safe_error_code = "sender_not_linked_or_consent_inactive"
        event.processed_at = now
        return
    request = db.query(
        VeterinaryContactRequest.id,
        VeterinaryContactRequest.conversation_code,
        VeterinaryContactRequest.requester_user_id,
        VeterinaryContactRequest.veterinarian_user_id,
        VeterinaryContactRequest.farm_id,
        VeterinaryContactRequest.status,
        VeterinaryContactRequest.urgency,
    ).filter_by(conversation_code=conversation_code).first()
    if not request or request.status not in {"pending", "accepted", "contacted"}:
        event.processing_status = "ignored"
        event.safe_error_code = "request_unavailable"
        event.processed_at = now
        return
    sender_user_id = preference.user_id
    if request.requester_user_id == sender_user_id:
        recipients = [request.veterinarian_user_id] if request.veterinarian_user_id else [
            member.user_id for member in db.query(FarmMember.user_id).filter_by(farm_id=request.farm_id, role="veterinarian").all()
        ]
    elif request.veterinarian_user_id == sender_user_id and request.status in {"accepted", "contacted"}:
        if not db.query(FarmMember.user_id).filter_by(farm_id=request.farm_id, user_id=sender_user_id, role="veterinarian").first():
            event.processing_status = "ignored"
            event.safe_error_code = "sender_not_assigned_to_request"
            event.processed_at = now
            return
        recipients = [request.requester_user_id]
    else:
        event.processing_status = "ignored"
        event.safe_error_code = "sender_not_a_request_participant"
        event.processed_at = now
        return

    domain_event = FarmDomainEvent(
        farm_id=request.farm_id,
        event_type="veterinary.contact_message_received_whatsapp",
        aggregate_type="veterinary_contact_request",
        aggregate_id=request.id,
        actor_user_id=sender_user_id,
        idempotency_key=f"whatsapp-message:{provider_message_id}:event",
        payload={"channel": "whatsapp", "provider": "meta"},
        occurred_at=now,
        created_at=now,
    )
    db.add(domain_event)
    db.flush()
    message = VeterinaryContactMessage(
        request_id=request.id,
        farm_id=request.farm_id,
        event_id=domain_event.id,
        sender_user_id=sender_user_id,
        body=text_body,
        source_channel="whatsapp",
        external_message_id=provider_message_id,
        idempotency_key=f"whatsapp-message:{provider_message_id}",
        created_at=now,
    )
    db.add(message)
    db.flush()
    for recipient_id in set(recipients):
        if recipient_id is None or recipient_id == sender_user_id:
            continue
        db.add(Notification(
            farm_id=request.farm_id,
            event_id=domain_event.id,
            recipient_user_id=recipient_id,
            notification_type="veterinary_contact_message",
            title="New WhatsApp message about a veterinary request",
            body="Open Veterinary in Terravanta to review the linked conversation.",
            severity="high" if request.urgency == "emergency" else "medium",
            action_section="veterinary",
            idempotency_key=f"whatsapp-message:{provider_message_id}:notification:{recipient_id}",
        ))
    db.add(AuditLog(
        user_id=sender_user_id,
        farm_id=request.farm_id,
        action="veterinary.contact_message_received_whatsapp",
        entity_type="veterinary_contact_message",
        entity_id=str(message.id),
        metadata_json={"request_id": str(request.id), "channel": "whatsapp"},
    ))
    preference.last_inbound_at = now
    preference.updated_at = now
    if settings.whatsapp_delivery_enabled:
        for recipient_id in set(recipients):
            if recipient_id is None or recipient_id == sender_user_id:
                continue
            recipient_pref = db.get(WhatsAppPreference, recipient_id)
            if _active_consent(recipient_pref):
                db.add(CommunicationOutbox(
                    recipient_user_id=recipient_id,
                    farm_id=request.farm_id,
                    request_id=request.id,
                    message_id=message.id,
                    body=text_body,
                    conversation_code=request.conversation_code,
                    status="queued",
                    idempotency_key=f"wa-contact-message:{message.id}:{recipient_id}",
                ))
    event.processing_status = "processed"
    event.processed_at = now
