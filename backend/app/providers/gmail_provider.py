"""
GmailEmailProvider — Google Gmail API.

Usa OAuth2 com refresh_token (modo "installed app" do Google). Lê a caixa
do usuário autenticado via /users/me/messages.

Para ativar:
  1. Google Cloud Console -> criar projeto.
  2. Habilitar "Gmail API" em "APIs & Services" -> Library.
  3. OAuth consent screen -> External, adicionar seu próprio e-mail em
     "Test users" (enquanto o app não estiver verificado).
  4. Credentials -> Create credentials -> OAuth client ID -> Desktop app
     (ou Web; se Web use redirect_uri http://localhost:8765/callback).
  5. Anotar GMAIL_CLIENT_ID e GMAIL_CLIENT_SECRET no .env.
  6. Rodar `python -m app.providers.gmail_oauth` para obter o refresh_token.
"""
import base64
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime
from typing import Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.database import SessionLocal
from app.providers.email_provider import EmailProvider, ProviderAttachment, ProviderMessage


GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _header(headers: List[dict], name: str) -> Optional[str]:
    name_l = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name_l:
            return h.get("value")
    return None


def _extract_body(payload: dict) -> Dict[str, Optional[str]]:
    """Anda recursivo nas parts e retorna dict com text/plain e text/html."""
    result = {"text": None, "html": None}

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        body = part.get("body") or {}
        data = body.get("data")
        if data:
            decoded = _b64url_decode(data).decode("utf-8", errors="replace")
            if mime == "text/plain" and not result["text"]:
                result["text"] = decoded
            elif mime == "text/html" and not result["html"]:
                result["html"] = decoded
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    return result


def _attachments(payload: dict) -> List[ProviderAttachment]:
    found: List[ProviderAttachment] = []

    def walk(part: dict) -> None:
        body = part.get("body") or {}
        if part.get("filename") and body.get("attachmentId"):
            found.append(ProviderAttachment(
                external_id=body["attachmentId"],
                filename=part["filename"],
                mime_type=part.get("mimeType"),
                size=body.get("size"),
            ))
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    return found


import threading as _threading
import time as _time
from collections import deque as _deque

# Rate limiter global thread-safe.
# Gmail: 15.000 quota units/min por usuario. messages.get = 5 units = 3000/min = 50/s teto.
# Operamos com folga em 25/s para nao acionar throttle silencioso.
_RATE_LOCK = _threading.Lock()
_REQUEST_TIMES: _deque = _deque(maxlen=500)
_TARGET_RPS = 25


def _rate_limit() -> None:
    with _RATE_LOCK:
        now = _time.time()
        while _REQUEST_TIMES and _REQUEST_TIMES[0] < now - 1.0:
            _REQUEST_TIMES.popleft()
        if len(_REQUEST_TIMES) >= _TARGET_RPS:
            sleep_until = _REQUEST_TIMES[0] + 1.0
            wait = max(0.0, sleep_until - now)
            if wait > 0:
                _time.sleep(wait)
        _REQUEST_TIMES.append(_time.time())


class GmailEmailProvider(EmailProvider):
    """Instanciado por conta Gmail. Cada conta tem suas próprias credenciais e token."""

    def __init__(self, account=None) -> None:
        """account: EmailAccount ORM object. Se None, usa credenciais globais (legado)."""
        self._account = account
        self._token: Optional[str] = None
        self._tls = _threading.local()

    def _client_for_thread(self) -> httpx.Client:
        c = getattr(self._tls, "client", None)
        if c is None:
            c = httpx.Client(
                timeout=httpx.Timeout(connect=15, read=60, write=60, pool=10),
                limits=httpx.Limits(max_keepalive_connections=2, max_connections=4),
                http2=False,
            )
            self._tls.client = c
        return c

    @property
    def _client(self) -> httpx.Client:
        return self._client_for_thread()

    def _get_credentials(self):
        """Retorna (client_id, client_secret, refresh_token).
        Prioridade: override da conta → AppConfig → .env"""
        from app.services.oauth_service import _gmail_client_id, _gmail_client_secret
        if self._account:
            client_id = self._account.client_id_override or ""
            client_secret = self._account.client_secret_override or ""
            refresh = self._account.refresh_token or settings.GMAIL_REFRESH_TOKEN or None
            if not client_id or not client_secret:
                db = SessionLocal()
                try:
                    client_id = client_id or _gmail_client_id(db)
                    client_secret = client_secret or _gmail_client_secret(db)
                finally:
                    db.close()
            return client_id, client_secret, refresh
        # legado: sem account, usa globais
        db = SessionLocal()
        try:
            client_id = _gmail_client_id(db)
            client_secret = _gmail_client_secret(db)
            from app.services.oauth_service import get_active_token
            refresh = get_active_token(db, "gmail") or settings.GMAIL_REFRESH_TOKEN or None
        finally:
            db.close()
        return client_id, client_secret, refresh

    def _get_token(self) -> str:
        if self._token:
            return self._token
        client_id, client_secret, refresh = self._get_credentials()
        if not client_id or not refresh:
            raise RuntimeError("Credenciais Gmail ausentes: configure CLIENT_ID/SECRET e conecte a conta na tela Configuracoes.")
        resp = httpx.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}"}

    def _get_full(self, msg_id: str) -> dict:
        delay = 1.0
        for attempt in range(6):
            _rate_limit()  # pacing global antes de cada request
            resp = self._client.get(
                f"{GMAIL_BASE}/messages/{msg_id}",
                headers=self._headers(),
                params={"format": "full"},
                timeout=60,
            )
            if resp.status_code in (403, 429):
                _time.sleep(delay)
                delay = min(delay * 2, 16)
                continue
            resp.raise_for_status()
            return resp.json()
        resp.raise_for_status()
        return resp.json()

    def _to_provider_msg(self, item: dict) -> ProviderMessage:
        payload = item.get("payload", {}) or {}
        headers = payload.get("headers", []) or []
        from_raw = _header(headers, "From") or ""
        sender_name, sender_email = parseaddr(from_raw)
        to_raw = _header(headers, "To") or ""
        recipients = [parseaddr(r)[1] for r in to_raw.split(",") if r.strip()]
        subject = _header(headers, "Subject")
        date_raw = _header(headers, "Date")
        try:
            received_at = parsedate_to_datetime(date_raw) if date_raw else datetime.fromtimestamp(int(item.get("internalDate", 0)) / 1000, tz=timezone.utc)
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=timezone.utc)
            received_at = received_at.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            received_at = datetime.utcnow()

        body = _extract_body(payload)
        return ProviderMessage(
            external_id=item["id"],
            thread_id=item.get("threadId"),
            sender_email=sender_email,
            sender_name=sender_name or None,
            recipients=recipients,
            subject=subject,
            body_text=body["text"],
            body_html=body["html"],
            received_at=received_at,
            attachments=_attachments(payload),
        )

    def list_message_ids(self, since: Optional[datetime] = None, limit: int = 100000) -> List[str]:
        """Lista apenas IDs paginando. Operação barata (não baixa corpo)."""
        ids: List[str] = []
        page_token: Optional[str] = None
        per_page = 500  # Gmail aceita até 500 por página no list
        # Filtra só e-mails relevantes: exclui promoções, notificações e newsletters
        q = "-category:promotions -category:updates -category:social -category:forums"
        if since:
            q += f" after:{int(since.timestamp())}"
        while len(ids) < limit:
            params: dict = {"maxResults": str(min(per_page, limit - len(ids)))}
            if q:
                params["q"] = q
            if page_token:
                params["pageToken"] = page_token
            resp = self._client.get(f"{GMAIL_BASE}/messages", headers=self._headers(), params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for m in data.get("messages", []) or []:
                ids.append(m["id"])
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return ids

    def list_messages(self, since: Optional[datetime] = None, limit: int = 1000) -> List[ProviderMessage]:
        ids = self.list_message_ids(since=since, limit=limit)
        return [self._to_provider_msg(self._get_full(mid)) for mid in ids]

    def get_message_by_id(self, external_id: str) -> Optional[ProviderMessage]:
        resp = self._client.get(f"{GMAIL_BASE}/messages/{external_id}", headers=self._headers(), params={"format": "full"}, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._to_provider_msg(resp.json())

    def get_thread(self, thread_id: str) -> List[ProviderMessage]:
        resp = self._client.get(f"{GMAIL_BASE}/threads/{thread_id}", headers=self._headers(), params={"format": "full"}, timeout=30)
        resp.raise_for_status()
        return [self._to_provider_msg(m) for m in resp.json().get("messages", [])]

    def send_reply(self, to: str, from_addr: str, subject: str, body_text: str, thread_id: Optional[str] = None) -> str:
        """Envia resposta por e-mail e retorna o external_id da mensagem enviada."""
        import email.mime.text as _mime_text
        subject_str = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        msg = _mime_text.MIMEText(body_text, "plain", "utf-8")
        msg["To"] = to
        msg["From"] = from_addr
        msg["Subject"] = subject_str
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        payload: dict = {"raw": raw}
        if thread_id:
            payload["threadId"] = thread_id
        resp = self._client.post(
            f"{GMAIL_BASE}/messages/send",
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["id"]
