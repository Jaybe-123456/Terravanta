"""Database-atomic idempotency for safe replay of queued client writes."""

import hashlib
import json
import re
from typing import Any

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from .models import ClientWriteReceipt, User


def _request_hash(path: str, body: Any) -> str:
    body_json = body.model_dump(mode="json") if hasattr(body, "model_dump") else body
    canonical = json.dumps({"path": path, "body": body_json}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def replay_client_write(db: Session, user: User, key: str | None, path: str, body: Any) -> JSONResponse | None:
    if not key:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", key):
        raise HTTPException(400, "Idempotency-Key must contain 16 to 80 safe characters")
    if db.get_bind().dialect.name == "postgresql":
        lock_key = f"client-write:{user.id}:{key}"
        db.execute(text("SELECT pg_advisory_xact_lock(0, hashtext(:key))"), {"key": lock_key})
    request_hash = _request_hash(path, body)
    existing = db.query(ClientWriteReceipt).filter_by(actor_user_id=user.id, idempotency_key=key).first()
    if existing is None:
        return None
    if existing.request_hash != request_hash:
        raise HTTPException(409, "This Idempotency-Key was already used for a different request")
    return JSONResponse(status_code=201, content=existing.response_json)


def store_client_write_receipt(db: Session, user: User, key: str | None, path: str, body: Any, response: Any) -> None:
    if not key:
        return
    db.add(ClientWriteReceipt(
        actor_user_id=user.id,
        idempotency_key=key,
        request_hash=_request_hash(path, body),
        response_json=jsonable_encoder(response),
    ))
