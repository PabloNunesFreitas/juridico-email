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
        if self._token:
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
            data["scope"] = "https://graph.microsoft.com/Mail.Read offline_access User.Read"
        else:
            data["grant_type"] = "client_credentials"
            data["scope"] = "https://graph.microsoft.com/.default"
        resp = httpx.post(url, data=data, timeout=30)
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
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

    def list_message_ids(self, since: Optional[datetime] = None, limit: int = 5000) -> List[str]:
        ids: List[str] = []
        url = f"{GRAPH_BASE}{self._user_path}/messages"
        params: dict = {"$top": "1000", "$select": "id", "$orderby": "receivedDateTime desc"}
        if since:
            params["$filter"] = f"receivedDateTime ge {since.isoformat()}Z"
        next_link: Optional[str] = None
        while len(ids) < limit:
            resp = httpx.get(next_link or url, headers=self._headers(), params=None if next_link else params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
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
