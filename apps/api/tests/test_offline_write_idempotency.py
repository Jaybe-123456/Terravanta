from uuid import uuid4


def test_replaying_offline_farm_create_returns_same_receipt(client, farmer_headers):
    key = str(uuid4())
    headers = {**farmer_headers, "Idempotency-Key": key}
    body = {
        "name": "Offline farm retry",
        "owner_name": "Offline Farmer",
        "county": "Kiambu",
        "subcounty": "Test",
        "size_acres": 2,
        "farming_system": "mixed",
        "production_activities": ["dairy"],
    }
    first = client.post("/api/v1/farms", headers=headers, json=body)
    replay = client.post("/api/v1/farms", headers=headers, json=body)
    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json() == first.json()

    conflict = client.post("/api/v1/farms", headers=headers, json={**body, "name": "Different request"})
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "This Idempotency-Key was already used for a different request"
