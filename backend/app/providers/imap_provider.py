"""IMAP/SMTP Email Provider — suporta qualquer servidor IMAP/SMTP (mail.shared.acl.com.br, etc)."""
import imaplib
import smtplib
import logging
from datetime import datetime, timezone
from email import message_from_bytes
from email.header import decode_header, make_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Optional

from app.providers.email_provider import EmailProvider, ProviderMessage, ProviderAttachment

log = logging.getLogger("imap_provider")


def _decode_mime_header(raw: Optional[str]) -> Optional[str]:
    """Decodifica cabeçalhos RFC 2047 (=?UTF-8?B?...?=) para texto legível."""
    if not raw:
        return raw
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return raw


def _decode_payload(part) -> Optional[str]:
    """Decodifica o corpo respeitando o charset declarado, com fallback.

    Muitos e-mails (Outlook/clientes BR antigos) usam ISO-8859-1 / Windows-1252.
    Forçar UTF-8 gera mojibake (acentos viram �). Aqui tentamos o charset
    declarado e, se falhar, cp1252/latin-1 (que mapeiam todos os bytes).
    """
    payload = part.get_payload(decode=True)
    if payload is None:
        return None
    declared = part.get_content_charset()
    candidates = []
    if declared:
        candidates.append(declared)
    candidates += ["utf-8", "cp1252", "latin-1"]
    for cs in candidates:
        try:
            return payload.decode(cs)
        except (LookupError, UnicodeDecodeError):
            continue
    return payload.decode("utf-8", errors="replace")


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
        self._selected_folder = None  # cache da pasta atualmente selecionada

    def _get_imap(self):
        """Conecta ao servidor IMAP com timeout adequado (força reconexão)."""
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

    def _ensure_imap(self):
        """Retorna a conexão existente se ainda viva (via NOOP); senão reconecta.

        Reusar a conexão é essencial para sync em massa: abrir/logar a cada
        e-mail seria lento e dispararia limites do provedor.
        """
        if self._imap is not None:
            try:
                status, _ = self._imap.noop()
                if status == "OK":
                    return self._imap
            except Exception:
                pass
        self._selected_folder = None
        return self._get_imap()

    def _select_folder(self, imap, folder: str, readonly: bool = True):
        """Seleciona uma pasta (com cache). Nomes vêm em modified UTF-7 (ASCII)."""
        if self._selected_folder == (folder, readonly):
            return
        status, _ = imap.select(f'"{folder}"', readonly=readonly)
        if status != "OK":
            raise RuntimeError(f"Falha ao selecionar pasta {folder}")
        self._selected_folder = (folder, readonly)

    def _list_folders(self, imap) -> List[str]:
        """Lista todas as pastas selecionáveis (nomes em modified UTF-7 ASCII)."""
        import re
        status, boxes = imap.list()
        if status != "OK" or not boxes:
            return ["INBOX"]
        folders = []
        for raw in boxes:
            line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
            # Ignora pastas marcadas como \Noselect
            if "\\Noselect" in line:
                continue
            try:
                if '"." ' in line:
                    part = line.split('"." ', 1)[1].strip()
                else:
                    part = line.rsplit(" ", 1)[1].strip()
                if part.startswith('"') and part.endswith('"'):
                    part = part[1:-1]
                folders.append(part)
            except Exception:
                continue
        return folders or ["INBOX"]

    def _close_imap(self):
        """Fecha conexão IMAP."""
        if self._imap:
            try:
                self._imap.logout()
            except Exception:
                try:
                    self._imap.close()
                except Exception:
                    pass
            self._imap = None
            self._selected_folder = None

    # Separador usado nos IDs compostos: "<pasta>\x1f<uid>"
    ID_SEP = "\x1f"

    def _parse_external_id(self, external_id: str):
        """Decodifica um external_id. Retorna (folder, uid, is_uid).

        - Formato novo: "<pasta>\x1f<uid>"  -> (pasta, uid, True)
        - Formato legado: "<seqnum>"          -> ("INBOX", seqnum, False)
        """
        if self.ID_SEP in external_id:
            folder, uid = external_id.split(self.ID_SEP, 1)
            return folder, uid, True
        return "INBOX", external_id, False

    def list_message_ids(self, since: Optional[datetime] = None, limit: int = 5000) -> List[str]:
        """Lista IDs de e-mails em TODAS as pastas (IDs compostos pasta\\x1fUID).

        Varre todas as pastas selecionáveis e usa UID (estável) em vez de
        número de sequência. Retorna no máximo `limit` IDs no total.
        """
        try:
            log.info(f"[IMAP] Conectando a {self.imap_host}:{self.imap_port} como {self.email}")
            imap = self._ensure_imap()

            search_criteria = "ALL"
            if since:
                date_str = since.strftime("%d-%b-%Y")
                search_criteria = f'(SINCE "{date_str}")'

            folders = self._list_folders(imap)
            log.info(f"[IMAP] {len(folders)} pasta(s) encontrada(s); critério: {search_criteria}")

            result: List[str] = []
            for folder in folders:
                try:
                    self._select_folder(imap, folder, readonly=True)
                    status, data = imap.uid("SEARCH", None, search_criteria)
                    if status != "OK" or not data or not data[0]:
                        continue
                    uids = data[0].split()
                    # mais recentes primeiro, respeitando limite por pasta
                    uids = uids[-limit:][::-1]
                    for u in uids:
                        result.append(f"{folder}{self.ID_SEP}{u.decode()}")
                    log.info(f"[IMAP]   {folder}: {len(uids)} msgs")
                except Exception as fe:
                    log.warning(f"[IMAP] falha na pasta {folder}: {fe}")
                    continue

            log.info(f"[IMAP] Total de IDs (todas as pastas): {len(result)}")
            return result[:limit] if limit else result
        except Exception as e:
            log.error(f"[IMAP] Erro ao listar IDs: {e}", exc_info=True)
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
        """Busca uma mensagem específica (ID composto pasta\\x1fUID ou legado)."""
        try:
            folder, ident, is_uid = self._parse_external_id(external_id)
            imap = self._ensure_imap()
            self._select_folder(imap, folder, readonly=True)
            if is_uid:
                status, data = imap.uid("FETCH", ident, "(RFC822)")
            else:
                status, data = imap.fetch(ident, "(RFC822)")
            if status != "OK" or not data or not data[0]:
                return None

            email_msg = message_from_bytes(data[0][1])
            return self._parse_message(external_id, email_msg)
        except Exception as e:
            log.error(f"Erro ao buscar mensagem {external_id}: {e}")
            # Conexão pode ter caído — força reconexão na próxima
            self._close_imap()
            return None

    def get_thread(self, thread_id: str) -> List[ProviderMessage]:
        """IMAP não suporta threads nativamente — retorna a mensagem como single-item list."""
        msg = self.get_message_by_id(thread_id)
        return [msg] if msg else []

    def _parse_message(self, external_id: str, email_msg) -> ProviderMessage:
        """Converte email.message para ProviderMessage."""
        from_raw = _decode_mime_header(email_msg.get("From", "unknown@unknown.com"))
        sender_email = from_raw
        sender_name = None

        # Parse "Name <email@domain.com>" format
        if "<" in sender_email:
            sender_name = sender_email.split("<")[0].strip().strip('"') or None
            sender_email = sender_email.split("<")[1].rstrip(">")

        recipients = []
        for hdr in ["To", "Cc"]:
            val = email_msg.get(hdr, "")
            if val:
                # Simples parse — split por vírgula
                recipients.extend([e.strip().split("<")[-1].rstrip(">") if "<" in e else e.strip() for e in val.split(",")])

        subject = _decode_mime_header(email_msg.get("Subject", "(sem assunto)"))
        body_text = None
        body_html = None
        attachments = []

        # Parse corpo e anexos (robusto a partes sem payload / None)
        if email_msg.is_multipart():
            for part in email_msg.walk():
                try:
                    ctype = part.get_content_type()
                    if ctype in ("multipart/alternative", "multipart/related", "multipart/mixed"):
                        continue
                    disp = (part.get("Content-Disposition") or "").lower()
                    is_attachment = "attachment" in disp or part.get_filename()
                    if ctype == "text/plain" and not body_text and not is_attachment:
                        body_text = _decode_payload(part)
                    elif ctype == "text/html" and not body_html and not is_attachment:
                        body_html = _decode_payload(part)
                    elif is_attachment or ctype not in ("text/plain", "text/html"):
                        payload = part.get_payload(decode=True)
                        # Anexo
                        filename = part.get_filename() or "attachment"
                        attachments.append(ProviderAttachment(
                            external_id=f"{external_id}_{filename}",
                            filename=filename,
                            mime_type=ctype,
                            size=len(payload) if payload is not None else 0,
                        ))
                except Exception as pe:
                    log.warning(f"[IMAP] parte ignorada em {external_id}: {pe}")
                    continue
        else:
            content = _decode_payload(email_msg)
            if content is None:
                raw = email_msg.get_payload()
                content = raw if isinstance(raw, str) else None
            # Roteia conforme o tipo: HTML de parte única vai pro campo HTML
            if content is not None:
                if email_msg.get_content_type() == "text/html":
                    body_html = content
                else:
                    body_text = content

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
        """Busca bytes de um anexo (ID composto pasta\\x1fUID ou legado)."""
        try:
            folder, ident, is_uid = self._parse_external_id(message_id)
            imap = self._ensure_imap()
            self._select_folder(imap, folder, readonly=True)
            if is_uid:
                status, data = imap.uid("FETCH", ident, "(RFC822)")
            else:
                status, data = imap.fetch(ident, "(RFC822)")
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
