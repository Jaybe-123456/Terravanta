"""Append farm-domain facts and schedule deterministic follow-up work."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from .models import AnimalHealthEvent, FarmDomainEvent, User, WorkflowRun

FARM_TIMEZONE = ZoneInfo("Africa/Nairobi")
WORKFLOW_TYPE = "health_follow_up_reminders_v1"


def append_domain_event(
    db: Session,
    *,
    farm_id,
    actor: User,
    event_type: str,
    aggregate_type: str,
    aggregate_id,
    idempotency_key: str,
    payload: dict,
) -> FarmDomainEvent:
    event = FarmDomainEvent(
        farm_id=farm_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        actor_user_id=actor.id,
        idempotency_key=idempotency_key,
        payload=payload,
    )
    db.add(event)
    db.flush()
    return event


def _scheduled_at(local_day: date) -> datetime:
    return datetime.combine(local_day, time(hour=8), tzinfo=FARM_TIMEZONE).astimezone(timezone.utc)


def schedule_health_follow_up(
    db: Session,
    *,
    farm_id,
    health_event: AnimalHealthEvent,
    source_event: FarmDomainEvent,
    due_on: date | None,
) -> None:
    if due_on is None:
        return

    today = datetime.now(FARM_TIMEZONE).date()
    schedule = [("upcoming", due_on - timedelta(days=2)), ("due", due_on), ("overdue", due_on + timedelta(days=1))]
    for step, local_day in schedule:
        # Avoid replaying every missed stage when an old case is first imported.
        if step == "upcoming" and local_day < today:
            continue
        if step == "due" and due_on < today:
            continue
        scheduled_at = _scheduled_at(max(local_day, today))
        db.add(WorkflowRun(
            farm_id=farm_id,
            event_id=source_event.id,
            workflow_type=WORKFLOW_TYPE,
            step=step,
            aggregate_id=health_event.id,
            due_on=due_on,
            scheduled_at=scheduled_at,
            status="pending",
            idempotency_key=f"{WORKFLOW_TYPE}:{health_event.id}:{source_event.id}:{due_on.isoformat()}:{step}",
        ))
