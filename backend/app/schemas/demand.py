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
    to_emails: Optional[List[str]] = Field(default=None, description="Destinatários (padrão: remetente original)")
    cc: List[str] = Field(default_factory=list, description="Endereços de e-mail em cópia (CC)")


class ComposeIn(BaseModel):
    to_emails: List[str] = Field(..., description="Destinatários")
    cc: List[str] = Field(default_factory=list)
    subject: str
    body_text: str
    account_id: Optional[int] = None


class AssignIn(BaseModel):
    user_id: int


class StatusIn(BaseModel):
    status: DemandStatus


class AttachmentOut(BaseModel):
    id: int
    filename: str
    mime_type: Optional[str] = None
    size: Optional[int] = None
    external_attachment_id: Optional[str] = None

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    id: int
    direction: str
    sender_email: str
    sender_name: Optional[str] = None
    recipient_emails: Optional[str] = None
    subject: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    received_at: datetime
    has_attachments: bool
    attachments: List[AttachmentOut] = []

    class Config:
        from_attributes = True


class CommentOut(BaseModel):
    id: int
    demand_id: int
    user_id: int
    user_name: str
    content: str
    created_at: datetime

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


class CoAssigneeOut(BaseModel):
    share_id: int
    user: UserMini

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
    co_assignees: List[CoAssigneeOut] = []
    email_account: Optional[InboxAccountMini] = None
    folder_id: Optional[int] = None
    archived: bool = False
    last_message_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class DemandDetail(DemandOut):
    messages: List[MessageOut] = []
