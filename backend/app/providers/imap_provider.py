"""IMAP/SMTP Email Provider — suporta qualquer servidor IMAP/SMTP (mail.shared.acl.com.br, etc)."""
import imaplib
import smtplib
import logging
from datetime import datetime, timezone
from email import message_from_bytes
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Optional

from app.providers.email_provider import EmailProvider, ProviderMessage, ProviderAttachment

log = logging.getLogger("imap_provider")


class IMAPEmailProvider(EmailProvider):
    """Provider IMAP/SMTP para servidores como mail.shared.acl.com.br"""

    def __init__(
        self,
        imap_host: str,
        imap_port: int,
        smtp_host: str,
        smtp_port: int,
        email: str,
        password: str,
        use_ssl_imap: bool = True,
        use_tls_smtp: bool = True,
    ):
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.email = email
        self.password = password
        self.use_ssl_imap = use_ssl_imap
        self.use_tls_smtp = use_tls_smtp
        self._imap = None

    def _get_imap(self):
        """Conecta ao servidor IMAP com timeout adequado."""
        self._close_imap()  # Sempre fecha antes de reabrir (evita corrupção)
        try:
            if self.use_ssl_imap:
                self._imap = imaplib.IMAP4_SSL(self.imap_host, self.imap_port, timeout=30)
            else:
                self._imap = imaplib.IMAP4(self.imap_host, self.imap_port, timeout=30)
            self._imap.login(self.email, self.password)
        except Exception as e:
            self._imap = None
            raise RuntimeError(f"Falha ao conectar IMAP: {e}")
        return self._imap

    def _close_imap(self):
        """Fecha conexão IMAP."""
        if self._imap:
            try:
                self._imap.close()
            except Exception:
                pass
            self._imap = None

    def list_message_ids(self, since: Optional[datetime] = None, limit: int = 5000) -> List[str]:
        """Lista IDs de e-mails na caixa de entrada."""
        try:
            imap = self._get_imap()
            imap.select("INBOX")

            # Busca por data se fornecida
            search_criteria = "ALL"
            if since:
                date_str = since.strftime("%d-%b-%Y")
                search_criteria = f'SINCE "{date_str}"'

            status, message_ids = imap.search(None, search_criteria)
            if status != "OK":
                return []

            ids = message_ids[0].split()
            # IMAP retorna em ordem crescente, invertemos para ter os mais recentes primeiro
            return [mid.decode() for mid in ids[-limit:]][::-1]
        except Exception as e:
            log.error(f"Erro ao listar IDs IMAP: {e}")
            self._close_imap()
            raise

    def list_messages(self, since: Optional[datetime] = None, limit: int = 50) -> List[ProviderMessage]:
        """Lista mensagens com detalhes."""
        ids = self.list_message_ids(since=since, limit=limit)
        messages = []
        for mid in ids[:limit]:
            msg = self.get_message_by_id(mid)
            if msg:
                messages.append(msg)
        return messages

    def get_message_by_id(self, external_id: str) -> Optional[ProviderMessage]:
        """Busca uma mensagem específica por ID IMAP."""
        try:
            imap = self._get_imap()
            imap.select("INBOX")
            status, data = imap.fetch(external_id, "(RFC822)")
            if status != "OK" or not data[0]:
                return None

            email_msg = message_from_bytes(data[0][1])
            return self._parse_message(external_id, email_msg)
        except Exception as e:
            log.error(f"Erro ao buscar mensagem {external_id}: {e}")
            return None

    def get_thread(self, thread_id: str) -> List[ProviderMessage]:
        """IMAP não suporta threads nativamente — retorna a mensagem como single-item list."""
        msg = self.get_message_by_id(thread_id)
        return [msg] if msg else []

    def _parse_message(self, external_id: str, email_msg) -> ProviderMessage:
        """Converte email.message para ProviderMessage."""
        sender_email = email_msg.get("From", "unknown@unknown.com")
        sender_name = None

        # Parse "Name <email@domain.com>" format
        if "<" in sender_email:
            sender_name = sender_email.split("<")[0].strip()
            sender_email = sender_email.split("<")[1].rstrip(">")

        recipients = []
        for hdr in ["To", "Cc"]:
            val = email_msg.get(hdr, "")
            if val:
                # Simples parse — split por vírgula
                recipients.extend([e.strip().split("<")[-1].rstrip(">") if "<" in e else e.strip() for e in val.split(",")])

        subject = email_msg.get("Subject", "(sem assunto)")
        body_text = None
        body_html = None
        attachments = []

        # Parse corpo e anexos
        if email_msg.is_multipart():
            for part in email_msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain" and not body_text:
                    body_text = part.get_payload(decode=True).decode("utf-8", errors="replace")
                elif ctype == "text/html" and not body_html:
                    body_html = part.get_payload(decode=True).decode("utf-8", errors="replace")
                elif ctype not in ["text/plain", "text/html", "multipart/alternative", "multipart/related"]:
                    # Anexo
                    filename = part.get_filename() or "attachment"
                    attachments.append(ProviderAttachment(
                        external_id=f"{external_id}_{filename}",
                        filename=filename,
                        mime_type=ctype,
                        size=len(part.get_payload(decode=True)),
                    ))
        else:
            body_text = email_msg.get_payload()

        # Parse data
        received_at = datetime.now(timezone.utc)
        date_str = email_msg.get("Date")
        if date_str:
            try:
                from email.utils import parsedate_to_datetime
                received_at = parsedate_to_datetime(date_str)
            except Exception:
                pass

        return ProviderMessage(
            external_id=external_id,
            thread_id=external_id,  # IMAP não tem threads — usamos o ID da mensagem
            sender_email=sender_email,
            sender_name=sender_name,
            recipients=list(set(recipients)),  # Remove duplicatas
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            received_at=received_at,
            attachments=attachments,
        )

    def send_reply(
        self,
        to: str,
        from_addr: str,
        subject: str,
        body_text: str,
        thread_id: Optional[str] = None,
        cc: Optional[List[str]] = None,
        attachments: Optional[List[tuple]] = None,
    ) -> str:
        """Envia resposta via SMTP."""
        try:
            msg = MIMEMultipart()
            msg["From"] = from_addr
            msg["To"] = to
            if cc:
                msg["Cc"] = ", ".join(cc)
            msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"

            msg.attach(MIMEText(body_text, "plain"))

            # Anexos
            if attachments:
                for filename, mime_type, data in attachments:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(data)
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", "attachment", filename=filename)
                    msg.attach(part)

            # Enviar via SMTP
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as smtp:
                if self.use_tls_smtp:
                    smtp.starttls()
                smtp.login(self.email, self.password)
                smtp.send_message(msg)

            return f"{from_addr}_{datetime.now(timezone.utc).timestamp()}"
        except Exception as e:
            log.error(f"Erro ao enviar e-mail SMTP: {e}")
            raise RuntimeError(f"Falha ao enviar e-mail: {e}")

    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Busca bytes de um anexo."""
        try:
            imap = self._get_imap()
            imap.select("INBOX")
            status, data = imap.fetch(message_id, "(RFC822)")
            if status != "OK":
                raise RuntimeError("Mensagem não encontrada")

            email_msg = message_from_bytes(data[0][1])

            # Procura pelo anexo
            for part in email_msg.walk():
                filename = part.get_filename()
                if filename and f"{message_id}_{filename}" == attachment_id:
                    return part.get_payload(decode=True)

            raise RuntimeError("Anexo não encontrado")
        except Exception as e:
            log.error(f"Erro ao baixar anexo: {e}")
            raise
