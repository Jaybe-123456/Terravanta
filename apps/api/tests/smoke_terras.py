"""Run focused Terras/API integration checks without installing pytest.

Usage in the API image: python /app/tests/smoke_terras.py
"""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.db import Base, get_db
from app.seed import seed


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def override_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


def login(client, role: str) -> dict[str, str]:
    token = client.post(f"/api/v1/auth/demo-login?role={role}").json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def run():
    Base.metadata.create_all(bind=engine)
    with TestingSession() as db:
        seed(db)
    main.initialize_database = lambda: None
    main.app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(main.app) as client:
            farmer = login(client, "farmer")
            farm_id = "8b1199df-8901-4ba2-9e33-c191f20d43ea"
            before = client.get(f"/api/v1/farms/{farm_id}/production-records", headers=farmer).json()
            draft_response = client.post("/api/v1/terras/route", headers=farmer, json={"message": "Record 24 liters of milk"})
            assert draft_response.status_code == 200, draft_response.text
            draft = draft_response.json()
            assert draft["external_model_used"] is False
            assert draft["draft"] == {"product_type": "milk", "quantity": 24, "unit": "liters"}
            assert draft["requires_confirmation"] is True
            after_route = client.get(f"/api/v1/farms/{farm_id}/production-records", headers=farmer).json()
            assert len(after_route) == len(before), "Routing must not write a production record"

            saved = client.post(f"/api/v1/farms/{farm_id}/production-records", headers=farmer, json={
                **draft["draft"], "recorded_on": date.today().isoformat(),
            })
            assert saved.status_code == 201, saved.text

            cooperative = login(client, "cooperative_admin")
            payout = client.post("/api/v1/terras/route", headers=cooperative, json={"message": "Help me close the payout period"})
            assert payout.status_code == 200, payout.text
            assert payout.json()["destination"] == "settlements"

            blocked_farmer = client.post("/api/v1/terras/route", headers=farmer, json={"message": "Help me reconcile a payout close"})
            assert blocked_farmer.json()["intent"] == "role_limited"
            veterinarian = login(client, "veterinarian")
            blocked_vet = client.post("/api/v1/terras/route", headers=veterinarian, json={"message": "record 10 liters of milk"})
            assert blocked_vet.json()["intent"] == "role_limited"
        print("Terras smoke checks passed: role routes, draft without write, confirmed record creation, and restricted intents.")
    finally:
        main.app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


if __name__ == "__main__":
    run()
