"""Poll the durable workflow queue. No model call or clinical write occurs here."""
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import text

from .config import settings
from .db import SessionLocal
from .models import Animal, AnimalHealthEvent, FarmMember, Notification, WorkflowRun

log = logging.getLogger("terravanta.workflow_worker")


def process_due_workflows_once(limit: int = 100) -> int:
    with SessionLocal() as db:
        if db.get_bind().dialect.name == "postgresql":
            processed = db.execute(
                text("SELECT terravanta_private.process_due_followup_workflows(:limit)"),
                {"limit": max(1, min(limit, 500))},
            ).scalar_one()
            db.commit()
            return int(processed)

        now = datetime.now(timezone.utc)
        runs = db.query(WorkflowRun).filter(
            WorkflowRun.status == "pending",
            WorkflowRun.scheduled_at <= now,
        ).order_by(WorkflowRun.scheduled_at, WorkflowRun.created_at).limit(max(1, min(limit, 500))).all()
        processed = 0
        for run in runs:
            case = db.query(AnimalHealthEvent).filter_by(id=run.aggregate_id, farm_id=run.farm_id).first()
            animal = db.get(Animal, case.animal_id) if case else None
            if not case or not animal or case.status != "open" or case.follow_up_on != run.due_on:
                run.status = "cancelled"
                run.attempts += 1
                run.completed_at = now
                processed += 1
                continue

            recipients = db.query(FarmMember).filter(
                FarmMember.farm_id == run.farm_id,
                FarmMember.role.in_(("owner", "farmer", "veterinarian")),
            ).all()
            title = {
                "upcoming": "Veterinary follow-up coming up",
                "due": "Veterinary follow-up due today",
                "overdue": "Veterinary follow-up is overdue",
            }[run.step]
            severity = {"upcoming": "info", "due": "medium", "overdue": "high"}[run.step]
            for recipient in recipients:
                key = f"{run.idempotency_key}:{recipient.user_id}"
                exists = db.query(Notification.id).filter_by(idempotency_key=key).first()
                if exists:
                    continue
                db.add(Notification(
                    farm_id=run.farm_id,
                    event_id=run.event_id,
                    recipient_user_id=recipient.user_id,
                    notification_type=f"veterinary_follow_up_{run.step}",
                    title=title,
                    body=f"Follow-up for animal {animal.tag} is scheduled for {run.due_on.isoformat()}.",
                    severity=severity,
                    action_section="veterinary",
                    idempotency_key=key,
                ))
            run.status = "completed"
            run.attempts += 1
            run.completed_at = now
            processed += 1
        db.commit()
        return processed


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if settings.service_mode != "worker":
        raise RuntimeError("Set SERVICE_MODE=worker before starting the workflow worker")
    interval = max(5, min(settings.workflow_poll_seconds, 300))
    log.info("Workflow worker started; poll interval=%ss", interval)
    while True:
        try:
            count = process_due_workflows_once()
            if count:
                log.info("Processed %s scheduled workflow step(s)", count)
        except Exception:
            log.exception("Workflow poll failed; queued work remains available for retry")
        time.sleep(interval)


if __name__ == "__main__":
    main()
