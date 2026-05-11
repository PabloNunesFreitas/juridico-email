from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class AssignmentRule(Base):
    """Continuidade automática: vincula um remetente a um responsável."""
    __tablename__ = "assignment_rules"

    id = Column(Integer, primary_key=True, index=True)
    sender_email = Column(String(180), unique=True, index=True, nullable=False)
    assigned_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
