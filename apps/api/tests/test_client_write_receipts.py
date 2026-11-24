import json
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.idempotency import replay_client_write, store_client_write_receipt
from app.models import User


def test_client_write_receipt_replays_same_response_and_rejects_key_reuse(db_session):
    user = User(id=uuid4(), display_name="Idempotency Test", email=f"{uuid4()}@idempotency.test")
    db_session.add(user)
    db_session.commit()
    key = str(uuid4())
    body = {"name": "test", "count": 1}
    response = {"id": str(uuid4()), "status": "created"}

    assert replay_client_write(db_session, user, key, "/api/v1/farms", body) is None
    store_client_write_receipt(db_session, user, key, "/api/v1/farms", body, response)
    db_session.commit()

    replay = replay_client_write(db_session, user, key, "/api/v1/farms", body)
    assert replay is not None
    assert replay.status_code == 201
    assert json.loads(replay.body) == response
    with pytest.raises(HTTPException) as conflict:
        replay_client_write(db_session, user, key, "/api/v1/farms", {"name": "different"})
    assert conflict.value.status_code == 409
