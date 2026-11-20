import os
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["APP_ENV"] = "test"
os.environ["DEMO_AUTH_SECRET"] = "test-secret-for-local-suite"
os.environ["ENABLE_SYNTHETIC_DATA"] = "true"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_admin_db, get_db
from app.main import app, initialize_database

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(autouse=True)
def reset_database():
    from app.seed import seed
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestingSession() as db:
        seed(db)


@pytest.fixture
def db_session():
    with TestingSession() as db:
        yield db


@pytest.fixture(scope="session")
def client():
    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_admin_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def farmer_headers(client):
    token = client.post("/api/v1/auth/demo-login?role=farmer").json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def vet_headers(client):
    token = client.post("/api/v1/auth/demo-login?role=veterinarian").json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
