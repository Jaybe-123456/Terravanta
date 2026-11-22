"""Poll the durable workflow queue. No model call or clinical write occurs here."""
import argparse
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import text

from .config import settings
from .db import SessionLocal, WhatsAppWorkerSessionLocal
from .models import Animal, AnimalHealthEvent, FarmMember, Notification, WorkflowRun
from .whatsapp import WhatsAppSendError, send_whatsapp_message

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


def process_whatsapp_outbox_once(limit: int = 5) -> int:
    """Claim and deliver queued WhatsApp messages only when Meta sending is explicitly enabled."""
    if not settings.whatsapp_delivery_configured:
        return 0
    with WhatsAppWorkerSessionLocal() as db:
        if db.get_bind().dialect.name != "postgresql":
            return 0
        rows = db.execute(
            text("SELECT * FROM terravanta_private.claim_whatsapp_deliveries(:limit)"),
            {"limit": max(1, min(limit, 200))},
        ).mappings().all()
        db.commit()

    processed = 0
    for row in rows:
        try:
            with WhatsAppWorkerSessionLocal() as db:
                authorized = db.execute(
                    text("SELECT terravanta_private.authorize_whatsapp_delivery(:delivery_id)"),
                    {"delivery_id": row["outbox_id"]},
                ).scalar_one()
                db.commit()
            if not authorized:
                processed += 1
                continue
            result = send_whatsapp_message(
                to_phone=row["destination_phone"],
                body=row["message_body"],
                conversation_code=row["conversation_code"],
                in_service_window=bool(row["in_service_window"]),
            )
            with WhatsAppWorkerSessionLocal() as db:
                db.execute(text("""
                    SELECT terravanta_private.finish_whatsapp_delivery(
                        :delivery_id, 'sent', :provider_message_id, '', false
                    )
                """), {"delivery_id": row["outbox_id"], "provider_message_id": result.provider_message_id})
                db.commit()
        except WhatsAppSendError as exc:
            safe_code = exc.safe_code
            result_status = "blocked" if exc.blocked else "failed"
            with WhatsAppWorkerSessionLocal() as db:
                db.execute(text("""
                    SELECT terravanta_private.finish_whatsapp_delivery(
                        :delivery_id, :result, NULL, :error_code, :retryable
                    )
                """), {
                    "delivery_id": row["outbox_id"],
                    "result": result_status,
                    "error_code": safe_code,
                    "retryable": exc.retryable,
                })
                db.commit()
            log.warning("WhatsApp delivery %s ended with %s", row["outbox_id"], safe_code)
        except Exception as exc:
            log.error("WhatsApp delivery %s failed before completion (%s)", row["outbox_id"], type(exc).__name__)
            with WhatsAppWorkerSessionLocal() as db:
                db.execute(text("""
                    SELECT terravanta_private.finish_whatsapp_delivery(
                        :delivery_id, 'failed', NULL, 'worker_internal_error', true
                    )
                """), {"delivery_id": row["outbox_id"]})
                db.commit()
        processed += 1
    return processed


def maintain_whatsapp_retention_once() -> int:
    """Scrub message bodies at 90 days and expire pairing/webhook dedupe data."""
    if not settings.whatsapp_worker_database_url:
        return 0
    with WhatsAppWorkerSessionLocal() as db:
        if db.get_bind().dialect.name != "postgresql":
            return 0
        count = db.execute(
            text("SELECT terravanta_private.maintain_whatsapp_retention()"),
        ).scalar_one()
        db.commit()
        return int(count)


def run_once() -> tuple[int, int]:
    """Run one bounded pass for metered cron environments without free workers."""
    workflows = process_due_workflows_once()
    whatsapp = process_whatsapp_outbox_once()
    log.info("One-shot worker completed: workflows=%s whatsapp=%s", workflows, whatsapp)
    return workflows, whatsapp


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if settings.service_mode != "worker":
        raise RuntimeError("Set SERVICE_MODE=worker before starting the workflow worker")
    parser = argparse.ArgumentParser(description="Process Terravanta workflow and WhatsApp queues")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process one bounded batch and exit; suitable for a metered scheduled job",
    )
    args = parser.parse_args(argv)
    if args.once:
        run_once()
        return

    interval = max(5, min(settings.workflow_poll_seconds, 300))
    last_retention_maintenance = 0.0
    log.info("Workflow worker started; poll interval=%ss", interval)
    while True:
        try:
            count = process_due_workflows_once()
            if count:
                log.info("Processed %s scheduled workflow step(s)", count)
            delivered = process_whatsapp_outbox_once()
            if delivered:
                log.info("Handled %s WhatsApp outbox item(s)", delivered)
            if time.time() - last_retention_maintenance >= 86_400:
                pruned = maintain_whatsapp_retention_once()
                last_retention_maintenance = time.time()
                if pruned:
                    log.info("Applied WhatsApp retention maintenance to %s row(s)", pruned)
        except Exception as exc:
            log.error("Workflow poll failed; queued work remains available for retry (%s)", type(exc).__name__)
        time.sleep(interval)


if __name__ == "__main__":
    main()
