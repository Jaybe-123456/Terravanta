from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .models import Notification, User
from .security import current_user, get_scoped_db

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


def _serialize(item: Notification) -> dict:
    return {
        "id": str(item.id),
        "farm_id": str(item.farm_id),
        "event_id": str(item.event_id),
        "type": item.notification_type,
        "title": item.title,
        "body": item.body,
        "severity": item.severity,
        "action_section": item.action_section,
        "created_at": item.created_at.isoformat(),
        "read_at": item.read_at.isoformat() if item.read_at else None,
    }


@router.get("")
def list_notifications(
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    user: User = Depends(current_user),
    db: Session = Depends(get_scoped_db),
):
    query = db.query(Notification).filter(Notification.recipient_user_id == user.id)
    unread_count = query.filter(Notification.read_at.is_(None)).count()
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))
    items = query.order_by(Notification.created_at.desc()).limit(limit).all()
    return {"items": [_serialize(item) for item in items], "unread_count": unread_count}


@router.patch("/{notification_id}/read")
def mark_notification_read(
    notification_id: UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_scoped_db),
):
    item = db.query(Notification).filter_by(id=notification_id, recipient_user_id=user.id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if item.read_at is None:
        item.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(item)
    return _serialize(item)
