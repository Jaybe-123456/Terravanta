import csv
import json
import hashlib
import io
import logging
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pypdf import PdfReader

from .ai import nvidia, parse_structured, safe_case_response, safe_farm_response
from .config import settings
from .db import AdminSessionLocal, Base, admin_engine, engine, get_admin_db, get_db
from .idempotency import replay_client_write, store_client_write_receipt
from .models import (
    AIRequest, AIResponse, Animal, AnimalHealthEvent, AnimalHealthFollowUp, AuditLog, Buyer, CompostApplication,
    CompostBatch, Consent, Delivery, DocumentExtraction, Farm, FarmMember, FeedAllocation,
    FeedBatch, KnowledgeSource, ManureRecord, Organization, OrganizationMember, Plot, SupabaseIdentityLink,
    ProductLot, ProductionRecord, ReconciliationItem, ReconciliationRun, SettlementClose, SettlementCloseItem, User, UserRole,
    VeterinaryContactRequest, VeterinaryContactMessage, FarmDomainEvent, Notification,
)
from .schemas import (
    AnimalCreate, AssistantRequest, CompostApplicationCreate, CompostCreate, ConsentCreate,
    DeliveryCreate, FarmCreate, FeedAllocationCreate, FeedBatchCreate, HealthEventCreate,
    HealthFollowUpCreate, ExtractedDocumentDraft, ManureCreate, PlotCreate, ProductionCreate, ReconciliationReviewCreate,
    SettlementApproveCreate, SettlementReviewCreate,
    TerrasRouteRequest, VeterinaryContactRequestCreate, VeterinaryContactRequestUpdate,
    VeterinaryContactMessageCreate, FarmAssistantRequest,
)
from .reconciliation import MAX_RECONCILIATION_ROWS, classify_collection_entry, parse_collection_csv
from .settlement import parse_settlement_sources
from .security import bearer, current_identity, current_user, get_scoped_db, issue_demo_token, require_role, user_role, user_roles, verified_supabase_user
from .seed import FARMER_ID, FARM_ID, seed
from .receivables import router as receivables_router
from .notifications import router as notifications_router
from .whatsapp_routes import router as whatsapp_router
from .workflows import append_domain_event, schedule_health_follow_up

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("terravanta")
KENYA_TIMEZONE = timezone(timedelta(hours=3))


def farm_today() -> date:
    """Kenyan farm event dates are local calendar dates; service timestamps remain UTC."""
    return datetime.now(KENYA_TIMEZONE).date()


def initialize_database():
    if settings.service_mode != "api":
        raise RuntimeError("FastAPI web service requires SERVICE_MODE=api")
    if settings.app_env == "production":
        # Production schema changes are applied by Alembic before the API starts.
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return
    Base.metadata.create_all(bind=admin_engine)
    if admin_engine.dialect.name == "postgresql":
        with admin_engine.begin() as connection:
            connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS postgis")
            connection.exec_driver_sql("ALTER TABLE farms ADD COLUMN IF NOT EXISTS location geometry(Point, 4326)")
            connection.exec_driver_sql("UPDATE farms SET location = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) WHERE location IS NULL AND latitude IS NOT NULL AND longitude IS NOT NULL")
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_farms_location_gist ON farms USING GIST (location)")
    if settings.enable_synthetic_data:
        with AdminSessionLocal() as db:
            seed(db)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="Terravanta API", version="1.0.0", description="Veterinary-first farm intelligence API. Optional demonstration records are synthetic.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(receivables_router)
app.include_router(notifications_router)
app.include_router(whatsapp_router)


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
def demo_login(role: str, db: Session = Depends(get_admin_db)):
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


@app.post("/api/v1/auth/onboard", status_code=200)
def onboard_account(
    identity: dict = Depends(current_identity),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_scoped_db),
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

    metadata = provider_user.get("user_metadata") or {}
    display_name = str(metadata.get("full_name") or metadata.get("name") or email.split("@", 1)[0]).strip()[:120]
    if len(display_name) < 2:
        raise HTTPException(422, "Enter your name when creating the account")

    if db.get_bind().dialect.name == "postgresql":
        claim = db.execute(text("""
            SELECT internal_user_id, outcome
            FROM terravanta_private.claim_farmer_identity(CAST(:subject AS uuid), :email, :display_name)
        """), {"subject": str(user_id), "email": email, "display_name": display_name}).one()
        internal_user_id, outcome = claim.internal_user_id, claim.outcome
        if outcome == "unauthorized":
            db.rollback()
            raise HTTPException(401, "Supabase identity could not be bound to this request")
        if outcome == "invalid_profile":
            db.rollback()
            raise HTTPException(422, "A valid verified email and name are required")
        if outcome == "conflict":
            db.rollback()
            raise HTTPException(409, "This email is linked to an account that needs administrator review")
        db.info["terravanta.user_id"] = str(internal_user_id)
        db.execute(text("SELECT set_config('terravanta.user_id', :user_id, true)"), {"user_id": str(internal_user_id)})
    else:
        # The SQLite path mirrors first-run and legacy farmer linking in local
        # development. Production performs this atomically in PostgreSQL.
        linked = db.get(SupabaseIdentityLink, user_id)
        user = db.get(User, linked.user_id) if linked else db.get(User, user_id)
        outcome = "existing" if user else ""
        if user and user.email.lower() != email:
            outcome = "conflict"
        if user is None:
            user = db.query(User).filter(func.lower(User.email) == email).first()
            if user:
                assigned = user_roles(db, user)
                has_org_membership = db.query(OrganizationMember).filter_by(user_id=user.id).first() is not None
                is_veterinarian = db.query(FarmMember).filter_by(user_id=user.id, role="veterinarian").first() is not None
                if assigned.difference({"farmer"}) or has_org_membership or is_veterinarian:
                    outcome = "conflict"
                else:
                    outcome = "linked_legacy_farmer"
                    if not linked:
                        db.add(SupabaseIdentityLink(supabase_user_id=user_id, user_id=user.id))
                    if "farmer" not in assigned:
                        db.add(UserRole(user_id=user.id, role="farmer"))
            else:
                user = User(id=user_id, display_name=display_name, email=email)
                db.add(user)
                db.add(UserRole(user_id=user.id, role="farmer"))
                outcome = "created"
        if outcome == "conflict":
            db.rollback()
            raise HTTPException(409, "This email is linked to an account that needs administrator review")
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "This email is linked to an account that needs administrator review") from exc
        internal_user_id = user.id
        db.info["terravanta.user_id"] = str(internal_user_id)

    user = db.get(User, internal_user_id)
    if user is None:
        db.rollback()
        raise HTTPException(409, "Terravanta account provisioning could not be completed")
    if outcome == "created":
        audit(db, user, "account.farmer_onboarded", "user", str(user.id))
    elif outcome == "linked_legacy_farmer":
        audit(db, user, "account.identity_linked", "user", str(user.id), metadata={"provider": "supabase"})
    db.commit()
    created = outcome == "created"
    roles = user_roles(db, user)
    if not roles:
        raise HTTPException(403, "This account needs a veterinarian or cooperative invitation before access")
    return {"id": str(user.id), "name": user.display_name, "email": user.email, "role": user_role(db, user), "roles": sorted(roles), "synthetic": False, "created": created}


@app.get("/api/v1/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    return {"id": str(user.id), "name": user.display_name, "email": user.email, "role": user_role(db, user), "roles": sorted(user_roles(db, user)), "synthetic": user.email.endswith(".demo")}


@app.get("/api/v1/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = primary_farm(db, user)
    animals = db.query(Animal).filter_by(farm_id=farm.id).count()
    open_cases = db.query(AnimalHealthEvent).filter_by(farm_id=farm.id, status="open").count()
    due_events = db.query(AnimalHealthEvent).filter(AnimalHealthEvent.farm_id == farm.id, AnimalHealthEvent.follow_up_on <= farm_today() + timedelta(days=7), AnimalHealthEvent.status == "open").count()
    feed_kg = db.query(func.coalesce(func.sum(FeedBatch.quantity_kg), 0)).filter_by(farm_id=farm.id).scalar()
    milk = db.query(ProductionRecord).filter(ProductionRecord.farm_id == farm.id, ProductionRecord.product_type == "milk", ProductionRecord.recorded_on >= farm_today() - timedelta(days=6)).order_by(ProductionRecord.recorded_on.desc()).all()
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
def list_farms(user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farms = db.query(Farm).join(FarmMember, FarmMember.farm_id == Farm.id).filter(FarmMember.user_id == user.id).order_by(Farm.created_at.desc()).all()
    return [dump(farm) for farm in farms]


@app.get("/api/v1/cooperatives")
def list_cooperatives(user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    require_role(db, user, "farmer", "platform_admin")
    return [{"id": str(row.id), "name": row.name} for row in db.query(Organization).filter_by(kind="cooperative").order_by(Organization.name).all()]


@app.post("/api/v1/farms", status_code=201)
def create_farm(body: FarmCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    require_role(db, user, "farmer", "platform_admin")
    replay = replay_client_write(db, user, idempotency_key, "/api/v1/farms", body)
    if replay:
        return replay
    code = f"TV-{re.sub('[^A-Z]', '', body.county.upper())[:3]}-{secrets.token_hex(2).upper()}"
    farm = Farm(code=code, name=body.name, owner_name=body.owner_name, county=body.county, subcounty=body.subcounty, latitude=body.latitude, longitude=body.longitude, size_acres=body.size_acres, farming_system=body.farming_system, production_activities=body.production_activities, verification_status="farmer_submitted", is_synthetic=False, created_by=user.id)
    db.add(farm)
    db.flush()
    if engine.dialect.name == "postgresql" and farm.latitude is not None and farm.longitude is not None:
        db.execute(text("UPDATE farms SET location = ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326) WHERE id = :farm_id"), {"longitude": farm.longitude, "latitude": farm.latitude, "farm_id": farm.id})
    db.add(FarmMember(farm_id=farm.id, user_id=user.id, role="owner"))
    audit(db, user, "farm.created", "farm", str(farm.id), farm.id)
    response = dump(farm)
    store_client_write_receipt(db, user, idempotency_key, "/api/v1/farms", body, response)
    db.commit()
    return response


@app.get("/api/v1/farms/{farm_id}")
def get_farm(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    return dump(farm_access(db, user, farm_id))


@app.get("/api/v1/farms/{farm_id}/passport")
def passport(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    sharing = []
    for consent in db.query(Consent).filter_by(farm_id=farm.id).all():
        row = dump(consent)
        organization = db.get(Organization, consent.grantee_org_id) if consent.grantee_org_id else None
        row["grantee_name"] = organization.name if organization else consent.grantee_email
        sharing.append(row)
    return {"farm": dump(farm), "provenance": {"farm": "farmer-submitted" if farm.verification_status == "farmer_submitted" else "verified", "synthetic": farm.is_synthetic}, "counts": {"animals": db.query(Animal).filter_by(farm_id=farm.id).count(), "plots": db.query(Plot).filter_by(farm_id=farm.id).count(), "health_events": db.query(AnimalHealthEvent).filter_by(farm_id=farm.id).count(), "health_events_verified": db.query(AnimalHealthEvent).filter_by(farm_id=farm.id, verified=True).count(), "production_records": db.query(ProductionRecord).filter_by(farm_id=farm.id).count(), "deliveries": db.query(Delivery).filter_by(farm_id=farm.id).count()}, "sharing": sharing}


@app.get("/api/v1/farms/{farm_id}/plots")
def list_plots(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    return [dump(row) for row in db.query(Plot).filter_by(farm_id=farm.id).order_by(Plot.name).all()]


@app.post("/api/v1/farms/{farm_id}/plots", status_code=201)
def create_plot(farm_id: UUID, body: PlotCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    path = f"/api/v1/farms/{farm_id}/plots"
    replay = replay_client_write(db, user, idempotency_key, path, body)
    if replay:
        return replay
    occupied = db.query(func.coalesce(func.sum(Plot.area_acres), 0)).filter_by(farm_id=farm.id).scalar()
    if farm.size_acres and occupied + body.area_acres > farm.size_acres:
        raise HTTPException(422, "Plot area exceeds the recorded farm area")
    row = Plot(farm_id=farm.id, **body.model_dump())
    db.add(row)
    db.flush()
    audit(db, user, "plot.created", "plot", str(row.id), farm.id)
    response = dump(row)
    store_client_write_receipt(db, user, idempotency_key, path, body, response)
    db.commit()
    return response


@app.get("/api/v1/farms/{farm_id}/animals")
def list_animals(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    return farm_animals(db, farm.id)


@app.post("/api/v1/farms/{farm_id}/animals", status_code=201)
def create_animal(farm_id: UUID, body: AnimalCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    path = f"/api/v1/farms/{farm_id}/animals"
    replay = replay_client_write(db, user, idempotency_key, path, body)
    if replay:
        return replay
    row = Animal(farm_id=farm.id, **body.model_dump())
    db.add(row)
    db.flush()
    audit(db, user, "animal.created", "animal", str(row.id), farm.id)
    response = dump(row)
    store_client_write_receipt(db, user, idempotency_key, path, body, response)
    db.commit()
    return response


@app.get("/api/v1/animals/{animal_id}")
def get_animal(animal_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    row = db.get(Animal, animal_id)
    if not row:
        raise HTTPException(404, "Animal not found")
    farm_access(db, user, row.farm_id)
    return {**dump(row), "health_history": [dump(event) for event in db.query(AnimalHealthEvent).filter_by(animal_id=row.id).order_by(AnimalHealthEvent.occurred_on.desc()).all()]}


@app.get("/api/v1/animals/{animal_id}/health-events")
def health_history(animal_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    animal = db.get(Animal, animal_id)
    if not animal:
        raise HTTPException(404, "Animal not found")
    farm_access(db, user, animal.farm_id)
    return [dump(row) for row in db.query(AnimalHealthEvent).filter_by(animal_id=animal.id).order_by(AnimalHealthEvent.occurred_on.desc()).all()]


def milk_productivity_context(db: Session, event: AnimalHealthEvent, follow_up: AnimalHealthFollowUp) -> dict:
    """Descriptive, unadjusted animal-milk comparison; it does not estimate treatment effect or ROI."""
    baseline_start, baseline_end = event.occurred_on - timedelta(days=7), event.occurred_on - timedelta(days=1)
    post_start, post_end = follow_up.occurred_on + timedelta(days=1), follow_up.occurred_on + timedelta(days=7)
    records = db.query(ProductionRecord).filter(
        ProductionRecord.farm_id == event.farm_id,
        ProductionRecord.animal_id == event.animal_id,
        func.lower(ProductionRecord.product_type) == "milk",
        func.lower(ProductionRecord.unit).in_(["l", "liter", "liters", "litre", "litres"]),
        ProductionRecord.recorded_on >= baseline_start,
        ProductionRecord.recorded_on <= post_end,
    ).all()
    by_day: dict[date, float] = {}
    for record in records:
        by_day[record.recorded_on] = by_day.get(record.recorded_on, 0.0) + float(record.quantity)

    def summarize(start: date, end: date) -> dict:
        observed = [liters for day, liters in by_day.items() if start <= day <= end]
        observed.sort()
        return {
            "from": start.isoformat(), "through": end.isoformat(),
            "days_with_records": len(observed), "recorded_liters": round(sum(observed), 2),
            "mean_liters_per_recorded_day": round(sum(observed) / len(observed), 2) if observed else None,
        }

    baseline, post = summarize(baseline_start, baseline_end), summarize(post_start, post_end)
    windows_observable = baseline["days_with_records"] >= 3 and post["days_with_records"] >= 3
    post_window_complete = post_end <= farm_today()
    available = windows_observable and post_window_complete
    change = None
    percent_change = None
    daily_value_rate_change = None
    if available:
        change = round(post["mean_liters_per_recorded_day"] - baseline["mean_liters_per_recorded_day"], 2)
        if baseline["mean_liters_per_recorded_day"]:
            percent_change = round(change / baseline["mean_liters_per_recorded_day"] * 100, 1)
        if follow_up.milk_price_kes_per_liter is not None:
            daily_value_rate_change = round(change * float(follow_up.milk_price_kes_per_liter), 2)
    return {
        "comparison_available": available,
        "comparison_basis": "7 recorded calendar days before the health event vs. 7 recorded calendar days after this follow-up",
        "baseline": baseline,
        "post_follow_up": post,
        "unadjusted_change_liters_per_recorded_day": change,
        "unadjusted_change_percent": percent_change,
        "estimated_daily_gross_milk_value_rate_change_kes": daily_value_rate_change,
        "farmgate_price_source": follow_up.milk_price_source,
        "interpretation": "Descriptive association only. Recording coverage, lactation, feed, season, concurrent illness and other factors are not controlled. This is not a treatment effect, additional revenue, or ROI.",
    }


@app.get("/api/v1/farms/{farm_id}/health-events")
def farm_health_events(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    events = db.query(AnimalHealthEvent).filter_by(farm_id=farm.id).order_by(AnimalHealthEvent.occurred_on.desc()).limit(200).all()
    result = []
    for event in events:
        animal = db.get(Animal, event.animal_id)
        follow_ups = db.query(AnimalHealthFollowUp).filter_by(farm_id=farm.id, health_event_id=event.id).order_by(AnimalHealthFollowUp.occurred_on.desc(), AnimalHealthFollowUp.created_at.desc()).all()
        result.append({
            **dump(event),
            "animal_name": animal.name if animal else "Unknown animal",
            "animal_tag": animal.tag if animal else "",
            "follow_up_count": len(follow_ups),
            "follow_ups": [dump(item) for item in follow_ups],
        })
    return result


def serialize_vet_contact_request(db: Session, row: VeterinaryContactRequest) -> dict:
    animal = db.get(Animal, row.animal_id) if row.animal_id else None
    requester = db.get(User, row.requester_user_id)
    veterinarian = db.get(User, row.veterinarian_user_id) if row.veterinarian_user_id else None
    return {
        **dump(row),
        "animal_tag": animal.tag if animal else None,
        "animal_name": animal.name if animal else None,
        "requester_name": requester.display_name if requester else "Farm member",
        "veterinarian_name": veterinarian.display_name if veterinarian else None,
    }


@app.get("/api/v1/farms/{farm_id}/veterinary-contact-requests")
def list_vet_contact_requests(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    role = user_role(db, user)
    require_role(db, user, "farmer", "veterinarian", "platform_admin")
    query = db.query(VeterinaryContactRequest).filter(VeterinaryContactRequest.farm_id == farm.id)
    if role == "farmer":
        query = query.filter(VeterinaryContactRequest.requester_user_id == user.id)
    elif role == "veterinarian":
        query = query.filter(or_(
            VeterinaryContactRequest.veterinarian_user_id == user.id,
            VeterinaryContactRequest.status == "pending",
        ))
    rows = query.order_by(VeterinaryContactRequest.created_at.desc()).limit(100).all()
    return [serialize_vet_contact_request(db, row) for row in rows]


@app.post("/api/v1/farms/{farm_id}/veterinary-contact-requests", status_code=201)
def create_vet_contact_request(
    farm_id: UUID,
    body: VeterinaryContactRequestCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_scoped_db),
):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer")
    if body.animal_id:
        animal = db.query(Animal).filter_by(id=body.animal_id, farm_id=farm.id).first()
        if not animal:
            raise HTTPException(422, "Choose an animal registered to this farm")

    veterinarians = db.query(FarmMember.user_id).filter(
        FarmMember.farm_id == farm.id,
        FarmMember.role == "veterinarian",
    ).all()
    vet_ids = [item.user_id for item in veterinarians]
    if not vet_ids:
        raise HTTPException(409, "No veterinarian is assigned to this farm yet. Ask your cooperative to connect a veterinarian before sending a request.")

    row = VeterinaryContactRequest(
        farm_id=farm.id,
        animal_id=body.animal_id,
        requester_user_id=user.id,
        message=body.message.strip(),
        urgency=body.urgency,
        preferred_contact_method=body.preferred_contact_method,
        status="pending",
    )
    db.add(row)
    db.flush()
    source_event = append_domain_event(
        db,
        farm_id=farm.id,
        actor=user,
        event_type="veterinary.contact_requested",
        aggregate_type="veterinary_contact_request",
        aggregate_id=row.id,
        idempotency_key=f"vet-contact:{row.id}:requested",
        payload={"urgency": row.urgency, "preferred_contact_method": row.preferred_contact_method, "animal_id": str(row.animal_id) if row.animal_id else None},
    )
    for vet_id in vet_ids:
        db.add(Notification(
            farm_id=farm.id,
            event_id=source_event.id,
            recipient_user_id=vet_id,
            notification_type="veterinary_contact_requested",
            title="Farmer requested veterinary contact",
            body=f"A {row.urgency} contact request is waiting for {farm.name}.",
            severity="high" if row.urgency in {"urgent", "emergency"} else "medium",
            action_section="veterinary",
            idempotency_key=f"vet-contact:{row.id}:requested:{vet_id}",
        ))
    if settings.whatsapp_delivery_enabled and db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT terravanta_private.enqueue_whatsapp_contact_request(:request_id)"),
            {"request_id": row.id},
        )
    audit(db, user, "veterinary.contact_requested", "veterinary_contact_request", str(row.id), farm.id, {"urgency": row.urgency})
    db.commit()
    db.refresh(row)
    result = serialize_vet_contact_request(db, row)
    result["notified_veterinarians"] = len(vet_ids)
    result["message_delivery"] = "in_app; WhatsApp alert queued only for assigned veterinarians with active channel consent when delivery is enabled"
    return result


@app.patch("/api/v1/veterinary-contact-requests/{request_id}")
def update_vet_contact_request(
    request_id: UUID,
    body: VeterinaryContactRequestUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_scoped_db),
):
    row = db.query(VeterinaryContactRequest).filter_by(id=request_id).with_for_update().first()
    if not row:
        raise HTTPException(404, "Veterinary contact request not found")
    membership = db.query(FarmMember).filter_by(farm_id=row.farm_id, user_id=user.id).first()
    if not membership:
        raise HTTPException(404, "Veterinary contact request not found")

    old_status = row.status
    if body.status == "cancelled":
        require_role(db, user, "farmer")
        if row.requester_user_id != user.id or old_status != "pending":
            raise HTTPException(409, "Only the requesting farmer can cancel a pending request")
    else:
        require_role(db, user, "veterinarian")
        if membership.role != "veterinarian":
            raise HTTPException(403, "Only a veterinarian assigned to this farm can respond")
        if body.status in {"accepted", "declined"} and old_status != "pending":
            raise HTTPException(409, "Only a pending request can be accepted or declined")
        if body.status == "contacted" and (old_status != "accepted" or row.veterinarian_user_id != user.id):
            raise HTTPException(409, "Only the veterinarian who accepted this request can record contact")
        if old_status == "pending":
            row.veterinarian_user_id = user.id
        elif row.veterinarian_user_id != user.id:
            raise HTTPException(403, "This request has already been accepted by another veterinarian")

    row.status = body.status
    row.updated_at = datetime.now(timezone.utc)
    row.responded_at = row.updated_at if body.status in {"accepted", "declined", "contacted"} else None
    source_event = append_domain_event(
        db,
        farm_id=row.farm_id,
        actor=user,
        event_type=f"veterinary.contact_{body.status}",
        aggregate_type="veterinary_contact_request",
        aggregate_id=row.id,
        idempotency_key=f"vet-contact:{row.id}:{body.status}:{row.updated_at.isoformat()}",
        payload={"previous_status": old_status, "status": row.status, "veterinarian_user_id": str(row.veterinarian_user_id) if row.veterinarian_user_id else None},
    )
    recipients = [row.requester_user_id] if user.id != row.requester_user_id else [
        item.user_id for item in db.query(FarmMember).filter_by(farm_id=row.farm_id, role="veterinarian").all()
    ]
    for recipient_id in recipients:
        db.add(Notification(
            farm_id=row.farm_id,
            event_id=source_event.id,
            recipient_user_id=recipient_id,
            notification_type=f"veterinary_contact_{body.status}",
            title=f"Veterinary contact request {body.status}",
            body=f"The contact request for {row.message[:100] or 'your farm'} is now {body.status.replace('_', ' ')}.",
            severity="info",
            action_section="veterinary",
            idempotency_key=f"vet-contact:{row.id}:{body.status}:{recipient_id}:{source_event.id}",
        ))
    audit(db, user, f"veterinary.contact_{body.status}", "veterinary_contact_request", str(row.id), row.farm_id)
    db.commit()
    db.refresh(row)
    return serialize_vet_contact_request(db, row)


def serialize_vet_contact_message(db: Session, row: VeterinaryContactMessage, user: User) -> dict:
    sender = db.get(User, row.sender_user_id)
    return {
        "id": str(row.id),
        "request_id": str(row.request_id),
        "sender_user_id": str(row.sender_user_id),
        "sender_name": sender.display_name if sender else "Farm member",
        "is_mine": row.sender_user_id == user.id,
        "body": row.body,
        "channel": row.source_channel,
        "created_at": row.created_at.isoformat(),
    }


def contact_request_for_conversation(db: Session, user: User, request_id: UUID) -> VeterinaryContactRequest:
    row = db.query(VeterinaryContactRequest).filter_by(id=request_id).first()
    if not row:
        raise HTTPException(404, "Veterinary contact request not found")
    membership = db.query(FarmMember).filter_by(farm_id=row.farm_id, user_id=user.id).first()
    if not membership:
        raise HTTPException(404, "Veterinary contact request not found")
    if row.requester_user_id != user.id:
        if membership.role != "veterinarian":
            raise HTTPException(404, "Veterinary contact request not found")
        if row.status != "pending" and row.veterinarian_user_id != user.id:
            raise HTTPException(404, "Veterinary contact request not found")
    return row


@app.get("/api/v1/veterinary-contact-requests/{request_id}/messages")
def list_vet_contact_messages(
    request_id: UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_scoped_db),
):
    row = contact_request_for_conversation(db, user, request_id)
    messages = db.query(VeterinaryContactMessage).filter_by(
        request_id=row.id, farm_id=row.farm_id,
    ).order_by(VeterinaryContactMessage.created_at.asc()).limit(200).all()
    return {"items": [serialize_vet_contact_message(db, item, user) for item in messages]}


@app.post("/api/v1/veterinary-contact-requests/{request_id}/messages", status_code=201)
def create_vet_contact_message(
    request_id: UUID,
    body: VeterinaryContactMessageCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_scoped_db),
):
    row = contact_request_for_conversation(db, user, request_id)
    membership = db.query(FarmMember).filter_by(farm_id=row.farm_id, user_id=user.id).first()
    if row.status not in {"pending", "accepted", "contacted"}:
        raise HTTPException(409, "This request is closed; no further messages can be added")
    if row.requester_user_id == user.id:
        require_role(db, user, "farmer")
        recipients = (
            [row.veterinarian_user_id]
            if row.veterinarian_user_id else [
                item.user_id for item in db.query(FarmMember).filter_by(farm_id=row.farm_id, role="veterinarian").all()
            ]
        )
    else:
        require_role(db, user, "veterinarian")
        if membership.role != "veterinarian" or row.veterinarian_user_id != user.id or row.status not in {"accepted", "contacted"}:
            raise HTTPException(403, "Accept this request before messaging the farmer")
        recipients = [row.requester_user_id]

    idempotency_key = f"vet-contact-message:{row.id}:{user.id}:{body.client_message_id}"
    existing = db.query(VeterinaryContactMessage).filter_by(idempotency_key=idempotency_key).first()
    if existing:
        return serialize_vet_contact_message(db, existing, user)

    source_event = append_domain_event(
        db,
        farm_id=row.farm_id,
        actor=user,
        event_type="veterinary.contact_message_sent",
        aggregate_type="veterinary_contact_request",
        aggregate_id=row.id,
        idempotency_key=f"{idempotency_key}:event",
        payload={"channel": "in_app", "client_message_id": str(body.client_message_id)},
    )
    message = VeterinaryContactMessage(
        request_id=row.id,
        farm_id=row.farm_id,
        event_id=source_event.id,
        sender_user_id=user.id,
        body=body.body,
        source_channel="in_app",
        idempotency_key=idempotency_key,
    )
    db.add(message)
    db.flush()
    for recipient_id in set(recipients):
        if recipient_id is None or recipient_id == user.id:
            continue
        db.add(Notification(
            farm_id=row.farm_id,
            event_id=source_event.id,
            recipient_user_id=recipient_id,
            notification_type="veterinary_contact_message",
            title="New message about a veterinary request",
            body="Open Veterinary in Terravanta to read and reply to the request.",
            severity="high" if row.urgency == "emergency" else "medium",
            action_section="veterinary",
            idempotency_key=f"{idempotency_key}:notification:{recipient_id}",
        ))
    if settings.whatsapp_delivery_enabled and db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT terravanta_private.enqueue_whatsapp_contact_message(:message_id)"),
            {"message_id": message.id},
        )
    audit(db, user, "veterinary.contact_message_sent", "veterinary_contact_message", str(message.id), row.farm_id, {"request_id": str(row.id), "channel": "in_app"})
    db.commit()
    db.refresh(message)
    return serialize_vet_contact_message(db, message, user)


@app.get("/api/v1/health-events/{event_id}/follow-ups")
def list_health_follow_ups(event_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    event = db.get(AnimalHealthEvent, event_id)
    if not event:
        raise HTTPException(404, "Health event not found")
    farm_access(db, user, event.farm_id)
    follow_ups = db.query(AnimalHealthFollowUp).filter_by(farm_id=event.farm_id, health_event_id=event.id).order_by(AnimalHealthFollowUp.occurred_on.desc(), AnimalHealthFollowUp.created_at.desc()).all()
    return {
        "health_event_id": str(event.id),
        "follow_ups": [
            {**dump(item), "milk_productivity_context": milk_productivity_context(db, event, item) if item.follow_up_status == "completed" else None}
            for item in follow_ups
        ],
    }


@app.post("/api/v1/health-events/{event_id}/follow-ups", status_code=201)
def create_health_follow_up(event_id: UUID, body: HealthFollowUpCreate, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    event = db.get(AnimalHealthEvent, event_id)
    if not event:
        raise HTTPException(404, "Health event not found")
    farm = farm_access(db, user, event.farm_id)
    require_role(db, user, "veterinarian")
    vet_membership = db.query(FarmMember).filter_by(farm_id=farm.id, user_id=user.id, role="veterinarian").first()
    if not vet_membership:
        raise HTTPException(403, "Only the veterinarian assigned to this farm can record clinical follow-up")
    if event.status != "open":
        raise HTTPException(409, "This health case is closed. Create a new health event if the animal needs care again.")
    if body.occurred_on < event.occurred_on:
        raise HTTPException(422, "Follow-up date cannot precede the health event")
    if body.occurred_on > farm_today():
        raise HTTPException(422, "A follow-up date cannot be in the future")
    previous = db.query(AnimalHealthFollowUp).filter_by(farm_id=farm.id, health_event_id=event.id).order_by(AnimalHealthFollowUp.occurred_on.desc(), AnimalHealthFollowUp.created_at.desc()).first()
    if previous and body.occurred_on < previous.occurred_on:
        raise HTTPException(422, "Follow-up records must be added in chronological order")
    if body.next_follow_up_on and body.next_follow_up_on <= body.occurred_on:
        raise HTTPException(422, "The next follow-up must be after this visit or contact")

    row = AnimalHealthFollowUp(
        farm_id=farm.id,
        health_event_id=event.id,
        recorded_by=user.id,
        recorded_by_name=user.display_name,
        follow_up_status=body.follow_up_status,
        occurred_on=body.occurred_on,
        clinical_outcome=body.clinical_outcome,
        case_disposition=body.case_disposition,
        treatment_adherence=body.treatment_adherence,
        care_plan_summary=body.care_plan_summary,
        next_follow_up_on=body.next_follow_up_on,
        case_cost_to_date_kes=body.case_cost_to_date_kes,
        case_cost_source="farmer_reported" if body.case_cost_to_date_kes is not None else "not_recorded",
        milk_price_kes_per_liter=body.milk_price_kes_per_liter,
        milk_price_source="farmer_reported" if body.milk_price_kes_per_liter is not None else "not_recorded",
        notes=body.notes,
    )
    db.add(row)
    if body.follow_up_status != "completed" or body.case_disposition in {"continue_follow_up", "referred"}:
        event.follow_up_on = body.next_follow_up_on
        event.status = "open"
    elif body.case_disposition == "closed_recovered":
        event.follow_up_on = None
        event.status = "resolved"
    elif body.case_disposition == "closed_other":
        event.follow_up_on = None
        event.status = "closed"
    db.flush()
    audit(db, user, "health_follow_up.recorded", "animal_health_follow_up", str(row.id), farm.id, {
        "follow_up_status": row.follow_up_status,
        "clinical_outcome": row.clinical_outcome,
        "case_disposition": row.case_disposition,
    })
    source_event = append_domain_event(
        db,
        farm_id=farm.id,
        actor=user,
        event_type="animal_health.follow_up_recorded",
        aggregate_type="animal_health_event",
        aggregate_id=event.id,
        idempotency_key=f"animal-health-follow-up:{row.id}:recorded",
        payload={
            "follow_up_id": str(row.id),
            "follow_up_status": row.follow_up_status,
            "case_disposition": row.case_disposition,
            "next_follow_up_on": event.follow_up_on.isoformat() if event.follow_up_on else None,
            "case_status": event.status,
        },
    )
    schedule_health_follow_up(
        db,
        farm_id=farm.id,
        health_event=event,
        source_event=source_event,
        due_on=event.follow_up_on if event.status == "open" else None,
    )
    db.commit()
    db.refresh(row)
    result = dump(row)
    result["milk_productivity_context"] = milk_productivity_context(db, event, row) if row.follow_up_status == "completed" else None
    return result


@app.post("/api/v1/animals/{animal_id}/health-events", status_code=201)
def create_health_event(animal_id: UUID, body: HealthEventCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    animal = db.get(Animal, animal_id)
    if not animal:
        raise HTTPException(404, "Animal not found")
    farm = farm_access(db, user, animal.farm_id)
    verified = False
    if body.verify_record:
        require_role(db, user, "veterinarian", "platform_admin")
        verified = True
    path = f"/api/v1/animals/{animal_id}/health-events"
    replay = replay_client_write(db, user, idempotency_key, path, body)
    if replay:
        return replay
    row = AnimalHealthEvent(farm_id=farm.id, animal_id=animal.id, created_by=user.id, verified_by=user.id if verified else None, event_type=body.event_type, occurred_on=body.occurred_on, summary=body.summary, observations=body.observations, follow_up_on=body.follow_up_on, status="open", verified=verified)
    db.add(row)
    db.flush()
    audit(db, user, "health_event.created", "animal_health_event", str(row.id), farm.id, {"verified": verified})
    source_event = append_domain_event(
        db,
        farm_id=farm.id,
        actor=user,
        event_type="animal_health_event.created",
        aggregate_type="animal_health_event",
        aggregate_id=row.id,
        idempotency_key=f"animal-health-event:{row.id}:created",
        payload={"event_type": row.event_type, "follow_up_on": row.follow_up_on.isoformat() if row.follow_up_on else None},
    )
    schedule_health_follow_up(
        db,
        farm_id=farm.id,
        health_event=row,
        source_event=source_event,
        due_on=row.follow_up_on,
    )
    response = dump(row)
    store_client_write_receipt(db, user, idempotency_key, path, body, response)
    db.commit()
    return response


@app.get("/api/v1/veterinary/queue")
def veterinary_queue(user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
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
def verify_health_event(event_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
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
def list_feed(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    return [dump(row) for row in db.query(FeedBatch).filter_by(farm_id=farm.id).order_by(FeedBatch.batch_date.desc()).all()]


@app.post("/api/v1/farms/{farm_id}/feed-batches", status_code=201)
def create_feed(farm_id: UUID, body: FeedBatchCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    path = f"/api/v1/farms/{farm_id}/feed-batches"
    replay = replay_client_write(db, user, idempotency_key, path, body)
    if replay:
        return replay
    data = body.model_dump()
    if data.get("plot_id"):
        plot = db.get(Plot, data["plot_id"])
        if not plot or plot.farm_id != farm.id:
            raise HTTPException(422, "Feed source plot must belong to this farm")
    row = FeedBatch(farm_id=farm.id, **data)
    db.add(row)
    db.flush()
    audit(db, user, "feed_batch.created", "feed_batch", str(row.id), farm.id)
    response = dump(row)
    store_client_write_receipt(db, user, idempotency_key, path, body, response)
    db.commit()
    return response


@app.post("/api/v1/farms/{farm_id}/feed-allocations", status_code=201)
def allocate_feed(farm_id: UUID, body: FeedAllocationCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    path = f"/api/v1/farms/{farm_id}/feed-allocations"
    replay = replay_client_write(db, user, idempotency_key, path, body)
    if replay:
        return replay
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
    response = dump(row)
    store_client_write_receipt(db, user, idempotency_key, path, body, response)
    db.commit()
    return response


@app.post("/api/v1/farms/{farm_id}/manure-records", status_code=201)
def create_manure(farm_id: UUID, body: ManureCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    path = f"/api/v1/farms/{farm_id}/manure-records"
    replay = replay_client_write(db, user, idempotency_key, path, body)
    if replay:
        return replay
    row = ManureRecord(farm_id=farm.id, **body.model_dump())
    db.add(row)
    db.flush()
    audit(db, user, "manure.created", "manure_record", str(row.id), farm.id)
    response = dump(row)
    store_client_write_receipt(db, user, idempotency_key, path, body, response)
    db.commit()
    return response


@app.post("/api/v1/farms/{farm_id}/compost-batches", status_code=201)
def create_compost(farm_id: UUID, body: CompostCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    path = f"/api/v1/farms/{farm_id}/compost-batches"
    replay = replay_client_write(db, user, idempotency_key, path, body)
    if replay:
        return replay
    data = body.model_dump()
    if data.get("manure_record_id"):
        manure = db.get(ManureRecord, data["manure_record_id"])
        if not manure or manure.farm_id != farm.id:
            raise HTTPException(422, "Manure record must belong to this farm")
    row = CompostBatch(farm_id=farm.id, **data)
    db.add(row)
    db.flush()
    audit(db, user, "compost.created", "compost_batch", str(row.id), farm.id)
    response = dump(row)
    store_client_write_receipt(db, user, idempotency_key, path, body, response)
    db.commit()
    return response


@app.post("/api/v1/farms/{farm_id}/compost-applications", status_code=201)
def apply_compost(farm_id: UUID, body: CompostApplicationCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    path = f"/api/v1/farms/{farm_id}/compost-applications"
    replay = replay_client_write(db, user, idempotency_key, path, body)
    if replay:
        return replay
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
    response = dump(row)
    store_client_write_receipt(db, user, idempotency_key, path, body, response)
    db.commit()
    return response


@app.get("/api/v1/farms/{farm_id}/resource-cycle")
def resource_cycle(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    return {"plots": [dump(row) for row in db.query(Plot).filter_by(farm_id=farm.id).all()], "feed_batches": [dump(row) for row in db.query(FeedBatch).filter_by(farm_id=farm.id).all()], "allocations": [dump(row) for row in db.query(FeedAllocation).filter_by(farm_id=farm.id).all()], "manure": [dump(row) for row in db.query(ManureRecord).filter_by(farm_id=farm.id).all()], "compost": [dump(row) for row in db.query(CompostBatch).filter_by(farm_id=farm.id).all()], "applications": [dump(row) for row in db.query(CompostApplication).filter_by(farm_id=farm.id).all()], "animals": farm_animals(db, farm.id), "note": "Recorded links only. No nutrient balances or agronomic recommendations are calculated."}


@app.get("/api/v1/farms/{farm_id}/production-records")
def list_production(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    return [dump(row) for row in db.query(ProductionRecord).filter_by(farm_id=farm.id).order_by(ProductionRecord.recorded_on.desc()).all()]


@app.post("/api/v1/farms/{farm_id}/production-records", status_code=201)
def create_production(farm_id: UUID, body: ProductionCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    path = f"/api/v1/farms/{farm_id}/production-records"
    replay = replay_client_write(db, user, idempotency_key, path, body)
    if replay:
        return replay
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
    response = dump(row)
    store_client_write_receipt(db, user, idempotency_key, path, body, response)
    db.commit()
    return response


@app.post("/api/v1/farms/{farm_id}/deliveries", status_code=201)
def create_delivery(farm_id: UUID, body: DeliveryCreate, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "platform_admin")
    path = f"/api/v1/farms/{farm_id}/deliveries"
    replay = replay_client_write(db, user, idempotency_key, path, body)
    if replay:
        return replay
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
    response = {"delivery": dump(delivery), "product_lot": dump(lot), "source_production": dump(record)}
    store_client_write_receipt(db, user, idempotency_key, path, body, response)
    db.commit()
    return response


@app.get("/api/v1/farms/{farm_id}/deliveries")
def list_deliveries(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    return [{**dump(row), "buyer": db.get(Buyer, row.buyer_id).name, "lot": dump(db.get(ProductLot, row.product_lot_id))} for row in db.query(Delivery).filter_by(farm_id=farm.id).order_by(Delivery.delivery_date.desc()).all()]


@app.post("/api/v1/farms/{farm_id}/consents", status_code=201)
def create_consent(farm_id: UUID, body: ConsentCreate, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
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
def revoke_consent(consent_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
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


def active_shared_farms(db: Session, user: User, organization_ids: list[UUID]) -> dict[str, SimpleNamespace]:
    grants = db.query(Consent).filter(
        Consent.status == "active",
        Consent.scope == "delivery_summary",
        or_(Consent.grantee_email == user.email.lower(), Consent.grantee_org_id.in_(organization_ids)),
        or_(Consent.expires_at.is_(None), Consent.expires_at > datetime.now(timezone.utc)),
    ).all()
    farm_ids = {grant.farm_id for grant in grants}
    if not farm_ids:
        return {}
    farms: dict[str, SimpleNamespace] = {}
    for farm_id in farm_ids:
        farm = shared_farm_card(db, farm_id)
        if farm:
            farms[farm.code.casefold()] = farm
    return farms


def shared_farm_card(db: Session, farm_id: UUID):
    """Return only farm identity fields covered by delivery-summary consent."""
    if db.get_bind().dialect.name == "postgresql":
        row = db.execute(
            text("SELECT id, name, code, is_synthetic FROM terravanta_private.shared_farm_card(:farm_id)"),
            {"farm_id": farm_id},
        ).mappings().first()
        return SimpleNamespace(**row) if row else None
    # SQLite is used for local tests and has no PostgreSQL RLS helper function.
    return db.get(Farm, farm_id)


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


def reconciliation_detail(db: Session, run: ReconciliationRun, shared_farms: dict[str, SimpleNamespace]) -> dict:
    shared_farm_ids = {farm.id for farm in shared_farms.values()}
    farms_by_id = {farm.id: farm for farm in shared_farms.values()}
    items = db.query(ReconciliationItem).filter_by(run_id=run.id).order_by(ReconciliationItem.row_number).all()
    output = []
    for item in items:
        has_consent = item.matched_farm_id in shared_farm_ids
        farm = farms_by_id.get(item.matched_farm_id) if has_consent else None
        delivery = db.get(Delivery, item.matched_delivery_id) if has_consent and item.matched_delivery_id else None
        lot = db.get(ProductLot, delivery.product_lot_id) if delivery else None
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
                {"id": f"production:{lot.production_record_id}", "type": "production_record", "label": "Source production record"},
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
    db: Session = Depends(get_scoped_db),
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
def list_reconciliation_runs(user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    organization_ids = cooperative_organization_ids(db, user)
    shared_farms = active_shared_farms(db, user, organization_ids)
    runs = db.query(ReconciliationRun).filter_by(organization_id=organization_ids[0]).order_by(
        ReconciliationRun.created_at.desc(),
    ).limit(25).all()
    return [reconciliation_summary(db, run, {farm.id for farm in shared_farms.values()}) for run in runs]


@app.get("/api/v1/cooperative/reconciliation/runs/{run_id}")
def get_reconciliation_run(run_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
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
    db: Session = Depends(get_scoped_db),
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
    db: Session = Depends(get_scoped_db),
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
def list_settlement_closes(user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    organization_ids = cooperative_organization_ids(db, user)
    closes = db.query(SettlementClose).filter_by(organization_id=organization_ids[0]).order_by(SettlementClose.created_at.desc()).limit(50).all()
    return [settlement_close_detail(db, close)["close"] for close in closes]


@app.get("/api/v1/cooperative/settlement-closes/{close_id}")
def get_settlement_close(close_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    organization_ids = cooperative_organization_ids(db, user)
    close = db.query(SettlementClose).filter_by(id=close_id, organization_id=organization_ids[0]).first()
    if not close:
        raise HTTPException(404, "Settlement close not found")
    return settlement_close_detail(db, close)


@app.post("/api/v1/cooperative/settlement-closes/{close_id}/items/{item_id}/review")
def review_settlement_item(
    close_id: UUID, item_id: UUID, body: SettlementReviewCreate,
    user: User = Depends(current_user), db: Session = Depends(get_scoped_db),
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
    user: User = Depends(current_user), db: Session = Depends(get_scoped_db),
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
def download_settlement_statement_pack(close_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
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
def cooperative_deliveries(user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
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
        farm = shared_farm_card(db, farm_id)
        if not farm:
            continue
        for row in db.query(Delivery).filter_by(farm_id=consent.farm_id).all():
            lot = db.get(ProductLot, row.product_lot_id)
            result.append({"farm_name": farm.name, "farm_code": farm.code, "delivery": dump(row), "product_type": lot.product_type, "lot_code": lot.lot_code, "scope": consent.scope, "synthetic": farm.is_synthetic, "documentation_gaps": [] if row.reference else ["Delivery reference is not recorded"]})
    return result


def build_alerts(db: Session, farm: Farm) -> list[dict]:
    today = farm_today()
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
def get_alerts(user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = primary_farm(db, user)
    return build_alerts(db, farm)


def farm_record_insights(db: Session, farm: Farm) -> dict:
    """Transparent, record-derived farm signals; never infer nutrient adequacy or treatment effect."""
    today = farm_today()
    window_start = today - timedelta(days=13)
    prior_start = window_start - timedelta(days=14)
    production = db.query(ProductionRecord).filter(
        ProductionRecord.farm_id == farm.id,
        ProductionRecord.recorded_on >= prior_start,
        ProductionRecord.recorded_on <= today,
    ).order_by(ProductionRecord.recorded_on.desc()).all()
    series: dict[tuple[str, str], dict[str, float]] = {}
    for item in production:
        key = (item.product_type.strip().lower(), item.unit.strip().lower())
        day_key = item.recorded_on.isoformat()
        series.setdefault(key, {})[day_key] = series.setdefault(key, {}).get(day_key, 0.0) + float(item.quantity)
    production_comparison = []
    for (product_type, unit), records in sorted(series.items()):
        current = [value for day, value in records.items() if window_start.isoformat() <= day <= today.isoformat()]
        prior = [value for day, value in records.items() if prior_start.isoformat() <= day < window_start.isoformat()]
        production_comparison.append({
            "product_type": product_type,
            "unit": unit,
            "current_window": {"from": window_start.isoformat(), "through": today.isoformat(), "days_recorded": len(current), "total": round(sum(current), 2)},
            "prior_window": {"from": prior_start.isoformat(), "through": (window_start - timedelta(days=1)).isoformat(), "days_recorded": len(prior), "total": round(sum(prior), 2)},
            "change_total": round(sum(current) - sum(prior), 2) if prior else None,
            "comparison_note": "Totals compare records in equal 14-day windows; missing days are not treated as zero production." if prior else "A prior 14-day baseline is not available.",
        })

    plots = db.query(Plot).filter_by(farm_id=farm.id).all()
    feed_batches = db.query(FeedBatch).filter_by(farm_id=farm.id).all()
    allocations = db.query(FeedAllocation).filter(
        FeedAllocation.farm_id == farm.id,
        FeedAllocation.allocated_on >= today - timedelta(days=29),
        FeedAllocation.allocated_on <= today,
    ).all()
    animals = db.query(Animal).filter_by(farm_id=farm.id).all()
    animals_with_feed_records = db.query(func.count(func.distinct(FeedAllocation.animal_id))).filter(
        FeedAllocation.farm_id == farm.id,
        FeedAllocation.allocated_on >= today - timedelta(days=29),
        FeedAllocation.allocated_on <= today,
    ).scalar() or 0
    open_cases = db.query(AnimalHealthEvent).filter_by(farm_id=farm.id, status="open").count()
    followups = db.query(AnimalHealthFollowUp).filter(
        AnimalHealthFollowUp.farm_id == farm.id,
        AnimalHealthFollowUp.occurred_on >= today - timedelta(days=89),
        AnimalHealthFollowUp.occurred_on <= today,
    ).all()
    deliveries = db.query(Delivery).filter_by(farm_id=farm.id).all()
    traceable_delivery_count = db.query(Delivery.id).join(
        ProductLot, ProductLot.id == Delivery.product_lot_id,
    ).join(
        ProductionRecord, ProductionRecord.id == ProductLot.production_record_id,
    ).filter(Delivery.farm_id == farm.id, ProductLot.farm_id == farm.id).count()
    active_shares = db.query(Consent).filter(
        Consent.farm_id == farm.id,
        Consent.status == "active",
        or_(Consent.expires_at.is_(None), Consent.expires_at > datetime.now(timezone.utc)),
    ).count()
    plot_map = {plot.id: plot for plot in plots}
    recent_plot_records = db.query(ProductionRecord).filter(
        ProductionRecord.farm_id == farm.id,
        ProductionRecord.plot_id.in_(list(plot_map)) if plot_map else ProductionRecord.plot_id.is_(None),
        ProductionRecord.recorded_on >= today - timedelta(days=89),
        ProductionRecord.recorded_on <= today,
    ).all() if plot_map else []
    plot_totals: dict[tuple[object, str, str], float] = {}
    for item in recent_plot_records:
        key = (item.plot_id, item.product_type, item.unit)
        plot_totals[key] = plot_totals.get(key, 0.0) + float(item.quantity)

    data_gaps = []
    actions = []
    if not any(item["current_window"]["days_recorded"] > 0 for item in production_comparison):
        data_gaps.append("No production entries appear in the current 14-day window.")
    if not plots:
        data_gaps.append("No crop plots are registered, so crop output cannot be compared by plot.")
    elif any(item.product_type.strip().lower() != "milk" for item in production) and not any(item.plot_id for item in production if item.product_type.strip().lower() != "milk"):
        data_gaps.append("Recent crop production is not linked to plots.")
    if not feed_batches:
        data_gaps.append("No feed batches are recorded; feed stock and use cannot be summarized.")
    if followups:
        completed = sum(item.follow_up_status == "completed" for item in followups)
        actions.append({"priority": "review", "title": "Review veterinary follow-up completion", "detail": f"{completed} of {len(followups)} recorded follow-ups in the last 90 days are marked completed. This is a workflow count, not a health outcome measure.", "destination": "veterinary"})
    if any(batch.aflatoxin_status == "pending_test" for batch in feed_batches):
        actions.append({"priority": "review", "title": "Close pending feed test records", "detail": "At least one batch is marked pending test. Record the laboratory result when received; no feed-safety status is inferred.", "destination": "feed"})
    if not deliveries:
        actions.append({"priority": "next_step", "title": "Connect production to traceability", "detail": "No deliveries are recorded. Link a delivery to its source production record when one occurs.", "destination": "traceability"})

    return {
        "period": {"through": today.isoformat(), "timezone": "Africa/Nairobi"},
        "record_counts": {
            "animals": len(animals),
            "open_veterinary_cases": open_cases,
            "plots": len(plots),
            "fodder_plots": sum(plot.is_feed_crop for plot in plots),
            "feed_batches": len(feed_batches),
            "feed_stock_kg_recorded": round(sum(max(0, batch.quantity_kg) for batch in feed_batches), 2),
            "feed_allocated_kg_last_30_days": round(sum(item.allocated_kg for item in allocations), 2),
            "animals_with_feed_records_last_30_days": animals_with_feed_records,
            "follow_ups_last_90_days": len(followups),
            "follow_ups_completed_last_90_days": sum(item.follow_up_status == "completed" for item in followups),
            "deliveries": len(deliveries),
            "source_linked_deliveries": traceable_delivery_count,
            "active_sharing_consents": active_shares,
        },
        "production_comparison": production_comparison,
        "plot_production_last_90_days": [
            {"plot_name": plot_map[plot_id].name, "crop_type": plot_map[plot_id].crop_type, "product_type": product_type, "quantity": round(quantity, 2), "unit": unit}
            for (plot_id, product_type, unit), quantity in sorted(plot_totals.items(), key=lambda entry: (plot_map[entry[0][0]].name.lower(), entry[0][1], entry[0][2]))
            if plot_id in plot_map
        ],
        "crop_mix": [{"crop_type": plot.crop_type, "area_acres": plot.area_acres, "is_feed_crop": plot.is_feed_crop} for plot in plots],
        "feed_stock": [{"batch_name": batch.name, "ingredients": batch.ingredients, "quantity_kg_recorded": batch.quantity_kg, "test_status": batch.aflatoxin_status, "batch_date": batch.batch_date.isoformat()} for batch in feed_batches],
        "data_gaps": data_gaps,
        "review_actions": actions,
        "interpretation_limits": [
            "These are descriptions of records, not verified farm performance or causal effects.",
            "Feed quantity is not a ration or nutritional adequacy assessment.",
            "No clinical diagnosis, treatment, food-safety status, or financial return is inferred.",
        ],
    }


@app.get("/api/v1/farms/{farm_id}/insights")
def get_farm_insights(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "veterinarian", "platform_admin")
    return farm_record_insights(db, farm)


def external_farm_summary(facts: dict) -> dict:
    """Allowlisted and aggregated fields for a user-approved external model request."""
    plot_totals: dict[tuple[str, str, str], float] = {}
    for item in facts["plot_production_last_90_days"]:
        key = (item["crop_type"], item["product_type"], item["unit"])
        plot_totals[key] = plot_totals.get(key, 0.0) + float(item["quantity"])
    crop_mix: dict[str, float] = {}
    for item in facts["crop_mix"]:
        crop_mix[item["crop_type"]] = crop_mix.get(item["crop_type"], 0.0) + float(item["area_acres"])
    return {
        "record_counts": facts["record_counts"],
        "production_comparison": facts["production_comparison"],
        "crop_area_by_type_acres": [{"crop_type": crop, "area_acres": round(area, 2)} for crop, area in sorted(crop_mix.items())],
        "plot_production_grouped_by_crop_last_90_days": [
            {"crop_type": crop, "product_type": product, "quantity": round(quantity, 2), "unit": unit}
            for (crop, product, unit), quantity in sorted(plot_totals.items())
        ],
        "feed_stock": [
            {"ingredients": item["ingredients"], "quantity_kg_recorded": item["quantity_kg_recorded"], "test_status": item["test_status"]}
            for item in facts["feed_stock"]
        ],
        "data_gaps": facts["data_gaps"],
        "review_actions": facts["review_actions"],
    }


@app.get("/api/v1/ai/provider-status")
def ai_provider_status(user: User = Depends(current_user)):
    """Report server-side provider configuration without revealing credentials or endpoints."""
    chat_configured = bool(settings.nvidia_api_key.strip() and settings.nvidia_base_url.strip() and settings.nvidia_chat_model.strip())
    parse_configured = bool(settings.nvidia_parse_url.strip() and (settings.nvidia_parse_api_key.strip() or settings.nvidia_api_key.strip()))
    return {
        "chat": {
            "provider": "NVIDIA NIM",
            "configured": chat_configured,
            "model": settings.nvidia_chat_model,
        },
        "image_parse": {
            "provider": "Nemotron Parse",
            "configured": parse_configured,
            "model": settings.nvidia_parse_model,
            "requires": ["NVIDIA_API_KEY"],
        },
        "structured_document_fields": {
            "configured": parse_configured and bool(settings.nvidia_api_key.strip()),
            "requires": ["NVIDIA_API_KEY"],
        },
        "selectable_pdf_text": {"configured": True, "provider": "local extraction"},
        "connectivity_checked": False,
    }


@app.post("/api/v1/farms/{farm_id}/ai-assistant")
async def farm_assistant(farm_id: UUID, body: FarmAssistantRequest, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    require_role(db, user, "farmer", "veterinarian", "platform_admin")
    enforce_ai_rate_limit(db, user)
    facts = farm_record_insights(db, farm)
    terms = set(re.findall(r"[a-z]{4,}", body.question.lower()))
    approved_sources = db.query(KnowledgeSource).filter_by(approved=True).all()
    retrieved = [source for source in approved_sources if terms.intersection(set(re.findall(r"[a-z]{4,}", (source.title + " " + source.content).lower())))][:4]
    sources = [{"id": str(source.id), "title": source.title, "url": source.source_url, "publisher": source.publisher} for source in retrieved]
    request = AIRequest(user_id=user.id, farm_id=farm.id, request_type="farm_assistant", model_name=settings.nvidia_chat_model, prompt_version="farm_v1")
    db.add(request)
    db.flush()
    response = {
        "request_id": str(request.id), "status": "unavailable", "answer": "", "model_generated": False,
        "facts": facts, "sources": sources,
        "safety_note": "Decision-support draft only. A qualified veterinarian or agricultural adviser must review advice before clinical, feed-safety, pesticide, fertilizer, or other high-impact action.",
        "privacy_note": "The model receives an allowlisted farm-record summary only after you enable external processing. Account names, emails, farm coordinates, animal names and tags are excluded from that summary; crop/feed labels and aggregate quantities may be sent. Your question is sent as written, so omit personal and contact details.",
    }
    if not body.allow_external_processing:
        response.update({"status": "consent_required", "answer": "No external model request was made. Enable external processing to send this aggregate farm snapshot and question to NVIDIA."})
        request.outcome = "consent_required"
    elif not settings.nvidia_api_key:
        response.update({"status": "provider_unconfigured", "answer": "NVIDIA is not configured. The record-based indicators remain available; no AI answer was generated."})
        request.outcome = "provider_unconfigured"
    else:
        # Exclude direct personal identifiers and fine-grained farm location from external model context.
        context = {
            "record_snapshot": external_farm_summary(facts),
            "approved_references": [{"id": str(source.id), "title": source.title, "publisher": source.publisher, "content": source.content[:1800]} for source in retrieved],
        }
        prompt = (
            "You are Terravanta's farm-record decision-support assistant. Use only the supplied record snapshot and approved references. "
            "Separate observed record facts from suggestions. Cite source IDs for domain-specific advice; do not invent sources. "
            "Do not diagnose, prescribe, calculate animal treatment doses, certify feed or food safety, give exact ration formulations, "
            "or prescribe pesticide/fertilizer rates. If no applicable approved source is supplied, limit the answer to describing records, "
            "uncertainty, and the additional information a qualified professional should review. Never claim causal productivity gains or ROI. "
            "Return a concise review draft, not an instruction that executes a farm action.\n\nCONTEXT: "
            + json.dumps(context, ensure_ascii=False) + "\nQUESTION: " + body.question
        )
        started = time.perf_counter()
        try:
            answer, latency = await nvidia.chat([{"role": "user", "content": prompt}])
            if not safe_farm_response(answer):
                answer = "The draft was withheld because it may contain a clinical or treatment instruction. Review the recorded indicators with a qualified veterinarian or agricultural adviser."
                request.outcome = "safety_filtered"
            else:
                request.outcome = "success"
            request.latency_ms = latency
            response.update({"status": request.outcome, "answer": answer, "model_generated": request.outcome == "success", "model": settings.nvidia_chat_model})
        except Exception as exc:
            log.warning("NVIDIA farm assistant failed (%s)", type(exc).__name__)
            request.outcome = "provider_error"
            request.latency_ms = round((time.perf_counter() - started) * 1000)
            response.update({"status": "unavailable", "answer": "The NVIDIA service is unavailable or rejected this request. No AI answer was generated; the record indicators remain available."})
    db.add(AIResponse(request_id=request.id, content=response["answer"], structured_output={"status": response["status"], "farm_facts": facts}, sources=sources))
    audit(db, user, "ai.farm_assistant", "ai_request", str(request.id), farm.id, {"status": response["status"], "model": settings.nvidia_chat_model})
    db.commit()
    return response


@app.post("/api/v1/terras/route")
def terras_route(body: TerrasRouteRequest, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    """Role-scoped, deterministic routing. This endpoint never writes farm data or calls a model."""
    role = user_role(db, user)
    message = body.message.lower()
    allowed_sections = {
        "farmer": ["overview", "farms", "veterinary", "crops", "feed", "production", "traceability", "assistant", "reports", "settings"],
        "veterinarian": ["overview", "veterinary", "assistant", "settings"],
        "cooperative_admin": ["overview", "settlements", "traceability", "reports", "settings"],
        "platform_admin": ["overview", "farms", "veterinary", "crops", "feed", "production", "traceability", "assistant", "settlements", "reports", "settings"],
    }.get(role)
    if not allowed_sections:
        raise HTTPException(403, "Terras is unavailable until an authorized workspace role is assigned")

    def routed(section: str, intent: str, reply: str, api_workflow: str | None = None, draft: dict | None = None, required_inputs: list[str] | None = None):
        if section not in allowed_sections:
            section = "overview"
            intent = "role_limited"
            reply = "That workflow is not available to your workspace role. I can help you find records and tasks your role is allowed to access."
            api_workflow = None
            draft = None
            required_inputs = []
        return {
            "reply": reply,
            "mode": "local_rules",
            "intent": intent,
            "destination": section,
            "api_workflow": api_workflow,
            "draft": draft,
            "required_inputs": required_inputs or [],
            "requires_confirmation": bool(draft or (api_workflow and api_workflow.startswith("POST "))),
            "external_model_used": False,
            "safety_note": "Terras can prepare a draft or open an existing workflow. Existing API permissions still apply, and a person must review and submit every change.",
        }

    payout_terms = ("payout", "settlement", "reconcile", "close period", "close the period", "member close")
    production_terms = ("milk", "production", "harvest")
    if role != "cooperative_admin" and any(term in message for term in payout_terms):
        return routed("overview", "role_limited", "Payout close is restricted to authorized cooperative members. I can route you to the records and tasks available in your workspace.")
    if role not in {"farmer", "platform_admin"} and any(term in message for term in production_terms):
        return routed("overview", "role_limited", "Production records can be entered by the farm owner or an authorized platform administrator. I can route you to casework available in your workspace.")

    if role == "cooperative_admin":
        if any(term in message for term in payout_terms):
            cooperative_organization_ids(db, user)  # Enforce cooperative membership before surfacing the workflow.
            return routed(
                "settlements", "payout_close",
                "Open Payout settlements to reconcile the collection, processor settlement, and payout exports. Terravanta checks their recorded arithmetic; your reviewer resolves exceptions and a cooperative approver signs off. It does not send payments.",
                "POST /api/v1/cooperative/settlement-closes",
                required_inputs=["Collection CSV", "Processor settlement CSV", "Farmer payout CSV", "Close period"],
            )
        if any(term in message for term in ("delivery", "shared member", "consent", "farmer records")):
            cooperative_organization_ids(db, user)
            return routed("traceability", "consented_member_records", "Open Shared member records to review only records farmers have actively shared with your cooperative.", "GET /api/v1/cooperative/deliveries")
        if "history" in message or "archive" in message:
            cooperative_organization_ids(db, user)
            return routed("reports", "close_history", "Open Close history to review previous payout periods, exception counts, and approval notes.", "GET /api/v1/cooperative/settlement-closes")
        return routed("overview", "cooperative_navigation", "I can take you to payout close, close history, or consented member delivery records. Try asking about a payout close or shared deliveries.")

    if role == "farmer" and any(term in message for term in ("call a vet", "contact a vet", "request a vet", "vet visit", "talk to a vet")):
        farm = primary_farm(db, user)
        return routed(
            "veterinary", "request_veterinarian_contact",
            "Open Veterinary and send a contact request to the veterinarians assigned to this farm. Terravanta records and notifies the request; it does not place a phone call or send a WhatsApp message yet. For an emergency, contact local veterinary help directly.",
            f"POST /api/v1/farms/{farm.id}/veterinary-contact-requests",
            required_inputs=["Optional animal", "Urgency", "What you observed", "Preferred contact method"],
        )

    if role in {"farmer", "platform_admin"} and any(term in message for term in ("milk", "production", "harvest")):
        farm = primary_farm(db, user)
        milk_quantity = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:litres?|liters?|l)\b", message)
        if "milk" in message and milk_quantity:
            quantity = float(milk_quantity.group(1))
            if quantity <= 0:
                return routed("production", "record_milk", "Enter a quantity greater than zero liters and I can prepare the draft.", required_inputs=["Quantity in liters"])
            draft = {"product_type": "milk", "quantity": quantity, "unit": "liters"}
            return routed(
                "production", "record_milk",
                f"I prepared a {quantity:g}-liter milk production draft for {farm.name}. Set the correct record date, review it, then choose Review and save to create the record.",
                f"POST /api/v1/farms/{farm.id}/production-records", draft,
            )
        if "milk" in message:
            return routed("production", "record_milk", "How many liters of milk should I prepare a draft for? You can set the record date before saving.", required_inputs=["Quantity in liters", "Record date"])
        return routed("production", "record_production", "Open Production to record milk, crop harvest, or another product. Tell me a quantity and unit if you want me to prepare a draft.", f"POST /api/v1/farms/{farm.id}/production-records", required_inputs=["Product type", "Quantity", "Unit", "Record date"])

    if any(term in message for term in ("animal", "vet", "veterinary", "case", "clinical")):
        return routed("veterinary", "veterinary_records", "Open Veterinary to review the animal or assigned case history. Terras does not diagnose, prescribe, or verify a clinical record.", "GET /api/v1/veterinary/queue" if role == "veterinarian" else None)
    if any(term in message for term in ("feed", "fodder", "ration", "nutrition")):
        return routed("feed", "feed_records", "Open Feed & nutrition to review feed batches, allocations, and recorded stock.")
    if any(term in message for term in ("plot", "crop", "compost", "soil")):
        return routed("crops", "crop_records", "Open Crops & plots to review crop seasons, plots, and the recorded compost links.")
    if any(term in message for term in ("delivery", "buyer", "traceability", "share", "consent")):
        return routed("traceability", "traceability", "Open Traceability to review product lots, deliveries, and consent-controlled sharing.")
    return routed("overview", "navigation_help", "Tell me the outcome you need—such as a payout close, milk record, feed allocation, veterinary case, or delivery—and I’ll route you to the existing Terravanta workflow.")


@app.post("/api/v1/ai/veterinary-assistant")
async def veterinary_assistant(body: AssistantRequest, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
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
async def extract_document(farm_id: UUID, file: UploadFile = File(...), allow_external_processing: bool = Form(False), user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
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
def review_document(document_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
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
def shareable_records(farm_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_scoped_db)):
    farm = farm_access(db, user, farm_id)
    return {"farm": {"code": farm.code, "name": farm.name, "county": farm.county, "verification_status": farm.verification_status}, "deliveries": [dump(row) for row in db.query(Delivery).filter_by(farm_id=farm.id).all()], "scope": "delivery_summary", "synthetic": farm.is_synthetic}
