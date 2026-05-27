from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint

from app.core.database import Base


class EmailAccount(Base):
    __tablename__ = "email_accounts"
    __table_args__ = (UniqueConstraint("provider", "email_address", name="uq_provider_email"),)

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(20), nullable=False, default="mock")  # mock | outlook | gmail
    email_address = Column(String(180), nullable=False)
    color = Column(String(7), nullable=False, default="#6366f1")
    # Credenciais específicas desta conta (sobrepõem AppConfig/env quando preenchidas)
    client_id_override = Column(String(500), nullable=True)
    client_secret_override = Column(Text, nullable=True)
    # Tokens OAuth
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    needs_reconnect = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
