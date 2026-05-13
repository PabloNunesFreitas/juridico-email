from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.core.database import Base


class DemandShare(Base):
    __tablename__ = "demand_shares"
    id = Column(Integer, primary_key=True, index=True)
    demand_id = Column(Integer, ForeignKey("demands.id", ondelete="CASCADE"), nullable=False, index=True)
    shared_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    shared_with_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    note = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    demand = relationship("Demand")
    shared_by = relationship("User", foreign_keys=[shared_by_id])
    shared_with = relationship("User", foreign_keys=[shared_with_id])
