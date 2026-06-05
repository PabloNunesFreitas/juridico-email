from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    demand_id = Column(Integer, ForeignKey("demands.id", ondelete="SET NULL"), nullable=True, index=True)
    type = Column(String(50), nullable=False)
    message = Column(String(500), nullable=False)
    read = Column(Boolean, default=False, nullable=False, index=True)
    responded = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User")
    demand = relationship("Demand")
