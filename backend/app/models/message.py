from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    demand_id = Column(Integer, ForeignKey("demands.id", ondelete="CASCADE"), nullable=False, index=True)
    external_message_id = Column(String(255), index=True, unique=True, nullable=True)
    direction = Column(String(10), nullable=False, default="in")  # in | out
    sent_by_user_id = Column(Integer, nullable=True, index=True)  # quem enviou (só para direction=out)
    sender_email = Column(String(180), nullable=False)
    sender_name = Column(String(180), nullable=True)
    recipient_emails = Column(Text, nullable=True)  # csv (To)
    cc_emails = Column(Text, nullable=True)  # csv (Cc)
    subject = Column(String(500), nullable=True)
    body_text = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)
    received_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    has_attachments = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    demand = relationship("Demand", back_populates="messages")
    attachments = relationship("Attachment", back_populates="message", cascade="all, delete-orphan")
