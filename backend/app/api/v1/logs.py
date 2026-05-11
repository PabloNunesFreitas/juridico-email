from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.log import AuditLogOut

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("", response_model=List[AuditLogOut])
def list_logs(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    event_type: Optional[str] = None,
    demand_id: Optional[int] = None,
    limit: int = 200,
):
    q = db.query(AuditLog)
    if event_type:
        q = q.filter(AuditLog.event_type == event_type)
    if demand_id is not None:
        q = q.filter(AuditLog.demand_id == demand_id)
    return q.order_by(AuditLog.created_at.desc()).limit(limit).all()
