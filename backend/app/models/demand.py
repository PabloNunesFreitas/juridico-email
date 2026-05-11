import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class DemandStatus(str, enum.Enum):
    CAIXA_ENTRADA = "Caixa de Entrada"
    ENVIAR_RESPOSTA_BANCO = "Enviar resposta banco"
    ENVIAR_MINUTA_ASSINADA = "Enviar minuta assinada"
    PENDENCIAS = "Pendências"
    ERRO = "Erro"
    ACORDOS_REALIZADOS = "Acordos realizados"
    SOLICITADA_PROPOSTA = "Solicitada proposta"
    PROPOSTA_ACEITA = "Proposta aceita"
    FOLLOW_UP = "Follow up"
    PROPOSTA_COM_ERRO = "Proposta com erro"
    MINUTA_ASSINADA = "Minuta assinada"


class Bank(str, enum.Enum):
    BB = "Banco do Brasil"
    CEF = "Caixa Econômica Federal"
    ITAU = "Itaú"
    BRADESCO = "Bradesco"
    SANTANDER = "Santander"
    OUTROS = "Outros"


class Demand(Base):
    __tablename__ = "demands"

    id = Column(Integer, primary_key=True, index=True)
    external_thread_id = Column(String(255), index=True, nullable=True)
    sender_email = Column(String(180), index=True, nullable=False)
    sender_name = Column(String(180), nullable=True)
    subject = Column(String(500), nullable=True)
    normalized_subject = Column(String(500), index=True, nullable=True)
    client_name = Column(String(180), nullable=True)
    nup = Column(String(60), nullable=True)
    bank = Column(Enum(Bank), nullable=True)
    status = Column(Enum(DemandStatus), nullable=False, default=DemandStatus.CAIXA_ENTRADA)
    assigned_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    email_account_id = Column(Integer, ForeignKey("email_accounts.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_message_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    assigned_user = relationship("User", foreign_keys=[assigned_user_id])
    email_account = relationship("EmailAccount", foreign_keys=[email_account_id])
    messages = relationship("Message", back_populates="demand", cascade="all, delete-orphan", order_by="Message.received_at")

