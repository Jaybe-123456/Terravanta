"""Meta WhatsApp Cloud API adapter and pairing-code primitives.

This module never logs credentials, phone numbers, message bodies, or pairing codes.
"""
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from .config import settings


PAIRING_TERMS_VERSION = "whatsapp-notifications-v1"
MAX_META_WEBHOOK_BYTES = 1_000_000


def new_pairing_code() -> str:
    return secrets.token_hex(6).upper()


def pairing_code_hash(code: str) -> str:
    if not settings.whatsapp_pairing_secret:
        raise RuntimeError("WhatsApp pairing is not configured")
    return hmac.new(
        settings.whatsapp_pairing_secret.encode("utf-8"),
        code.upper().encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def normalize_phone_e164(value: str) -> str:
    """Normalize Meta's digits-only wa_id to E.164-shaped storage."""
    digits = re.sub(r"\D", "", value)
    if not 8 <= len(digits) <= 15 or digits.startswith("0"):
        raise ValueError("Invalid WhatsApp phone identifier")
    return f"+{digits}"


def make_link_url(code: str) -> str:
    business_number = re.sub(r"\D", "", settings.meta_wa_business_number)
    if not business_number:
        raise RuntimeError("The Terravanta WhatsApp business number is not configured")
    return f"https://wa.me/{business_number}?text={quote(f'TVLINK {code}')}"


@dataclass(frozen=True)
class WhatsAppSendResult:
    provider_message_id: str


class WhatsAppSendError(Exception):
    def __init__(self, safe_code: str, *, retryable: bool, blocked: bool = False):
        super().__init__(safe_code)
        self.safe_code = safe_code
        self.retryable = retryable
        self.blocked = blocked


def send_whatsapp_message(
    *,
    to_phone: str,
    body: str,
    conversation_code: str | None,
    in_service_window: bool,
) -> WhatsAppSendResult:
    """Send a free-form reply in an open user-initiated window, otherwise a template notice."""
    if not settings.whatsapp_delivery_configured:
        raise WhatsAppSendError("provider_not_configured", retryable=False, blocked=True)
    if not re.fullmatch(r"v\d+\.\d+", settings.meta_wa_graph_api_version):
        raise WhatsAppSendError("graph_api_version_invalid", retryable=False, blocked=True)

    if in_service_window:
        text_body = f"Terravanta · {conversation_code}\n{body}" if conversation_code else body
        if conversation_code:
            text_body += f"\n\nTo reply, send: TV {conversation_code} <your message>"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone.removeprefix("+"),
            "type": "text",
            "text": {"preview_url": False, "body": text_body[:4000]},
        }
    else:
        if not settings.meta_wa_notification_template:
            raise WhatsAppSendError("utility_template_not_configured", retryable=False, blocked=True)
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone.removeprefix("+"),
            "type": "template",
            "template": {
                "name": settings.meta_wa_notification_template,
                "language": {"code": settings.meta_wa_template_language},
                "components": [{
                    "type": "body",
                    "parameters": [{"type": "text", "text": conversation_code or "Terravanta"}],
                }],
            },
        }

    url = f"https://graph.facebook.com/{settings.meta_wa_graph_api_version}/{settings.meta_wa_phone_number_id}/messages"
    try:
        with httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.meta_wa_access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise WhatsAppSendError("provider_timeout", retryable=True) from exc
    except httpx.RequestError as exc:
        raise WhatsAppSendError("provider_network_error", retryable=True) from exc

    try:
        response_body = response.json()
    except ValueError:
        response_body = {}
    if response.status_code >= 400:
        meta_code = (response_body.get("error") or {}).get("code")
        safe_code = f"meta_{meta_code}" if isinstance(meta_code, int) else f"http_{response.status_code}"
        retryable = response.status_code == 429 or response.status_code >= 500
        raise WhatsAppSendError(safe_code, retryable=retryable)
    message_id = ((response_body.get("messages") or [{}])[0]).get("id")
    if not isinstance(message_id, str) or not message_id:
        raise WhatsAppSendError("provider_response_missing_message_id", retryable=True)
    return WhatsAppSendResult(provider_message_id=message_id)
