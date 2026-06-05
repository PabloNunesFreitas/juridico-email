from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.core.database import Base


class DemandShare(Base):
    __tablename__ = "demand_shares"
    id = Column(Integer, primary_key=True, index=True)
    demand_id = Column(Integer, ForeignKey("demands.id", ondelete="CASCADE"), nullable=False, index=True)
    shared_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    shared_with_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    note = Column(String(500), nullable=True)
    is_co_assignee = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    demand = relationship("Demand")
    shared_by = relationship("User", foreign_keys=[shared_by_id])
    shared_with = relationship("User", foreign_keys=[shared_with_id])
