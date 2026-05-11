from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: int
    demand_id: Optional[int] = None
    user_id: Optional[int] = None
    event_type: str
    description: Optional[str] = None
    metadata_json: Optional[Any] = None
    created_at: datetime

    class Config:
        from_attributes = True
