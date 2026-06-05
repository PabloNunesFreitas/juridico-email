from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text

from app.core.database import Base


class AppConfig(Base):
    __tablename__ = "app_config"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
