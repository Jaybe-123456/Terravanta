def _headers(client, role):
    token = client.post(f"/api/v1/auth/demo-login?role={role}").json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_terras_prepares_milk_draft_without_writing_record(client, farmer_headers):
    before = client.get("/api/v1/farms/8b1199df-8901-4ba2-9e33-c191f20d43ea/production-records", headers=farmer_headers).json()
    response = client.post("/api/v1/terras/route", headers=farmer_headers, json={"message": "Record 24 liters of milk"})
    assert response.status_code == 200
    result = response.json()
    assert result["destination"] == "production"
    assert result["mode"] == "local_rules"
    assert result["external_model_used"] is False
    assert result["requires_confirmation"] is True
    assert result["draft"] == {"product_type": "milk", "quantity": 24, "unit": "liters"}
    after = client.get("/api/v1/farms/8b1199df-8901-4ba2-9e33-c191f20d43ea/production-records", headers=farmer_headers).json()
    assert len(after) == len(before)


def test_terras_cooperative_routes_payout_close_only_for_cooperative(client):
    response = client.post("/api/v1/terras/route", headers=_headers(client, "cooperative_admin"), json={"message": "Help me close the payout period"})
    assert response.status_code == 200
    result = response.json()
    assert result["destination"] == "settlements"
    assert result["api_workflow"] == "POST /api/v1/cooperative/settlement-closes"
    assert result["required_inputs"] == ["Collection CSV", "Processor settlement CSV", "Farmer payout CSV", "Close period"]
    assert result["requires_confirmation"] is True
    assert "does not send payments" in result["reply"]

    blocked = client.post("/api/v1/terras/route", headers=_headers(client, "farmer"), json={"message": "Help me reconcile a payout close"})
    assert blocked.status_code == 200
    assert blocked.json()["destination"] != "settlements"
    assert blocked.json()["intent"] == "role_limited"


def test_terras_requires_auth_and_validates_prompt(client):
    assert client.post("/api/v1/terras/route", json={"message": "go"}).status_code == 401
    assert client.post("/api/v1/terras/route", headers=_headers(client, "farmer"), json={"message": " "}).status_code == 422


def test_terras_veterinarian_never_routes_to_farmer_production(client):
    response = client.post("/api/v1/terras/route", headers=_headers(client, "veterinarian"), json={"message": "record 12 liters of milk"})
    assert response.status_code == 200
    assert response.json()["destination"] == "overview"
    assert response.json()["intent"] == "role_limited"
    assert response.json()["draft"] is None
