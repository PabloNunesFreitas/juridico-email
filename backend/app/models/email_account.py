from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint

from app.core.database import Base


class EmailAccount(Base):
    __tablename__ = "email_accounts"
    __table_args__ = (UniqueConstraint("provider", "email_address", name="uq_provider_email"),)

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(20), nullable=False, default="mock")  # mock | outlook | gmail | imap
    email_address = Column(String(180), nullable=False)
    color = Column(String(7), nullable=False, default="#6366f1")
    # Credenciais específicas desta conta (sobrepõem AppConfig/env quando preenchidas)
    client_id_override = Column(String(500), nullable=True)
    client_secret_override = Column(Text, nullable=True)
    # Tokens OAuth
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    # Configuração IMAP/SMTP (para provider="imap")
    imap_host = Column(String(255), nullable=True)
    imap_port = Column(Integer, nullable=True, default=993)
    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(Integer, nullable=True, default=587)
    password = Column(Text, nullable=True)  # Encriptografado para IMAP
    active = Column(Boolean, nullable=False, default=True)
    needs_reconnect = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
