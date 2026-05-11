from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict

from app.models.demand import DemandStatus, Bank


class DemandUpdate(BaseModel):
    client_name: Optional[str] = None
    nup: Optional[str] = None
    bank: Optional[Bank] = None
    status: Optional[DemandStatus] = None


class ReplyIn(BaseModel):
    body_text: str


class AssignIn(BaseModel):
    user_id: int


class StatusIn(BaseModel):
    status: DemandStatus


class MessageOut(BaseModel):
    id: int
    direction: str
    sender_email: str
    sender_name: Optional[str] = None
    subject: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    received_at: datetime
    has_attachments: bool

    class Config:
        from_attributes = True


class UserMini(BaseModel):
    id: int
    name: str
    email: str

    class Config:
        from_attributes = True


class InboxAccountMini(BaseModel):
    id: int
    email_address: str
    color: str

    class Config:
        from_attributes = True


class DemandOut(BaseModel):
    id: int
    sender_email: str
    sender_name: Optional[str] = None
    subject: Optional[str] = None
    client_name: Optional[str] = None
    nup: Optional[str] = None
    bank: Optional[Bank] = None
    status: DemandStatus
    assigned_user: Optional[UserMini] = None
    email_account: Optional[InboxAccountMini] = None
    last_message_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class DemandDetail(DemandOut):
    messages: List[MessageOut] = []
