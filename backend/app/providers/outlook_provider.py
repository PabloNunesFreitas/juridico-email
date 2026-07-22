"""
OutlookEmailProvider — Microsoft Graph.

Suporta dois modos:
  - Application (client_credentials): tenant corporativo pago. Lê qualquer caixa
    via /users/{email}/messages. Usado quando OUTLOOK_REFRESH_TOKEN está vazio
    e OUTLOOK_TENANT_ID é específico.
  - Delegated (refresh_token): conta pessoal Outlook.com/Hotmail OU corporativa.
    Lê a caixa do usuário autenticado via /me/messages. Usado quando há
    OUTLOOK_REFRESH_TOKEN. Tenant deve ser "common" para conta pessoal.

Para obter o refresh_token inicial, ver `app/providers/outlook_oauth.py`.
"""
from datetime import datetime
from typing import List, Optional

import httpx

from app.core.config import settings
from app.core.database import SessionLocal
from app.providers.email_provider import EmailProvider, ProviderMessage, ProviderAttachment


GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL_TPL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


class OutlookEmailProvider(EmailProvider):
    def __init__(self, account=None) -> None:
        self._account = account
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0
        _, _, _, refresh = self._load_credentials()
        self._delegated: bool = bool(refresh)

    def _load_credentials(self):
        """Retorna (client_id, client_secret, tenant, refresh_token).
        Prioridade: override da conta → AppConfig → .env"""
        from app.services.oauth_service import _outlook_client_id, _outlook_client_secret, _outlook_tenant
        if self._account:
            client_id = self._account.client_id_override or ""
            client_secret = self._account.client_secret_override or ""
            refresh = self._account.refresh_token or settings.OUTLOOK_REFRESH_TOKEN or None
            db = SessionLocal()
            try:
                client_id = client_id or _outlook_client_id(db)
                client_secret = client_secret or _outlook_client_secret(db)
                tenant = _outlook_tenant(db)
            finally:
                db.close()
            return client_id, client_secret, tenant, refresh
        # legado: sem account
        from app.services.oauth_service import get_active_token
        db = SessionLocal()
        try:
            client_id = _outlook_client_id(db)
            client_secret = _outlook_client_secret(db)
            tenant = _outlook_tenant(db)
            refresh = get_active_token(db, "outlook") or settings.OUTLOOK_REFRESH_TOKEN or None
        finally:
            db.close()
        return client_id, client_secret, tenant, refresh

    @property
    def _user_path(self) -> str:
        return "/me" if self._delegated else f"/users/{settings.CENTRAL_EMAIL}"

    def _get_token(self) -> str:
        import time as _time_mod
        if self._token and _time_mod.time() < self._token_expiry - 60:
            return self._token
        client_id, client_secret, tenant, refresh = self._load_credentials()
        if not client_id:
            raise RuntimeError("OUTLOOK_CLIENT_ID ausente. Configure em Configurações.")
        url = TOKEN_URL_TPL.format(tenant=tenant)
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if refresh:
            data["grant_type"] = "refresh_token"
            data["refresh_token"] = refresh
            data["scope"] = "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send offline_access User.Read"
        else:
            data["grant_type"] = "client_credentials"
            data["scope"] = "https://graph.microsoft.com/.default"
        resp = httpx.post(url, data=data, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        self._token = result["access_token"]
        self._token_expiry = _time_mod.time() + result.get("expires_in", 3600)
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}"}

    @staticmethod
    def _to_provider_msg(item: dict) -> ProviderMessage:
        sender = item.get("from", {}).get("emailAddress", {})
        return ProviderMessage(
            external_id=item["id"],
            thread_id=item.get("conversationId"),
            sender_email=sender.get("address", ""),
            sender_name=sender.get("name"),
            recipients=[r["emailAddress"]["address"] for r in item.get("toRecipients", [])],
            subject=item.get("subject"),
            body_text=(item.get("body", {}) or {}).get("content") if item.get("body", {}).get("contentType") == "text" else None,
            body_html=(item.get("body", {}) or {}).get("content") if item.get("body", {}).get("contentType") == "html" else None,
            received_at=datetime.fromisoformat(item["receivedDateTime"].replace("Z", "+00:00")),
            attachments=[
                ProviderAttachment(external_id=a["id"], filename=a.get("name", ""), mime_type=a.get("contentType"), size=a.get("size"))
                for a in item.get("attachments", [])
            ],
        )

    def _graph_get(self, url: str, params=None, next_link: Optional[str] = None) -> dict:
        import time as _time_mod
        for attempt in range(4):
            resp = httpx.get(next_link or url, headers=self._headers(), params=None if next_link else params, timeout=30)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", "10"))
                _time_mod.sleep(min(wait, 60))
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError("Microsoft Graph rate limit excedido após várias tentativas")

    def list_message_ids(self, since: Optional[datetime] = None, limit: int = 5000) -> List[str]:
        ids: List[str] = []
        url = f"{GRAPH_BASE}{self._user_path}/messages"
        filters = ["isJunk eq false", "isDraft eq false"]
        if since:
            filters.append(f"receivedDateTime ge {since.isoformat()}Z")
        params: dict = {"$top": "1000", "$select": "id", "$filter": " and ".join(filters)}
        next_link: Optional[str] = None
        while len(ids) < limit:
            data = self._graph_get(url, params=params, next_link=next_link)
            for m in data.get("value", []):
                ids.append(m["id"])
            next_link = data.get("@odata.nextLink")
            if not next_link:
                break
        return ids[:limit]

    def list_messages(self, since: Optional[datetime] = None, limit: int = 50) -> List[ProviderMessage]:
        params = {"$top": str(limit), "$orderby": "receivedDateTime desc"}
        if since:
            params["$filter"] = f"receivedDateTime ge {since.isoformat()}Z"
        url = f"{GRAPH_BASE}{self._user_path}/messages"
        resp = httpx.get(url, headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        return [self._to_provider_msg(m) for m in resp.json().get("value", [])]

    def get_message_by_id(self, external_id: str) -> Optional[ProviderMessage]:
        url = f"{GRAPH_BASE}{self._user_path}/messages/{external_id}"
        resp = httpx.get(url, headers=self._headers(), timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._to_provider_msg(resp.json())

    def get_thread(self, thread_id: str) -> List[ProviderMessage]:
        url = f"{GRAPH_BASE}{self._user_path}/messages"
        params = {"$filter": f"conversationId eq '{thread_id}'", "$orderby": "receivedDateTime asc"}
        resp = httpx.get(url, headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        return [self._to_provider_msg(m) for m in resp.json().get("value", [])]

    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        import base64 as _b64
        url = f"{GRAPH_BASE}{self._user_path}/messages/{message_id}/attachments/{attachment_id}"
        data = self._graph_get(url)
        content = data.get("contentBytes", "")
        return _b64.b64decode(content) if content else b""

    def send_reply(self, to: str, from_addr: str, subject: str, body_text: str, thread_id: Optional[str] = None, cc: Optional[List[str]] = None, attachments: Optional[List[tuple]] = None, body_html: Optional[str] = None, inline_images: Optional[List[tuple]] = None, message_id: Optional[str] = None, in_reply_to: Optional[str] = None, references: Optional[str] = None, thread_index: Optional[str] = None) -> str:
        """Envia resposta via Microsoft Graph e retorna o id da mensagem enviada.
        attachments: lista de (filename, mime_type, bytes)
        inline_images: lista de (filename, mime_type, bytes, cid) para print no corpo
        """
        import base64 as _b64
        subject_str = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        use_html = bool(body_html) or bool(inline_images)
        msg: dict = {
            "subject": subject_str,
            "body": {"contentType": "HTML" if use_html else "Text", "content": body_html if use_html else body_text},
            "toRecipients": [{"emailAddress": {"address": to}}],
        }
        if cc:
            msg["ccRecipients"] = [{"emailAddress": {"address": addr}} for addr in cc]
        graph_attachments = [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": fname,
                "contentType": mime_type,
                "contentBytes": _b64.b64encode(data).decode(),
            }
            for fname, mime_type, data in (attachments or [])
        ]
        for fname, mime_type, data, cid in (inline_images or []):
            graph_attachments.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": fname,
                "contentType": mime_type,
                "contentBytes": _b64.b64encode(data).decode(),
                "isInline": True,
                "contentId": cid,
            })
        if graph_attachments:
            msg["attachments"] = graph_attachments
        # Encadeamento: Graph gerencia a conversa internamente, mas repassamos
        # In-Reply-To/References como cabeçalhos de internet (best-effort).
        headers = []
        if in_reply_to:
            headers.append({"name": "In-Reply-To", "value": in_reply_to})
        if references:
            headers.append({"name": "References", "value": references})
        if headers:
            msg["internetMessageHeaders"] = headers
        body = {"message": msg, "saveToSentItems": True}
        url = f"{GRAPH_BASE}{self._user_path}/sendMail"
        resp = httpx.post(url, headers=self._headers(), json=body, timeout=30)
        resp.raise_for_status()
        return ""
