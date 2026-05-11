from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class ProviderAttachment:
    external_id: str
    filename: str
    mime_type: Optional[str] = None
    size: Optional[int] = None


@dataclass
class ProviderMessage:
    external_id: str
    thread_id: Optional[str]
    sender_email: str
    sender_name: Optional[str]
    recipients: List[str]
    subject: Optional[str]
    body_text: Optional[str]
    body_html: Optional[str]
    received_at: datetime
    attachments: List[ProviderAttachment] = field(default_factory=list)


class EmailProvider(ABC):
    """Contrato para integração com Outlook / Gmail / Mock."""

    @abstractmethod
    def list_messages(self, since: Optional[datetime] = None, limit: int = 50) -> List[ProviderMessage]:
        ...

    def list_message_ids(self, since: Optional[datetime] = None, limit: int = 5000) -> List[str]:
        """Retorna apenas os external_ids — operação barata para enumerar a caixa
        antes de baixar detalhes. Default: usa list_messages e extrai ids
        (subclasses devem sobrescrever para versão mais eficiente)."""
        return [m.external_id for m in self.list_messages(since=since, limit=limit)]

    @abstractmethod
    def get_message_by_id(self, external_id: str) -> Optional[ProviderMessage]:
        ...

    @abstractmethod
    def get_thread(self, thread_id: str) -> List[ProviderMessage]:
        ...

    # Reservados para evoluções futuras (envio, marcação, mover de pasta).
    def send_message(self, to: List[str], subject: str, body: str, in_reply_to: Optional[str] = None) -> str:
        raise NotImplementedError

    def mark_as_read(self, external_id: str) -> None:
        raise NotImplementedError

    def move_message(self, external_id: str, folder: str) -> None:
        raise NotImplementedError
