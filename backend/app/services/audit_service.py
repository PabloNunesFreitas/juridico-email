from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def log_event(
    db: Session,
    *,
    event_type: str,
    description: str = "",
    user_id: Optional[int] = None,
    demand_id: Optional[int] = None,
    metadata: Optional[dict[str, Any]] = None,
    commit: bool = True,
) -> AuditLog:
    entry = AuditLog(
        event_type=event_type,
        description=description,
        user_id=user_id,
        demand_id=demand_id,
        metadata_json=metadata,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    return entry
