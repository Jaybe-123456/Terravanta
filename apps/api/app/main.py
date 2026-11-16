import csv
import json
import hashlib
import hmac
import io
import logging
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials
import httpx
from pydantic import ValidationError
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pypdf import PdfReader

from .ai import nvidia, parse_structured, safe_case_response
from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .models import (
    AIRequest, AIResponse, AccessCode, Animal, AnimalHealthEvent, AuditLog, Buyer, CompostApplication,
    CompostBatch, Consent, Delivery, DocumentExtraction, Farm, FarmMember, FeedAllocation,
    FeedBatch, KnowledgeSource, ManureRecord, Organization, OrganizationMember, Plot,
    ProductLot, ProductionRecord, ReconciliationItem, ReconciliationRun, SettlementClose, SettlementCloseItem, User, UserRole,
)
from .schemas import (
    AccessCodeLogin, AccessCodeRequest, AnimalCreate, AssistantRequest, CompostApplicationCreate, CompostCreate, ConsentCreate,
    DeliveryCreate, FarmCreate, FeedAllocationCreate, FeedBatchCreate, HealthEventCreate,
    ExtractedDocumentDraft, ManureCreate, PlotCreate, ProductionCreate, ReconciliationReviewCreate,
    SettlementApproveCreate, SettlementReviewCreate,
)
from .reconciliation import MAX_RECONCILIATION_ROWS, classify_collection_entry, parse_collection_csv
from .settlement import parse_settlement_sources
from .security import bearer, current_identity, current_user, issue_access_code_token, issue_demo_token, require_role, user_role, user_roles, verified_supabase_user
from .seed import FARMER_ID, FARM_ID, seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("terravanta")


def email_code_hash(email: str, code: str) -> str:
    message = f"email-otp\0{email}\0{code}".encode("utf-8")
    return hmac.new(settings.demo_auth_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def send_access_code_email(email: str, name: str, code: str):
    if not settings.resend_api_key or not settings.access_code_from_email:
        raise HTTPException(503, "Email code delivery is not configured yet. Please try again later.")
    text_body = (
        f"Hello {name},\n\nYour Terravanta sign-in code is {code}. "
        "It expires in 10 minutes and can be used once. If you did not request it, ignore this email."
    )
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}", "Content-Type": "application/json"},
            json={
                "from": settings.access_code_from_email,
                "to": [email],
                "subject": "Your Terravanta sign-in code",
                "text": text_body,
            },
            timeout=10,
        )
    except httpx.HTTPError as exc:
        log.warning("Access code email delivery failed (%s)", type(exc).__name__)
        raise HTTPException(503, "We could not send your code. Please try again later.") from exc
    if not response.is_success:
        log.warning("Access code email provider returned HTTP %s", response.status_code)
        raise HTTPException(503, "We could not send your code. Please try again later.")


def initialize_database():
    if settings.app_env == "production":
        # Production schema changes are applied by Alembic before the API starts.
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS postgis")
            connection.exec_driver_sql("ALTER TABLE farms ADD COLUMN IF NOT EXISTS location geometry(Point, 4326)")
            connection.exec_driver_sql("UPDATE farms SET location = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) WHERE location IS NULL AND latitude IS NOT NULL AND longitude IS NOT NULL")
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_farms_location_gist ON farms USING GIST (location)")
    if settings.enable_synthetic_data:
        with SessionLocal() as db:
            seed(db)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="Terravanta API", version="1.0.0", description="Veterinary-first farm intelligence API. Optional demonstration records are synthetic.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def dump(row, exclude: set[str] | None = None) -> dict:
    exclude = exclude or set()
    result = {}
    for key, value in row.__dict__.items():
        if key.startswith("_") or key in exclude:
            continue
        if isinstance(value, UUID):
            value = str(value)
        elif isinstance(value, (date, datetime)):
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = float(value)
        result[key] = value
    return result


def farm_access(db: Session, user: User, farm_id: str | UUID) -> Farm:
    try:
        farm_uuid = UUID(str(farm_id))
    except ValueError as exc:
        raise HTTPException(422, "Invalid farm id") from exc
    membership = db.query(FarmMember).filter_by(farm_id=farm_uuid, user_id=user.id).first()
    farm = db.get(Farm, farm_uuid)
    if not membership or not farm:
        raise HTTPException(404, "Farm not found or access not granted")
    return farm


def primary_farm(db: Session, user: User) -> Farm:
    farm = db.query(Farm).join(FarmMember, FarmMember.farm_id == Farm.id).filter(FarmMember.user_id == user.id).order_by(Farm.created_at.desc()).first()
    if not farm:
        raise HTTPException(404, "No farm is available for this account")
    return farm


def audit(db: Session, user: User, action: str, entity_type: str, entity_id: str, farm_id: UUID | None = None, metadata: dict | None = None):
    db.add(AuditLog(user_id=user.id, farm_id=farm_id, action=action, entity_type=entity_type, entity_id=str(entity_id), metadata_json=metadata or {}))


def enforce_ai_rate_limit(db: Session, user: User):
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=1)
    recent = db.query(AIRequest).filter(AIRequest.user_id == user.id, AIRequest.created_at >= cutoff).count()
    if recent >= 8:
        raise HTTPException(429, "AI request limit reached. Wait a minute before trying again.")


def farm_animals(db: Session, farm_id: UUID) -> list[dict]:
    return [dump(row) for row in db.query(Animal).filter_by(farm_id=farm_id).order_by(Animal.tag).all()]


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "service": "terravanta-api"}


@app.post("/api/v1/auth/demo-login")
def demo_login(role: str, db: Session = Depends(get_db)):
    if settings.app_env == "production" or not settings.enable_synthetic_data:
        raise HTTPException(404, "Demo authentication is disabled")
    role = role.lower()
    if role not in {"farmer", "veterinarian", "cooperative_admin"}:
        raise HTTPException(422, "Choose farmer, veterinarian, or cooperative_admin")
    email = {"farmer": "farmer@terravanta.demo", "veterinarian": "vet@terravanta.demo", "cooperative_admin": "cooperative@terravanta.demo"}[role]
    user = db.query(User).filter_by(email=email).first()
    if not user:
        raise HTTPException(503, "Demo data is not initialized")
    return {"access_token": issue_demo_token(user, role), "token_type": "bearer", "user": {"id": str(user.id), "name": user.display_name, "role": role}, "synthetic": True}


@app.post("/api/v1/auth/request-access-code", status_code=202)
def request_access_code(payload: AccessCodeRequest, db: Session = Depends(get_db)):
    """Email a short-lived one-time code; never return the code in the API response."""
    if not settings.temp_access_auth_enabled:
        raise HTTPException(404, "Temporary access-code sign-in is disabled")
    if not settings.resend_api_key or not settings.access_code_from_email:
        raise HTTPException(503, "Email code delivery is not configured yet. Please try again later.")
    now = datetime.now(timezone.utc)
    recent_count = db.query(AccessCode).filter(
        AccessCode.email == payload.email,
        AccessCode.code_type == "email_otp",
        AccessCode.created_at >= now - timedelta(minutes=15),
    ).count()
    if recent_count >= 3:
        raise HTTPException(429, "Too many codes requested for this email. Try again in 15 minutes.")
    service_count = db.query(AccessCode).filter(
        AccessCode.code_type == "email_otp",
        AccessCode.created_at >= now - timedelta(hours=1),
    ).count()
    if service_count >= 100:
        raise HTTPException(429, "Sign-in code requests are temporarily busy. Try again later.")

    user = db.query(User).filter(func.lower(User.email) == payload.email).first()
    eligible = True
    if user:
        roles = user_roles(db, user)
        eligible = (not roles or roles == {"farmer"}) and user.display_name.casefold() == payload.name.casefold()
    if eligible:
        code = f"{secrets.randbelow(100_000_000):08d}"
        for previous in db.query(AccessCode).filter_by(email=payload.email, code_type="email_otp", revoked_at=None).all():
            previous.revoked_at = now
        record = AccessCode(
            code_hash=email_code_hash(payload.email, code), email=payload.email,
            display_name=payload.name, code_type="email_otp",
            expires_at=now + timedelta(minutes=10), attempt_count=0,
        )
        db.add(record)
        db.commit()
        try:
            send_access_code_email(payload.email, payload.name, code)
        except HTTPException:
            record.revoked_at = datetime.now(timezone.utc)
            db.commit()
            raise
    return {"message": "If these details can be registered, a verification code has been sent to that email. It expires in 10 minutes."}


@app.post("/api/v1/auth/access-code-login")
def access_code_login(payload: AccessCodeLogin, db: Session = Depends(get_db)):
    if not settings.temp_access_auth_enabled:
        raise HTTPException(404, "Temporary access-code sign-in is disabled")
    now = datetime.now(timezone.utc)
    record = None
    if len(payload.code) == 8 and payload.code.isdigit():
        record = db.query(AccessCode).filter_by(email=payload.email, code_type="email_otp", revoked_at=None).order_by(AccessCode.created_at.desc()).first()
        expires_at = record.expires_at if record else None
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        valid_code = bool(record and hmac.compare_digest(record.code_hash, email_code_hash(payload.email, payload.code)))
        if not record or not expires_at or expires_at <= now or record.display_name.casefold() != payload.name.casefold() or not valid_code:
            if record:
                record.attempt_count += 1
                if record.attempt_count >= 5 or expires_at <= now:
                    record.revoked_at = now
                db.commit()
            raise HTTPException(401, "Name, email, or verification code is invalid or expired")
        record.revoked_at = now  # Email verification codes are single-use.
    else:
        code_hash = hashlib.sha256(payload.code.encode("utf-8")).hexdigest()
        record = db.query(AccessCode).filter_by(code_hash=code_hash, email=payload.email, code_type="invite").first()
        expires_at = record.expires_at if record else None
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if not record or record.revoked_at or expires_at <= now or record.display_name.casefold() != payload.name.casefold():
            raise HTTPException(401, "Name, email, or verification code is invalid or expired")

    user = db.query(User).filter(func.lower(User.email) == payload.email).first()
    created = False
    if user is None:
        user = User(display_name=record.display_name, email=record.email)
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role="farmer"))
        audit(db, user, "account.farmer_access_code_created", "user", str(user.id))
        created = True
    else:
        roles = user_roles(db, user)
        if roles and roles != {"farmer"}:
            raise HTTPException(403, "This access code is only valid for farmer accounts")
        if not roles:
            db.add(UserRole(user_id=user.id, role="farmer"))
        if user.display_name.casefold() != record.display_name.casefold():
            raise HTTPException(409, "The invited name does not match this existing account; contact Terravanta support")
    audit(db, user, "auth.access_code_login", "user", str(user.id))
    db.commit()
    return {"access_token": issue_access_code_token(user), "token_type": "bearer", "expires_in": 43200,
            "user": {"id": str(user.id), "name": user.display_name, "email": user.email, "role": "farmer", "created": created}}


@app.post("/api/v1/auth/onboard", status_code=200)
def onboard_account(
    identity: dict = Depends(current_identity),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
):
    if identity.get("demo") or not settings.supabase_url:
        raise HTTPException(403, "Real farmer onboarding requires a verified Supabase identity")
    try:
        user_id = UUID(identity["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(401, "Supabase account identity is invalid") from exc
    if credentials is None:
        raise HTTPException(401, "Sign in to continue")
    provider_user = verified_supabase_user(credentials.credentials, user_id)
    email = str(provider_user.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(422, "A verified email address is required to create a Terravanta account")

    user = db.get(User, user_id)
    created = False
    if user is None:
        existing_email = db.query(User).filter(func.lower(User.email) == email).first()
        if existing_email:
            raise HTTPException(409, "This email is linked to another Terravanta identity. Contact support.")
        metadata = provider_user.get("user_metadata") or {}
        display_name = str(metadata.get("full_name") or metadata.get("name") or email.split("@", 1)[0]).strip()[:120]
        if len(display_name) < 2:
            raise HTTPException(422, "Enter your name when creating the account")
        user = User(id=user_id, display_name=display_name, email=email)
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role="farmer"))
        audit(db, user, "account.farmer_onboarded", "user", str(user.id))
        db.commit()
        created = True
    roles = user_roles(db, user)
    if not roles:
        raise HTTPException(403, "This account needs a veterinarian or cooperative invitation before access")
    return {"id": str(user.id), "name": user.display_name, "email": user.email, "role": user_role(db, user), "roles": sorted(roles), "synthetic": False, "created": created}


@app.get("/api/v1/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"id": str(user.id), "name": user.display_name, "email": user.email, "role": user_role(db, user), "roles": sorted(user_roles(db, user)), "synthetic": user.email.endswith(".demo")}


@app.get("/api/v1/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = primary_farm(db, user)
    animals = db.query(Animal).filter_by(farm_id=farm.id).count()
    open_cases = db.query(AnimalHealthEvent).filter_by(farm_id=farm.id, status="open").count()
    due_events = db.query(AnimalHealthEvent).filter(AnimalHealthEvent.farm_id == farm.id, AnimalHealthEvent.follow_up_on <= date.today() + timedelta(days=7), AnimalHealthEvent.status == "open").count()
    feed_kg = db.query(func.coalesce(func.sum(FeedBatch.quantity_kg), 0)).filter_by(farm_id=farm.id).scalar()
    milk = db.query(ProductionRecord).filter(ProductionRecord.farm_id == farm.id, ProductionRecord.product_type == "milk", ProductionRecord.recorded_on >= date.today() - timedelta(days=6)).order_by(ProductionRecord.recorded_on.desc()).all()
    weekly = {}
    for row in reversed(milk):
        weekly[row.recorded_on.isoformat()] = round(row.quantity, 1)
    deliveries = db.query(Delivery).filter_by(farm_id=farm.id).count()
    recent_events = db.query(AnimalHealthEvent).filter_by(farm_id=farm.id).order_by(AnimalHealthEvent.created_at.desc()).limit(4).all()
    recent_production = db.query(ProductionRecord).filter_by(farm_id=farm.id).order_by(ProductionRecord.recorded_on.desc()).limit(2).all()
    activities = [{"kind": "Veterinary", "date": item.occurred_on.isoformat(), "text": item.summary, "verified": item.verified} for item in recent_events]
    activities += [{"kind": "Production", "date": item.recorded_on.isoformat(), "text": f"{item.quantity:g} {item.unit} {item.product_type} recorded", "verified": False} for item in recent_production]
    return {
        "farm": dump(farm),
        "stats": {"farms": db.query(FarmMember.farm_id).filter_by(user_id=user.id).distinct().count(), "animals": animals, "active_cases": open_cases, "follow_ups_due": due_events, "milk_liters_7d": round(sum(weekly.values()), 1), "feed_inventory_kg": round(float(feed_kg), 1), "crop_plots": db.query(Plot).filter_by(farm_id=farm.id).count(), "deliveries": deliveries},
        "milk_trend": [{"date": day, "liters": value} for day, value in weekly.items()],
        "activities": activities[:6],
        "synthetic": farm.is_synthetic,
    }


@app.get("/api/v1/farms")
def list_farms(user: User = Depends(current_user), db: Session = Depends(get_db)):
    farms = db.query(Farm).join(FarmMember, FarmMember.farm_id == Farm.id).filter(FarmMember.user_id == user.id).order_by(Farm.created_at.desc()).all()
    return [dump(farm) for farm in farms]


@app.get("/api/v1/cooperatives")
def list_cooperatives(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, "farmer", "platform_admin")
    return [{"id": str(row.id), "name": row.name} for row in db.query(Organization).filter_by(kind="cooperative").order_by(Organization.name).all()]


@app.post("/api/v1/farms", status_code=201)
def create_farm(body: FarmCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, "farmer", "platform_admin")
    code = f"TV-{re.sub('[^A-Z]', '', body.county.upper())[:3]}-{secrets.token_hex(2).upper()}"
    farm = Farm(code=code, name=body.name, owner_name=body.owner_name, county=body.county, subcounty=body.subcounty, latitude=body.latitude, longitude=body.longitude, size_acres=body.size_acres, farming_system=body.farming_system, production_activities=body.production_activities, verification_status="farmer_submitted", is_synthetic=False, created_by=user.id)
    db.add(farm)
    db.flush()
    if engine.dialect.name == "postgresql" and farm.latitude is not None and farm.longitude is not None:
        db.execute(text("UPDATE farms SET location = ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326) WHERE id = :farm_id"), {"longitude": farm.longitude, "latitude": farm.latitude, "farm_id": farm.id})
    db.add(FarmMember(farm_id=farm.id, user_id=user.id, role="owner"))
    audit(db, user, "farm.created", "farm", str(farm.id), farm.id)
    db.commit()
    return dump(farm)


@app.get("/api/v1/farms/{farm_id}")
def get_farm(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return dump(farm_access(db, user, farm_id))


@app.get("/api/v1/farms/{farm_id}/passport")
def passport(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    sharing = []
    for consent in db.query(Consent).filter_by(farm_id=farm.id).all():
        row = dump(consent)
        organization = db.get(Organization, consent.grantee_org_id) if consent.grantee_org_id else None
        row["grantee_name"] = organization.name if organization else consent.grantee_email
        sharing.append(row)
    return {"farm": dump(farm), "provenance": {"farm": "farmer-submitted" if farm.verification_status == "farmer_submitted" else "verified", "synthetic": farm.is_synthetic}, "counts": {"animals": db.query(Animal).filter_by(farm_id=farm.id).count(), "plots": db.query(Plot).filter_by(farm_id=farm.id).count(), "health_events": db.query(AnimalHealthEvent).filter_by(farm_id=farm.id).count(), "health_events_verified": db.query(AnimalHealthEvent).filter_by(farm_id=farm.id, verified=True).count(), "production_records": db.query(ProductionRecord).filter_by(farm_id=farm.id).count(), "deliveries": db.query(Delivery).filter_by(farm_id=farm.id).count()}, "sharing": sharing}


@app.get("/api/v1/farms/{farm_id}/plots")
def list_plots(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    return [dump(row) for row in db.query(Plot).filter_by(farm_id=farm.id).order_by(Plot.name).all()]


@app.post("/api/v1/farms/{farm_id}/plots", status_code=201)
def create_plot(farm_id: UUID, body: PlotCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    occupied = db.query(func.coalesce(func.sum(Plot.area_acres), 0)).filter_by(farm_id=farm.id).scalar()
    if farm.size_acres and occupied + body.area_acres > farm.size_acres:
        raise HTTPException(422, "Plot area exceeds the recorded farm area")
    row = Plot(farm_id=farm.id, **body.model_dump())
    db.add(row)
    db.flush()
    audit(db, user, "plot.created", "plot", str(row.id), farm.id)
    db.commit()
    return dump(row)


@app.get("/api/v1/farms/{farm_id}/animals")
def list_animals(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    return farm_animals(db, farm.id)


@app.post("/api/v1/farms/{farm_id}/animals", status_code=201)
def create_animal(farm_id: UUID, body: AnimalCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    row = Animal(farm_id=farm.id, **body.model_dump())
    db.add(row)
    db.flush()
    audit(db, user, "animal.created", "animal", str(row.id), farm.id)
    db.commit()
    return dump(row)


@app.get("/api/v1/animals/{animal_id}")
def get_animal(animal_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(Animal, animal_id)
    if not row:
        raise HTTPException(404, "Animal not found")
    farm_access(db, user, row.farm_id)
    return {**dump(row), "health_history": [dump(event) for event in db.query(AnimalHealthEvent).filter_by(animal_id=row.id).order_by(AnimalHealthEvent.occurred_on.desc()).all()]}


@app.get("/api/v1/animals/{animal_id}/health-events")
def health_history(animal_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    animal = db.get(Animal, animal_id)
    if not animal:
        raise HTTPException(404, "Animal not found")
    farm_access(db, user, animal.farm_id)
    return [dump(row) for row in db.query(AnimalHealthEvent).filter_by(animal_id=animal.id).order_by(AnimalHealthEvent.occurred_on.desc()).all()]


@app.post("/api/v1/animals/{animal_id}/health-events", status_code=201)
def create_health_event(animal_id: UUID, body: HealthEventCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    animal = db.get(Animal, animal_id)
    if not animal:
        raise HTTPException(404, "Animal not found")
    farm = farm_access(db, user, animal.farm_id)
    verified = False
    if body.verify_record:
        require_role(db, user, "veterinarian", "platform_admin")
        verified = True
    row = AnimalHealthEvent(farm_id=farm.id, animal_id=animal.id, created_by=user.id, verified_by=user.id if verified else None, event_type=body.event_type, occurred_on=body.occurred_on, summary=body.summary, observations=body.observations, follow_up_on=body.follow_up_on, status="open", verified=verified)
    db.add(row)
    db.flush()
    audit(db, user, "health_event.created", "animal_health_event", str(row.id), farm.id, {"verified": verified})
    db.commit()
    return dump(row)


@app.get("/api/v1/veterinary/queue")
def veterinary_queue(user: User = Depends(current_user), db: Session = Depends(get_db)):
    role = require_role(db, user, "veterinarian", "platform_admin")
    query = db.query(AnimalHealthEvent).filter(AnimalHealthEvent.status == "open")
    if role != "platform_admin":
        assigned_farms = select(FarmMember.farm_id).where(FarmMember.user_id == user.id, FarmMember.role == "veterinarian")
        query = query.filter(AnimalHealthEvent.farm_id.in_(assigned_farms))
    events = query.order_by(AnimalHealthEvent.follow_up_on.asc().nullslast(), AnimalHealthEvent.occurred_on.desc()).limit(100).all()
    result = []
    for event in events:
        animal, farm = db.get(Animal, event.animal_id), db.get(Farm, event.farm_id)
        result.append({**dump(event), "animal_tag": animal.tag, "animal_name": animal.name, "farm_name": farm.name, "farm_code": farm.code})
    return result


@app.post("/api/v1/health-events/{event_id}/verify")
def verify_health_event(event_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    event = db.get(AnimalHealthEvent, event_id)
    if not event:
        raise HTTPException(404, "Health event not found")
    farm_access(db, user, event.farm_id)
    require_role(db, user, "veterinarian", "platform_admin")
    if not event.verified:
        event.verified = True
        event.verified_by = user.id
        audit(db, user, "health_event.verified", "animal_health_event", event.id, event.farm_id)
        db.commit()
    return dump(event)


@app.get("/api/v1/farms/{farm_id}/feed-batches")
def list_feed(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    return [dump(row) for row in db.query(FeedBatch).filter_by(farm_id=farm.id).order_by(FeedBatch.batch_date.desc()).all()]


@app.post("/api/v1/farms/{farm_id}/feed-batches", status_code=201)
def create_feed(farm_id: UUID, body: FeedBatchCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    data = body.model_dump()
    if data.get("plot_id"):
        plot = db.get(Plot, data["plot_id"])
        if not plot or plot.farm_id != farm.id:
            raise HTTPException(422, "Feed source plot must belong to this farm")
    row = FeedBatch(farm_id=farm.id, **data)
    db.add(row)
    db.flush()
    audit(db, user, "feed_batch.created", "feed_batch", str(row.id), farm.id)
    db.commit()
    return dump(row)


@app.post("/api/v1/farms/{farm_id}/feed-allocations", status_code=201)
def allocate_feed(farm_id: UUID, body: FeedAllocationCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    batch = db.query(FeedBatch).filter_by(id=body.feed_batch_id, farm_id=farm.id).with_for_update().first()
    animal = db.get(Animal, body.animal_id)
    if not batch or not animal or batch.farm_id != farm.id or animal.farm_id != farm.id:
        raise HTTPException(422, "Select a feed batch and animal from this farm")
    if batch.quantity_kg < body.allocated_kg:
        raise HTTPException(422, "Allocation exceeds the remaining batch quantity")
    batch.quantity_kg -= body.allocated_kg
    row = FeedAllocation(farm_id=farm.id, feed_batch_id=body.feed_batch_id, animal_id=body.animal_id, allocated_kg=body.allocated_kg, allocated_on=body.allocated_on)
    db.add(row)
    audit(db, user, "feed_allocation.created", "feed_allocation", str(row.id), farm.id)
    db.commit()
    return dump(row)


@app.post("/api/v1/farms/{farm_id}/manure-records", status_code=201)
def create_manure(farm_id: UUID, body: ManureCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    row = ManureRecord(farm_id=farm.id, **body.model_dump())
    db.add(row)
    db.flush()
    audit(db, user, "manure.created", "manure_record", str(row.id), farm.id)
    db.commit()
    return dump(row)


@app.post("/api/v1/farms/{farm_id}/compost-batches", status_code=201)
def create_compost(farm_id: UUID, body: CompostCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    data = body.model_dump()
    if data.get("manure_record_id"):
        manure = db.get(ManureRecord, data["manure_record_id"])
        if not manure or manure.farm_id != farm.id:
            raise HTTPException(422, "Manure record must belong to this farm")
    row = CompostBatch(farm_id=farm.id, **data)
    db.add(row)
    db.flush()
    audit(db, user, "compost.created", "compost_batch", str(row.id), farm.id)
    db.commit()
    return dump(row)


@app.post("/api/v1/farms/{farm_id}/compost-applications", status_code=201)
def apply_compost(farm_id: UUID, body: CompostApplicationCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    compost = db.query(CompostBatch).filter_by(id=body.compost_batch_id, farm_id=farm.id).with_for_update().first()
    plot = db.get(Plot, body.plot_id)
    if not compost or not plot or compost.farm_id != farm.id or plot.farm_id != farm.id:
        raise HTTPException(422, "Compost and plot must belong to this farm")
    if compost.quantity_kg < body.quantity_kg:
        raise HTTPException(422, "Application exceeds the remaining compost quantity")
    compost.quantity_kg -= body.quantity_kg
    if compost.quantity_kg == 0:
        compost.status = "used"
    row = CompostApplication(farm_id=farm.id, compost_batch_id=body.compost_batch_id, plot_id=body.plot_id, applied_on=body.applied_on, quantity_kg=body.quantity_kg)
    db.add(row)
    audit(db, user, "compost_application.created", "compost_application", str(row.id), farm.id)
    db.commit()
    return dump(row)


@app.get("/api/v1/farms/{farm_id}/resource-cycle")
def resource_cycle(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    return {"plots": [dump(row) for row in db.query(Plot).filter_by(farm_id=farm.id).all()], "feed_batches": [dump(row) for row in db.query(FeedBatch).filter_by(farm_id=farm.id).all()], "allocations": [dump(row) for row in db.query(FeedAllocation).filter_by(farm_id=farm.id).all()], "manure": [dump(row) for row in db.query(ManureRecord).filter_by(farm_id=farm.id).all()], "compost": [dump(row) for row in db.query(CompostBatch).filter_by(farm_id=farm.id).all()], "applications": [dump(row) for row in db.query(CompostApplication).filter_by(farm_id=farm.id).all()], "animals": farm_animals(db, farm.id), "note": "Recorded links only. No nutrient balances or agronomic recommendations are calculated."}


@app.get("/api/v1/farms/{farm_id}/production-records")
def list_production(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    return [dump(row) for row in db.query(ProductionRecord).filter_by(farm_id=farm.id).order_by(ProductionRecord.recorded_on.desc()).all()]


@app.post("/api/v1/farms/{farm_id}/production-records", status_code=201)
def create_production(farm_id: UUID, body: ProductionCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    data = body.model_dump()
    for key, cls in (("animal_id", Animal), ("plot_id", Plot)):
        if data.get(key):
            linked = db.get(cls, data[key])
            if not linked or linked.farm_id != farm.id:
                raise HTTPException(422, f"{key} must belong to this farm")
    row = ProductionRecord(farm_id=farm.id, **data)
    db.add(row)
    db.flush()
    audit(db, user, "production.created", "production_record", str(row.id), farm.id)
    db.commit()
    return dump(row)


@app.post("/api/v1/farms/{farm_id}/deliveries", status_code=201)
def create_delivery(farm_id: UUID, body: DeliveryCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    record = db.query(ProductionRecord).filter_by(id=body.production_record_id, farm_id=farm.id).with_for_update().first()
    if not record or record.farm_id != farm.id:
        raise HTTPException(422, "Select a production record from this farm")
    if body.unit != record.unit:
        raise HTTPException(422, "Delivery unit must match its source production record")
    already_allocated = db.query(func.coalesce(func.sum(Delivery.quantity), 0)).join(ProductLot, ProductLot.id == Delivery.product_lot_id).filter(ProductLot.production_record_id == record.id, Delivery.status.in_(["pending", "accepted"])).scalar()
    if float(already_allocated) + body.quantity > record.quantity:
        raise HTTPException(422, "Delivery quantity exceeds the remaining source production quantity")
    buyer = db.query(Buyer).filter(func.lower(Buyer.name) == body.buyer_name.lower()).first()
    if not buyer:
        buyer = Buyer(name=body.buyer_name)
        db.add(buyer)
        db.flush()
    lot = ProductLot(farm_id=farm.id, production_record_id=record.id, lot_code=f"{farm.code}-{secrets.token_hex(3).upper()}", product_type=record.product_type, quantity=body.quantity, unit=body.unit)
    db.add(lot)
    db.flush()
    delivery = Delivery(farm_id=farm.id, product_lot_id=lot.id, buyer_id=buyer.id, delivery_date=body.delivery_date, quantity=body.quantity, unit=body.unit, status=body.status, reference=body.reference)
    db.add(delivery)
    db.flush()
    audit(db, user, "delivery.created", "delivery", str(delivery.id), farm.id, {"lot_code": lot.lot_code})
    db.commit()
    return {"delivery": dump(delivery), "product_lot": dump(lot), "source_production": dump(record)}


@app.get("/api/v1/farms/{farm_id}/deliveries")
def list_deliveries(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    return [{**dump(row), "buyer": db.get(Buyer, row.buyer_id).name, "lot": dump(db.get(ProductLot, row.product_lot_id))} for row in db.query(Delivery).filter_by(farm_id=farm.id).order_by(Delivery.delivery_date.desc()).all()]


@app.post("/api/v1/farms/{farm_id}/consents", status_code=201)
def create_consent(farm_id: UUID, body: ConsentCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    if body.scope not in {"delivery_summary", "verified_production"}:
        raise HTTPException(422, "Only delivery summaries and verified production summaries can be shared in the MVP")
    grantee_email = body.grantee_email.lower().strip() if body.grantee_email else None
    if body.grantee_org_id:
        organization = db.get(Organization, body.grantee_org_id)
        if not organization or organization.kind != "cooperative":
            raise HTTPException(422, "Choose a registered cooperative organization")
        existing_query = db.query(Consent).filter_by(farm_id=farm.id, grantee_org_id=body.grantee_org_id, scope=body.scope, status="active")
    else:
        existing_query = db.query(Consent).filter_by(farm_id=farm.id, grantee_email=grantee_email, scope=body.scope, status="active")
    if existing_query.filter(or_(Consent.expires_at.is_(None), Consent.expires_at > datetime.now(timezone.utc))).first():
        raise HTTPException(409, "An active grant already exists for this cooperative and scope")
    row = Consent(farm_id=farm.id, granted_by=user.id, grantee_org_id=body.grantee_org_id, grantee_email=grantee_email or "", scope=body.scope, status="active")
    db.add(row)
    db.flush()
    audit(db, user, "consent.granted", "consent", str(row.id), farm.id, {"scope": body.scope})
    db.commit()
    return dump(row)


@app.delete("/api/v1/consents/{consent_id}")
def revoke_consent(consent_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(Consent, consent_id)
    if not row or row.granted_by != user.id:
        raise HTTPException(404, "Consent not found")
    row.status, row.revoked_at = "revoked", datetime.now(timezone.utc)
    audit(db, user, "consent.revoked", "consent", consent_id, row.farm_id)
    db.commit()
    return {"revoked": True, "consent_id": consent_id}


def cooperative_organization_ids(db: Session, user: User) -> list[UUID]:
    require_role(db, user, "cooperative_admin")
    organization_ids = [row.organization_id for row in db.query(OrganizationMember).filter_by(
        user_id=user.id, role="cooperative_admin",
    ).all()]
    if len(organization_ids) != 1:
        raise HTTPException(403, "This cooperative account must be assigned to exactly one cooperative organization")
    return organization_ids


def active_shared_farms(db: Session, user: User, organization_ids: list[UUID]) -> dict[str, Farm]:
    grants = db.query(Consent).filter(
        Consent.status == "active",
        Consent.scope == "delivery_summary",
        or_(Consent.grantee_email == user.email.lower(), Consent.grantee_org_id.in_(organization_ids)),
        or_(Consent.expires_at.is_(None), Consent.expires_at > datetime.now(timezone.utc)),
    ).all()
    farm_ids = {grant.farm_id for grant in grants}
    if not farm_ids:
        return {}
    return {farm.code.casefold(): farm for farm in db.query(Farm).filter(Farm.id.in_(farm_ids)).all()}


def reconciliation_summary(db: Session, run: ReconciliationRun, shared_farm_ids: set[UUID]) -> dict:
    items = db.query(ReconciliationItem).filter_by(run_id=run.id).all()
    statuses = [
        "matched" if item.status == "matched" and item.matched_farm_id in shared_farm_ids else
        "consent_revoked" if item.matched_farm_id and item.matched_farm_id not in shared_farm_ids else item.status
        for item in items
    ]
    matched = statuses.count("matched")
    resolved = sum(item.review_status in {"confirmed", "follow_up", "not_required"} for item in items)
    return {
        "id": str(run.id), "organization_id": str(run.organization_id), "filename": run.filename,
        "total_rows": run.total_rows, "matched_rows": matched, "exception_rows": run.total_rows - matched,
        "resolved_rows": resolved, "open_rows": run.total_rows - resolved,
        "status": "complete" if resolved == run.total_rows else "in_review",
        "created_at": run.created_at.isoformat(),
    }


def reconciliation_detail(db: Session, run: ReconciliationRun, shared_farms: dict[str, Farm]) -> dict:
    shared_farm_ids = {farm.id for farm in shared_farms.values()}
    items = db.query(ReconciliationItem).filter_by(run_id=run.id).order_by(ReconciliationItem.row_number).all()
    output = []
    for item in items:
        has_consent = item.matched_farm_id in shared_farm_ids
        farm = db.get(Farm, item.matched_farm_id) if has_consent else None
        delivery = db.get(Delivery, item.matched_delivery_id) if has_consent and item.matched_delivery_id else None
        lot = db.get(ProductLot, delivery.product_lot_id) if delivery else None
        production = db.get(ProductionRecord, lot.production_record_id) if lot else None
        status = item.status
        if item.matched_farm_id and not has_consent:
            status = "consent_revoked"
        output.append({
            "id": str(item.id), "row_number": item.row_number, "farm_code": item.farm_code,
            "farm_name": farm.name if farm else None,
            "collection_date": item.collection_date.isoformat() if item.collection_date else item.submitted_date or None,
            "quantity_liters": item.quantity_liters, "submitted_quantity": item.submitted_quantity,
            "receipt_reference": item.receipt_reference,
            "status": status, "discrepancies": item.discrepancy_details,
            "review_status": item.review_status, "review_note": item.review_note,
            "matched_delivery": ({
                "id": str(delivery.id), "date": delivery.delivery_date.isoformat(), "quantity": delivery.quantity,
                "unit": delivery.unit, "reference": delivery.reference, "status": delivery.status,
                "lot_code": lot.lot_code if lot else None, "product_type": lot.product_type if lot else None,
            } if delivery else None),
            "trace_graph": ([
                {"id": f"farm:{farm.id}", "type": "farm", "label": farm.name},
                {"id": f"production:{production.id}", "type": "production_record", "label": f"{production.quantity:g} {production.unit} · {production.recorded_on.isoformat()}"},
                {"id": f"lot:{lot.id}", "type": "product_lot", "label": lot.lot_code},
                {"id": f"delivery:{delivery.id}", "type": "delivery", "label": delivery.reference or delivery.delivery_date.isoformat()},
                {"id": f"intake:{item.id}", "type": "cooperative_intake", "label": f"Row {item.row_number}"},
            ] if farm and delivery and lot else [
                {"id": f"intake:{item.id}", "type": "cooperative_intake", "label": f"Row {item.row_number}"},
                {"id": f"exception:{item.id}", "type": "exception", "label": status.replace("_", " ")},
            ]),
        })
    return {"run": reconciliation_summary(db, run, shared_farm_ids), "items": output}


@app.post("/api/v1/cooperative/reconciliation/runs", status_code=201)
async def create_reconciliation_run(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    organization_ids = cooperative_organization_ids(db, user)
    filename = Path(file.filename or "collection.csv").name[:255]
    if not filename.lower().endswith(".csv"):
        raise HTTPException(415, "Upload a CSV collection sheet")
    content = await file.read(2_000_001)
    if len(content) > 2_000_000:
        raise HTTPException(413, "Collection CSV is limited to 2 MB")
    try:
        entries = parse_collection_csv(content)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if len(entries) > MAX_RECONCILIATION_ROWS:
        raise HTTPException(422, f"CSV may contain at most {MAX_RECONCILIATION_ROWS} data rows")

    source_hash = hashlib.sha256(content).hexdigest()
    organization_id = organization_ids[0]
    if db.query(ReconciliationRun).filter_by(organization_id=organization_id, source_sha256=source_hash).first():
        raise HTTPException(409, "This collection sheet has already been imported")
    shared_farms = active_shared_farms(db, user, organization_ids)
    run = ReconciliationRun(
        organization_id=organization_id, uploaded_by=user.id, filename=filename,
        source_sha256=source_hash, total_rows=len(entries),
    )
    db.add(run)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "This collection sheet has already been imported") from exc

    for entry in entries:
        farm = shared_farms.get(entry["farm_code"].casefold())
        status = "not_shared"
        delivery_id = None
        discrepancies = ["Farm not found in this cooperative's active consented records"]
        if entry["errors"]:
            status, discrepancies = "invalid_row", entry["errors"]
            farm = None
        elif farm:
            candidates = db.query(Delivery, ProductLot).join(
                ProductLot, ProductLot.id == Delivery.product_lot_id,
            ).filter(
                Delivery.farm_id == farm.id,
                Delivery.delivery_date == entry["collection_date"],
                Delivery.unit == "L",
                Delivery.status.in_(["pending", "accepted"]),
                func.lower(ProductLot.product_type) == "milk",
            ).all()
            candidate_rows = [{
                "id": str(delivery.id), "quantity": delivery.quantity, "reference": delivery.reference,
            } for delivery, _ in candidates]
            status, delivery_id, discrepancies = classify_collection_entry(entry, candidate_rows)

        db.add(ReconciliationItem(
            run_id=run.id, row_number=entry["row_number"], farm_code=entry["farm_code"],
            submitted_date=entry["submitted_date"], collection_date=entry["collection_date"],
            submitted_quantity=entry["submitted_quantity"], quantity_liters=entry["quantity_liters"],
            receipt_reference=entry["receipt_reference"], status=status,
            matched_farm_id=farm.id if farm else None,
            matched_delivery_id=UUID(delivery_id) if delivery_id else None,
            discrepancy_details=discrepancies, review_status="not_required" if status == "matched" else "pending",
        ))
    db.flush()
    summary = reconciliation_summary(db, run, {farm.id for farm in shared_farms.values()})
    audit(db, user, "cooperative.reconciliation_imported", "reconciliation_run", str(run.id), metadata={
        "total_rows": run.total_rows, "matched_rows": summary["matched_rows"], "exception_rows": summary["exception_rows"],
    })
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "This collection sheet has already been imported") from exc
    db.refresh(run)
    return reconciliation_detail(db, run, shared_farms)


@app.get("/api/v1/cooperative/reconciliation/runs")
def list_reconciliation_runs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    organization_ids = cooperative_organization_ids(db, user)
    shared_farms = active_shared_farms(db, user, organization_ids)
    runs = db.query(ReconciliationRun).filter_by(organization_id=organization_ids[0]).order_by(
        ReconciliationRun.created_at.desc(),
    ).limit(25).all()
    return [reconciliation_summary(db, run, {farm.id for farm in shared_farms.values()}) for run in runs]


@app.get("/api/v1/cooperative/reconciliation/runs/{run_id}")
def get_reconciliation_run(run_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    organization_ids = cooperative_organization_ids(db, user)
    run = db.query(ReconciliationRun).filter_by(id=run_id, organization_id=organization_ids[0]).first()
    if not run:
        raise HTTPException(404, "Reconciliation run not found")
    return reconciliation_detail(db, run, active_shared_farms(db, user, organization_ids))


@app.post("/api/v1/cooperative/reconciliation/items/{item_id}/review")
def review_reconciliation_item(
    item_id: UUID,
    body: ReconciliationReviewCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    organization_ids = cooperative_organization_ids(db, user)
    item = db.get(ReconciliationItem, item_id)
    run = db.get(ReconciliationRun, item.run_id) if item else None
    if not item or not run or run.organization_id != organization_ids[0]:
        raise HTTPException(404, "Reconciliation item not found")
    if item.review_status == "not_required":
        raise HTTPException(409, "This row already matched the recorded delivery")
    if body.decision == "confirmed":
        shared_farms = active_shared_farms(db, user, organization_ids)
        if not item.matched_farm_id or item.matched_farm_id not in {farm.id for farm in shared_farms.values()}:
            raise HTTPException(403, "A confirmed review requires an active farm consent and a linked delivery")
        if not item.matched_delivery_id:
            raise HTTPException(422, "This exception has no delivery record to confirm")
    item.review_status = body.decision
    item.reviewed_by = user.id
    item.reviewed_at = datetime.now(timezone.utc)
    item.review_note = body.note.strip()
    audit(db, user, "cooperative.reconciliation_reviewed", "reconciliation_item", str(item.id), metadata={
        "decision": body.decision, "match_status": item.status,
    })
    db.commit()
    db.refresh(run)
    return reconciliation_detail(db, run, active_shared_farms(db, user, organization_ids))


def settlement_close_detail(db: Session, close: SettlementClose) -> dict:
    items = db.query(SettlementCloseItem).filter_by(close_id=close.id).order_by(SettlementCloseItem.member_code).all()
    reconciled = sum(item.status == "reconciled" for item in items)
    pending = sum(item.review_status == "pending" for item in items)
    unresolved = sum(item.status != "reconciled" and item.review_status != "accepted_with_note" for item in items)
    issue_counts: dict[str, int] = {}
    for item in items:
        for issue in item.issues or []:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
    return {
        "close": {
            "id": str(close.id), "organization_id": str(close.organization_id),
            "period_start": close.period_start.isoformat(), "period_end": close.period_end.isoformat(),
            "status": close.status, "member_count": len(items), "reconciled_count": reconciled,
            "exception_count": len(items) - reconciled, "pending_review_count": pending,
            "unresolved_exception_count": unresolved, "issue_counts": issue_counts,
            "collection_filename": close.collection_filename, "processor_filename": close.processor_filename,
            "payout_filename": close.payout_filename, "collection_row_count": close.collection_row_count,
            "processor_row_count": close.processor_row_count, "payout_row_count": close.payout_row_count,
            "source_hashes": {"collection": close.collection_sha256, "processor": close.processor_sha256, "payout": close.payout_sha256},
            "approval_note": close.approval_note, "approved_by": str(close.approved_by) if close.approved_by else None,
            "approved_at": close.approved_at.isoformat() if close.approved_at else None,
            "created_at": close.created_at.isoformat(),
        },
        "items": [dump(item) for item in items],
    }


@app.post("/api/v1/cooperative/settlement-closes", status_code=201)
async def create_settlement_close(
    period_start: date = Form(...),
    period_end: date = Form(...),
    collection_file: UploadFile = File(...),
    processor_file: UploadFile = File(...),
    payout_file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    organization_ids = cooperative_organization_ids(db, user)
    files = {
        "collection": (collection_file, "collection"),
        "processor": (processor_file, "processor settlement"),
        "payout": (payout_file, "payout"),
    }
    contents = {}
    filenames = {}
    for key, (upload, label) in files.items():
        filename = Path(upload.filename or f"{key}.csv").name[:255]
        if not filename.lower().endswith(".csv"):
            raise HTTPException(415, f"Upload a CSV file for {label}")
        content = await upload.read(5_000_001)
        if len(content) > 5_000_000:
            raise HTTPException(413, f"{label.title()} CSV is limited to 5 MB")
        contents[key] = content
        filenames[key] = filename
    try:
        parsed = parse_settlement_sources(contents["collection"], contents["processor"], contents["payout"], period_start, period_end)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    source_hashes = {key: hashlib.sha256(content).hexdigest() for key, content in contents.items()}
    fingerprint_payload = "|".join([str(organization_ids[0]), period_start.isoformat(), period_end.isoformat(), *[source_hashes[key] for key in ("collection", "processor", "payout")]])
    fingerprint = hashlib.sha256(fingerprint_payload.encode("utf-8")).hexdigest()
    if db.query(SettlementClose).filter_by(organization_id=organization_ids[0], source_fingerprint=fingerprint).first():
        raise HTTPException(409, "These exact source exports have already been used for this settlement period")
    close = SettlementClose(
        organization_id=organization_ids[0], created_by=user.id, period_start=period_start, period_end=period_end,
        source_fingerprint=fingerprint, collection_filename=filenames["collection"], processor_filename=filenames["processor"],
        payout_filename=filenames["payout"], collection_sha256=source_hashes["collection"],
        processor_sha256=source_hashes["processor"], payout_sha256=source_hashes["payout"],
        collection_row_count=parsed["collection_row_count"], processor_row_count=parsed["processor_row_count"],
        payout_row_count=parsed["payout_row_count"], status="review_required",
    )
    db.add(close)
    try:
        db.flush()
        for item in parsed["items"]:
            db.add(SettlementCloseItem(
                close_id=close.id, member_code=item["member_code"], collection_liters=item["collection_liters"],
                processor_liters=item["processor_liters"], volume_variance_liters=item["volume_variance_liters"],
                gross_amount_kes=item["gross_amount_kes"], deductions_kes=item["deductions_kes"],
                net_amount_kes=item["net_amount_kes"], payout_amount_kes=item["payout_amount_kes"],
                processor_arithmetic_variance_kes=item["processor_arithmetic_variance_kes"], payout_variance_kes=item["payout_variance_kes"],
                status=item["status"], issues=item["issues"],
                source_rows={"collection": item["collection_rows"], "processor": item["processor_rows"], "payout": item["payout_rows"]},
                source_references={"collection": item["collection_references"], "processor": item["processor_references"], "payout": item["payout_references"]},
                review_status=item["review_status"],
            ))
        audit(db, user, "cooperative.settlement_close_created", "settlement_close", str(close.id), metadata={
            "period_start": period_start.isoformat(), "period_end": period_end.isoformat(),
            "member_count": len(parsed["items"]), "source_hashes": source_hashes,
        })
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "These exact source exports have already been used for this settlement period") from exc
    db.refresh(close)
    return settlement_close_detail(db, close)


@app.get("/api/v1/cooperative/settlement-closes")
def list_settlement_closes(user: User = Depends(current_user), db: Session = Depends(get_db)):
    organization_ids = cooperative_organization_ids(db, user)
    closes = db.query(SettlementClose).filter_by(organization_id=organization_ids[0]).order_by(SettlementClose.created_at.desc()).limit(50).all()
    return [settlement_close_detail(db, close)["close"] for close in closes]


@app.get("/api/v1/cooperative/settlement-closes/{close_id}")
def get_settlement_close(close_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    organization_ids = cooperative_organization_ids(db, user)
    close = db.query(SettlementClose).filter_by(id=close_id, organization_id=organization_ids[0]).first()
    if not close:
        raise HTTPException(404, "Settlement close not found")
    return settlement_close_detail(db, close)


@app.post("/api/v1/cooperative/settlement-closes/{close_id}/items/{item_id}/review")
def review_settlement_item(
    close_id: UUID, item_id: UUID, body: SettlementReviewCreate,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    organization_ids = cooperative_organization_ids(db, user)
    close = db.query(SettlementClose).filter_by(id=close_id, organization_id=organization_ids[0]).first()
    item = db.query(SettlementCloseItem).filter_by(id=item_id, close_id=close_id).first()
    if not close or not item:
        raise HTTPException(404, "Settlement exception not found")
    if close.status == "approved":
        raise HTTPException(409, "An approved close is immutable")
    if item.status == "reconciled":
        raise HTTPException(409, "This member row reconciled automatically and needs no exception review")
    item.review_status = "accepted_with_note" if body.decision == "accept_with_note" else "follow_up"
    item.reviewer_id = user.id
    item.reviewed_at = datetime.now(timezone.utc)
    item.review_note = body.note
    audit(db, user, "cooperative.settlement_exception_reviewed", "settlement_close_item", str(item.id), metadata={
        "close_id": str(close.id), "member_code": item.member_code, "decision": body.decision, "note": body.note,
    })
    db.commit()
    return settlement_close_detail(db, close)


@app.post("/api/v1/cooperative/settlement-closes/{close_id}/approve")
def approve_settlement_close(
    close_id: UUID, body: SettlementApproveCreate,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    organization_ids = cooperative_organization_ids(db, user)
    close = db.query(SettlementClose).filter_by(id=close_id, organization_id=organization_ids[0]).first()
    if not close:
        raise HTTPException(404, "Settlement close not found")
    if close.status == "approved":
        raise HTTPException(409, "This settlement close is already approved")
    pending = db.query(SettlementCloseItem).filter(
        SettlementCloseItem.close_id == close.id,
        SettlementCloseItem.status != "reconciled",
        SettlementCloseItem.review_status != "accepted_with_note",
    ).count()
    if pending:
        raise HTTPException(409, f"Review all {pending} open exception(s) before approving this close")
    close.status = "approved"
    close.approved_by = user.id
    close.approved_at = datetime.now(timezone.utc)
    close.approval_note = body.note
    audit(db, user, "cooperative.settlement_close_approved", "settlement_close", str(close.id), metadata={
        "period_start": close.period_start.isoformat(), "period_end": close.period_end.isoformat(),
        "approved_exception_count": db.query(SettlementCloseItem).filter_by(close_id=close.id, review_status="accepted_with_note").count(),
    })
    db.commit()
    return settlement_close_detail(db, close)


def spreadsheet_safe_cell(value):
    text_value = str(value if value is not None else "")
    if text_value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text_value
    return text_value


@app.get("/api/v1/cooperative/settlement-closes/{close_id}/statement-pack")
def download_settlement_statement_pack(close_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    organization_ids = cooperative_organization_ids(db, user)
    close = db.query(SettlementClose).filter_by(id=close_id, organization_id=organization_ids[0]).first()
    if not close:
        raise HTTPException(404, "Settlement close not found")
    if close.status != "approved":
        raise HTTPException(409, "Approve the close before downloading its statement pack")
    rows = db.query(SettlementCloseItem).filter_by(close_id=close.id).order_by(SettlementCloseItem.member_code).all()
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["member_code", "period_start", "period_end", "collection_liters", "processor_liters", "volume_variance_liters", "gross_amount_kes", "deductions_kes", "net_amount_kes", "payout_amount_kes", "payout_variance_kes", "reconciliation_status", "review_status", "review_note"])
    for item in rows:
        writer.writerow([spreadsheet_safe_cell(item.member_code), close.period_start.isoformat(), close.period_end.isoformat(), item.collection_liters, item.processor_liters, item.volume_variance_liters, item.gross_amount_kes, item.deductions_kes, item.net_amount_kes, item.payout_amount_kes, item.payout_variance_kes, item.status, item.review_status, spreadsheet_safe_cell(item.review_note)])
    audit(db, user, "cooperative.settlement_statement_pack_downloaded", "settlement_close", str(close.id), metadata={"row_count": len(rows)})
    db.commit()
    filename = f"terravanta-settlement-{close.period_start.isoformat()}-{close.period_end.isoformat()}.csv"
    return Response(content=output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/v1/cooperative/deliveries")
def cooperative_deliveries(user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_role(db, user, "cooperative_admin", "platform_admin")
    member_orgs = select(OrganizationMember.organization_id).where(OrganizationMember.user_id == user.id, OrganizationMember.role == "cooperative_admin")
    consents = db.query(Consent).filter(
        Consent.status == "active",
        Consent.scope == "delivery_summary",
        or_(Consent.grantee_email == user.email.lower(), Consent.grantee_org_id.in_(member_orgs)),
        or_(Consent.expires_at.is_(None), Consent.expires_at > datetime.now(timezone.utc)),
    ).all()
    consent_by_farm = {consent.farm_id: consent for consent in consents}
    result = []
    for farm_id, consent in consent_by_farm.items():
        farm = db.get(Farm, farm_id)
        for row in db.query(Delivery).filter_by(farm_id=consent.farm_id).all():
            lot = db.get(ProductLot, row.product_lot_id)
            result.append({"farm_name": farm.name, "farm_code": farm.code, "delivery": dump(row), "product_type": lot.product_type, "lot_code": lot.lot_code, "scope": consent.scope, "synthetic": farm.is_synthetic, "documentation_gaps": [] if row.reference else ["Delivery reference is not recorded"]})
    return result


def build_alerts(db: Session, farm: Farm) -> list[dict]:
    today = date.today()
    alerts = []
    events = db.query(AnimalHealthEvent).filter(AnimalHealthEvent.farm_id == farm.id, AnimalHealthEvent.status == "open", AnimalHealthEvent.follow_up_on.is_not(None), AnimalHealthEvent.follow_up_on <= today + timedelta(days=7)).all()
    for event in events:
        animal = db.get(Animal, event.animal_id)
        alerts.append({"id": f"followup-{event.id}", "severity": "high" if event.follow_up_on <= today else "medium", "title": "Veterinary follow-up due", "trigger": f"Follow-up date: {event.follow_up_on.isoformat()}", "supporting_data": f"{animal.tag} · {event.event_type}", "next_action": "Review the recorded case and contact the responsible veterinarian.", "status": "open", "timestamp": event.created_at.isoformat()})
    for batch in db.query(FeedBatch).filter(FeedBatch.farm_id == farm.id, FeedBatch.quantity_kg < 100).all():
        alerts.append({"id": f"feed-{batch.id}", "severity": "medium", "title": "Feed inventory running low", "trigger": "Recorded batch quantity is below 100 kg", "supporting_data": f"{batch.name} · {batch.quantity_kg:g} kg", "next_action": "Review stock and upcoming feed needs.", "status": "open", "timestamp": batch.batch_date.isoformat()})
    for batch in db.query(FeedBatch).filter(FeedBatch.farm_id == farm.id, FeedBatch.aflatoxin_status == "pending_test").all():
        alerts.append({"id": f"lab-{batch.id}", "severity": "medium", "title": "Feed test result pending", "trigger": "Aflatoxin status is marked pending test", "supporting_data": batch.name, "next_action": "Record the laboratory result when received. No safety status is inferred.", "status": "open", "timestamp": batch.batch_date.isoformat()})
    milk = db.query(ProductionRecord).filter_by(farm_id=farm.id, product_type="milk").order_by(ProductionRecord.recorded_on.desc()).limit(8).all()
    if len(milk) >= 4:
        latest = milk[0]
        baseline = sum(row.quantity for row in milk[1:]) / len(milk[1:])
        if baseline and latest.quantity < baseline * 0.7:
            alerts.append({"id": f"production-{latest.id}", "severity": "medium", "title": "Milk production changed", "trigger": "Latest record is more than 30% below the recent recorded average", "supporting_data": f"Latest {latest.quantity:g} {latest.unit}; preceding average {baseline:.1f} {latest.unit}", "next_action": "Check the source records and review animal, feed, and collection notes.", "status": "open", "timestamp": latest.recorded_on.isoformat()})
    return alerts


@app.get("/api/v1/alerts")
def get_alerts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = primary_farm(db, user)
    return build_alerts(db, farm)


@app.post("/api/v1/ai/veterinary-assistant")
async def veterinary_assistant(body: AssistantRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    animal = db.get(Animal, body.animal_id)
    if not animal:
        raise HTTPException(404, "Animal not found")
    farm = farm_access(db, user, animal.farm_id)
    require_role(db, user, "farmer", "veterinarian", "platform_admin")
    enforce_ai_rate_limit(db, user)
    history = db.query(AnimalHealthEvent).filter_by(animal_id=animal.id).order_by(AnimalHealthEvent.occurred_on.desc()).limit(12).all()
    approved_sources = db.query(KnowledgeSource).filter_by(approved=True).all()
    terms = set(re.findall(r"[a-z]{4,}", body.question.lower()))
    retrieved = [source for source in approved_sources if terms.intersection(set(re.findall(r"[a-z]{4,}", (source.title + " " + source.content).lower())))]
    sources = [{"id": str(source.id), "title": source.title, "url": source.source_url, "publisher": source.publisher} for source in retrieved]
    request = AIRequest(user_id=user.id, farm_id=farm.id, request_type="veterinary_assistant", model_name=settings.nvidia_chat_model, prompt_version="v1")
    db.add(request)
    db.flush()
    recorded_facts = [{"event_id": str(row.id), "date": row.occurred_on.isoformat(), "type": row.event_type, "summary": row.summary, "observations": row.observations, "follow_up": row.follow_up_on.isoformat() if row.follow_up_on else None, "verified": row.verified} for row in history]
    response = {"request_id": str(request.id), "status": "unavailable", "answer": "", "recorded_facts": recorded_facts, "sources": sources, "model_generated": False, "safety_note": "AI support does not diagnose, prescribe, calculate doses, or replace a licensed veterinarian."}
    if not body.allow_external_processing:
        response["status"] = "consent_required"
        response["answer"] = "No external model request was made. Enable the explicit data-sharing option to send this case context to the configured NVIDIA endpoint."
        request.outcome = "consent_required"
    elif not settings.nvidia_api_key:
        response["answer"] = "NVIDIA is not configured. The farm records remain available; no AI answer was generated."
        request.outcome = "provider_unconfigured"
    else:
        context = {"animal": {"tag": animal.tag, "name": animal.name, "species": animal.species, "breed": animal.breed}, "recorded_health_events": recorded_facts, "approved_references": [{"id": str(row.id), "title": row.title, "url": row.source_url, "content": row.content[:2400]} for row in retrieved]}
        prompt = "You are a veterinary record review assistant. Never diagnose, recommend or name treatment/medication, calculate doses, or claim a record is clinically verified unless marked verified. Only summarize provided facts, identify missing record fields, state uncertainty, and cite provided source IDs when relevant. Do not invent references. If urgent warning signs are described, advise prompt assessment by a licensed veterinarian. Return plain text.\n\nCONTEXT: " + json.dumps(context, ensure_ascii=False) + "\nQUESTION: " + body.question
        started = time.perf_counter()
        try:
            answer, latency = await nvidia.chat([{"role": "user", "content": prompt}])
            if not safe_case_response(answer):
                answer = "The generated response was withheld because it appeared to contain treatment, dosage, or diagnostic instructions. Please review the recorded facts with a licensed veterinarian."
                request.outcome = "safety_filtered"
            else:
                request.outcome = "success"
            request.latency_ms = latency
            response.update({"status": request.outcome, "answer": answer, "model_generated": request.outcome == "success", "model": settings.nvidia_chat_model})
        except Exception as exc:
            log.warning("NVIDIA veterinary request failed (%s)", type(exc).__name__)
            request.outcome = "provider_error"
            request.latency_ms = round((time.perf_counter() - started) * 1000)
            response.update({"status": "unavailable", "answer": "The NVIDIA service is unavailable or rejected this request. No AI answer was generated; you can still review and add farm records."})
    db.add(AIResponse(request_id=request.id, content=response["answer"], structured_output={"status": response["status"], "recorded_facts": recorded_facts}, sources=sources))
    audit(db, user, "ai.veterinary_assistant", "ai_request", str(request.id), farm.id, {"status": response["status"], "model": settings.nvidia_chat_model})
    db.commit()
    return response


@app.post("/api/v1/documents/extract", status_code=201)
async def extract_document(farm_id: UUID, file: UploadFile = File(...), allow_external_processing: bool = Form(False), user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "veterinarian", "platform_admin")
    enforce_ai_rate_limit(db, user)
    if file.content_type not in {"application/pdf", "image/jpeg", "image/png"}:
        raise HTTPException(415, "Upload a PDF, JPEG, or PNG file")
    content = await file.read(8 * 1024 * 1024 + 1)
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(413, "Maximum document size is 8 MB")
    signatures = {"application/pdf": content.startswith(b"%PDF"), "image/jpeg": content.startswith(b"\xff\xd8\xff"), "image/png": content.startswith(b"\x89PNG\r\n\x1a\n")}
    if not signatures.get(file.content_type, False):
        raise HTTPException(415, "The file contents do not match the selected document type")
    suffix = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}[file.content_type]
    stored_path = Path(settings.uploads_dir).resolve()
    stored_path.mkdir(parents=True, exist_ok=True)
    path = stored_path / f"{secrets.token_hex(16)}{suffix}"
    path.write_bytes(content)
    extracted_text, fields, model_name, outcome = "", {}, "local-text-extractor", "pending_review"
    latency = None
    if file.content_type == "application/pdf":
        try:
            reader = PdfReader(str(path))
            if len(reader.pages) > 50:
                raise HTTPException(413, "PDFs are limited to 50 pages")
            extracted_text = "\n".join(page.extract_text() or "" for page in reader.pages)[:30000]
            fields = {"document_type": "unclassified", "extracted_characters": len(extracted_text), "needs_review": True}
            outcome = "local_extraction" if extracted_text else "manual_review_required"
        except HTTPException:
            path.unlink(missing_ok=True)
            raise
        except Exception:
            extracted_text = ""
            fields = {"document_type": "unclassified", "needs_review": True, "notice": "Could not extract selectable PDF text; use an image upload with NVIDIA configured."}
            outcome = "manual_review_required"
    elif allow_external_processing and settings.nvidia_parse_url:
        try:
            parsed_text, latency = await nvidia.parse_image(str(path), file.content_type)
            model_name = settings.nvidia_parse_model
            extracted_text = parsed_text[:30000]
            if settings.nvidia_api_key:
                extraction_prompt = (
                    "Extract only information explicitly visible in this parsed farm or veterinary document. "
                    "Return one JSON object with keys document_type, animal_tag, event_date, provider, "
                    "key_values, extracted_text, uncertainties. Use null for missing values. Do not infer, "
                    "diagnose, recommend treatment, or mark anything verified.\n\nDOCUMENT TEXT:\n" + parsed_text[:22000]
                )
                output, structure_latency = await nvidia.chat([{"role": "user", "content": extraction_prompt}], max_tokens=1200)
                latency += structure_latency
                parsed_fields, _ = parse_structured(output)
                draft = ExtractedDocumentDraft.model_validate(parsed_fields)
                if not draft.extracted_text and not draft.key_values:
                    raise ValueError("The model returned no extractable fields")
                fields = draft.model_dump(mode="json", exclude_none=True)
                extracted_text = draft.extracted_text or extracted_text
                model_name = f"{settings.nvidia_parse_model} + {settings.nvidia_chat_model}"
                outcome = "success"
            else:
                fields = {"document_type": "unclassified", "needs_review": True, "notice": "Parsed text is shown for manual review. NVIDIA_API_KEY is needed to map it into the extraction fields."}
                outcome = "parsed_needs_review"
        except (ValidationError, ValueError):
            fields = {"document_type": "unclassified", "needs_review": True, "notice": "The model response did not match the extraction schema. Review the parsed draft text manually."}
            outcome = "invalid_model_output"
        except Exception as exc:
            log.warning("NVIDIA document extraction failed (%s)", type(exc).__name__)
            fields = {"document_type": "unclassified", "needs_review": True, "notice": "NVIDIA parsing failed. Try again or enter the values manually."}
            outcome = "provider_error"
    else:
        notice = "External document processing was not approved for this upload; image OCR was not attempted." if not allow_external_processing else "NVIDIA_PARSE_URL is not configured; image OCR was not attempted."
        fields = {"document_type": "unclassified", "needs_review": True, "notice": notice}
        outcome = "consent_required" if not allow_external_processing else "provider_unconfigured"
    row = DocumentExtraction(farm_id=farm.id, uploaded_by=user.id, filename=Path(file.filename or "upload").name[:255], mime_type=file.content_type, extracted_text=extracted_text, extracted_fields=fields, status="pending_review", source_model=model_name)
    db.add(row)
    db.flush()
    request = AIRequest(user_id=user.id, farm_id=farm.id, request_type="document_extraction", model_name=model_name, latency_ms=latency, outcome=outcome)
    db.add(request)
    audit(db, user, "document.extracted", "document_extraction", str(row.id), farm.id, {"model": model_name, "review_required": True, "external_processing_allowed": allow_external_processing, "outcome": outcome})
    db.commit()
    return {**dump(row), "review_required": True, "stored_file": path.name}


@app.post("/api/v1/documents/{document_id}/review")
def review_document(document_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(DocumentExtraction, document_id)
    if not row:
        raise HTTPException(404, "Document extraction not found")
    farm_access(db, user, row.farm_id)
    require_role(db, user, "farmer", "veterinarian", "platform_admin")
    row.status = "reviewed"
    audit(db, user, "document.reviewed", "document_extraction", document_id, row.farm_id, {"uploaded_by": str(row.uploaded_by)})
    db.commit()
    return {"reviewed": True, "message": "Reviewed extraction is retained separately. Add confirmed values to an official record using its normal workflow."}


@app.get("/api/v1/farms/{farm_id}/passport/shareable-records")
def shareable_records(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = farm_access(db, user, farm_id)
    return {"farm": {"code": farm.code, "name": farm.name, "county": farm.county, "verification_status": farm.verification_status}, "deliveries": [dump(row) for row in db.query(Delivery).filter_by(farm_id=farm.id).all()], "scope": "delivery_summary", "synthetic": farm.is_synthetic}
