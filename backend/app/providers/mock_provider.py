"""
Provider mockado para PoC. Gera e-mails sintéticos representativos do fluxo
jurídico de poupança (banco, NUP, cliente, status no assunto).
"""
import random
from datetime import datetime, timedelta
from typing import List, Optional

from app.providers.email_provider import EmailProvider, ProviderMessage, ProviderAttachment


_BANKS = ["BB", "CEF", "Itaú", "Bradesco", "Santander"]
_CLIENTS = [
    ("João Pereira", "joao.pereira@cliente.com"),
    ("Maria Silva", "maria.silva@cliente.com"),
    ("Carlos Souza", "advcarlos@escritorio.com"),
    ("Ana Lima", "ana.lima@cliente.com"),
    ("Banco Itaú Jurídico", "juridico@itau-mock.com"),
    ("CEF Acordos", "acordos@cef-mock.com"),
]
_STATUSES = [
    "Solicita proposta",
    "Proposta aceita",
    "Enviar minuta assinada",
    "Follow up",
    "Pendências",
    "Acordo realizado",
]


def _seed_messages() -> List[ProviderMessage]:
    random.seed(42)
    out: List[ProviderMessage] = []
    base = datetime.utcnow() - timedelta(days=10)
    for i in range(15):
        client_name, client_email = random.choice(_CLIENTS)
        bank = random.choice(_BANKS)
        status = random.choice(_STATUSES)
        nup = f"{random.randint(1000000,9999999)}-{random.randint(10,99)}.2024.8.26.0000"
        subject = f"{status} / {client_name} / {nup} / {bank} / Resp."
        thread_id = f"thr-{client_email}-{i % 6}"
        received = base + timedelta(hours=i * 7)
        out.append(ProviderMessage(
            external_id=f"msg-{i:04d}",
            thread_id=thread_id,
            sender_email=client_email,
            sender_name=client_name,
            recipients=["poupanca@empresa.com.br"],
            subject=subject,
            body_text=f"Prezados,\n\nSegue tratativa referente ao processo {nup} junto ao {bank}.\n\nAtenciosamente,\n{client_name}",
            body_html=None,
            received_at=received,
            attachments=[ProviderAttachment(external_id=f"att-{i}", filename="minuta.pdf", mime_type="application/pdf", size=12345)] if i % 3 == 0 else [],
        ))
    return out


class MockEmailProvider(EmailProvider):
    def __init__(self) -> None:
        self._store: List[ProviderMessage] = _seed_messages()

    def list_messages(self, since: Optional[datetime] = None, limit: int = 50) -> List[ProviderMessage]:
        msgs = self._store
        if since:
            msgs = [m for m in msgs if m.received_at >= since]
        return sorted(msgs, key=lambda m: m.received_at)[:limit]

    def get_message_by_id(self, external_id: str) -> Optional[ProviderMessage]:
        return next((m for m in self._store if m.external_id == external_id), None)

    def get_thread(self, thread_id: str) -> List[ProviderMessage]:
        return [m for m in self._store if m.thread_id == thread_id]

    def send_reply(self, to: str, from_addr: str, subject: str, body_text: str, thread_id: Optional[str] = None, cc: Optional[List[str]] = None, attachments: Optional[List[tuple]] = None, body_html: Optional[str] = None, inline_images: Optional[List[tuple]] = None) -> str:
        import uuid
        ext_id = f"mock-out-{uuid.uuid4().hex[:8]}"
        self._store.append(ProviderMessage(
            external_id=ext_id,
            thread_id=thread_id,
            sender_email=from_addr,
            sender_name=None,
            recipients=[to] + (cc or []),
            subject=subject if subject.lower().startswith("re:") else f"Re: {subject}",
            body_text=body_text,
            body_html=None,
            received_at=datetime.utcnow(),
        ))
        return ext_id
