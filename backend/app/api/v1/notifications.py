from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.notification import Notification
from app.models.user import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: int
    demand_id: Optional[int]
    type: str
    message: str
    read: bool
    responded: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class ChatMentionOut(BaseModel):
    notification_id: int
    demand_id: int
    demand_subject: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=List[NotificationOut])
def list_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.query(Notification).filter(Notification.user_id == user.id, Notification.read.is_(False)).count()
    return {"count": n}


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.query(Notification).filter(Notification.user_id == user.id, Notification.read.is_(False)).update({"read": True})
    db.commit()
    return {"ok": True}


@router.patch("/{notif_id}/read")
def mark_read(notif_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.query(Notification).filter(Notification.id == notif_id, Notification.user_id == user.id).first()
    if n:
        n.read = True
        db.commit()
    return {"ok": True}


@router.get("/pending-mentions", response_model=List[int])
def pending_mentions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Retorna demand_ids onde o usuário tem @menções não respondidas."""
    rows = (
        db.query(Notification.demand_id)
        .filter(
            Notification.user_id == user.id,
            Notification.type == "COMMENT_MENTION",
            Notification.responded.is_(False),
            Notification.demand_id.isnot(None),
        )
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


@router.get("/chat", response_model=List[ChatMentionOut])
def chat_mentions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Retorna menções pendentes com contexto da demanda para o painel de chat."""
    from app.models.demand import Demand
    rows = (
        db.query(Notification, Demand.subject, Demand.sender_email)
        .join(Demand, Demand.id == Notification.demand_id)
        .filter(
            Notification.user_id == user.id,
            Notification.type == "COMMENT_MENTION",
            Notification.responded.is_(False),
            Notification.demand_id.isnot(None),
        )
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        ChatMentionOut(
            notification_id=n.id,
            demand_id=n.demand_id,
            demand_subject=subject or email or "(sem assunto)",
            message=n.message,
            created_at=n.created_at,
        )
        for n, subject, email in rows
    ]
