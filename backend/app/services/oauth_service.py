"""
Fluxo OAuth para Gmail/Outlook iniciado pelo próprio sistema.

start(provider, base_url, db, client_id_override, client_secret_override) -> URL de autorização
callback(db, code, state, base_url) -> troca code por tokens e persiste em email_accounts
"""
import secrets
import urllib.parse
from typing import List, Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.app_config import AppConfig
from app.models.email_account import EmailAccount

# State em memória: mapeia state -> {provider, client_id, client_secret}
_PENDING: dict[str, dict] = {}


# ── credential helpers ───────────────────────────────────────────────────────

def _cfg(db: Session, key: str, env_fallback: str = "") -> str:
    row = db.query(AppConfig).filter(AppConfig.key == key).first()
    return (row.value or "") if (row and row.value) else (env_fallback or "")


def _gmail_client_id(db: Session) -> str:
    return _cfg(db, "gmail_client_id", settings.GMAIL_CLIENT_ID)


def _gmail_client_secret(db: Session) -> str:
    return _cfg(db, "gmail_client_secret", settings.GMAIL_CLIENT_SECRET)


def _outlook_client_id(db: Session) -> str:
    return _cfg(db, "outlook_client_id", settings.OUTLOOK_CLIENT_ID)


def _outlook_client_secret(db: Session) -> str:
    return _cfg(db, "outlook_client_secret", settings.OUTLOOK_CLIENT_SECRET)


def _outlook_tenant(db: Session) -> str:
    return _cfg(db, "outlook_tenant_id", settings.OUTLOOK_TENANT_ID) or "common"


# ── URL builders ─────────────────────────────────────────────────────────────

def _redirect_uri(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/api/v1/email/oauth/callback"


def _gmail_auth_url(state: str, base_url: str, client_id: str) -> str:
    if not client_id:
        raise RuntimeError("GMAIL_CLIENT_ID não configurado. Preencha em Configurações → Gmail.")
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": _redirect_uri(base_url),
        "scope": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def _outlook_auth_url(state: str, base_url: str, client_id: str, tenant: str) -> str:
    if not client_id:
        raise RuntimeError("OUTLOOK_CLIENT_ID não configurado. Preencha em Configurações → Outlook.")
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": _redirect_uri(base_url),
        "response_mode": "query",
        "scope": "Mail.Read Mail.Send offline_access User.Read",
        "prompt": "consent",
        "state": state,
    }
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?" + urllib.parse.urlencode(params)


# ── public API ────────────────────────────────────────────────────────────────

def start(
    provider: str,
    base_url: str,
    db: Session,
    client_id_override: Optional[str] = None,
    client_secret_override: Optional[str] = None,
) -> str:
    state = secrets.token_urlsafe(24)

    if provider == "gmail":
        client_id = client_id_override or _gmail_client_id(db)
        client_secret = client_secret_override or _gmail_client_secret(db)
        _PENDING[state] = {"provider": provider, "client_id": client_id, "client_secret": client_secret}
        return _gmail_auth_url(state, base_url, client_id)

    if provider == "outlook":
        client_id = client_id_override or _outlook_client_id(db)
        client_secret = client_secret_override or _outlook_client_secret(db)
        tenant = _outlook_tenant(db)
        _PENDING[state] = {"provider": provider, "client_id": client_id, "client_secret": client_secret}
        return _outlook_auth_url(state, base_url, client_id, tenant)

    raise ValueError(f"Provider não suportado: {provider}")


def _exchange_gmail(code: str, base_url: str, client_id: str, client_secret: str) -> dict:
    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": _redirect_uri(base_url),
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _exchange_outlook(code: str, base_url: str, client_id: str, client_secret: str, tenant: str) -> dict:
    resp = httpx.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": _redirect_uri(base_url),
            "grant_type": "authorization_code",
            "scope": "Mail.Read Mail.Send offline_access User.Read",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _userinfo_email(provider: str, access_token: str) -> Optional[str]:
    try:
        if provider == "gmail":
            r = httpx.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                headers={"Authorization": f"Bearer {access_token}"}, timeout=15,
            )
            if r.status_code == 200:
                return r.json().get("emailAddress")
        else:
            r = httpx.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}"}, timeout=15,
            )
            if r.status_code == 200:
                d = r.json()
                return d.get("mail") or d.get("userPrincipalName")
    except Exception:
        pass
    return None


def callback(db: Session, code: str, state: str, base_url: str) -> EmailAccount:
    pending = _PENDING.pop(state, None)
    if not pending:
        raise ValueError("State inválido ou expirado")

    provider = pending["provider"]
    client_id = pending["client_id"]
    client_secret = pending["client_secret"]

    if provider == "gmail":
        tokens = _exchange_gmail(code, base_url, client_id, client_secret)
    elif provider == "outlook":
        from app.core.database import SessionLocal
        db2 = SessionLocal()
        try:
            tenant = _outlook_tenant(db2)
        finally:
            db2.close()
        tokens = _exchange_outlook(code, base_url, client_id, client_secret, tenant)
    else:
        raise ValueError(f"Provider não suportado: {provider}")

    refresh = tokens.get("refresh_token")
    access = tokens.get("access_token")
    if not refresh:
        raise RuntimeError(
            "Resposta sem refresh_token. "
            "Para Gmail garanta access_type=offline e prompt=consent; "
            "para Outlook garanta scope offline_access."
        )

    email = _userinfo_email(provider, access) or settings.CENTRAL_EMAIL

    acc = db.query(EmailAccount).filter(
        EmailAccount.provider == provider,
        EmailAccount.email_address == email,
    ).first()
    if not acc:
        acc = EmailAccount(provider=provider, email_address=email, active=True)
        db.add(acc)

    acc.access_token = access
    acc.refresh_token = refresh
    acc.active = True
    # Armazena override de credenciais apenas quando diferente do padrão AppConfig
    acc.client_id_override = client_id
    acc.client_secret_override = client_secret
    db.commit()
    db.refresh(acc)
    return acc


def get_active_accounts(db: Session, provider: str) -> List[EmailAccount]:
    return (
        db.query(EmailAccount)
        .filter(EmailAccount.provider == provider, EmailAccount.active.is_(True))
        .order_by(EmailAccount.id)
        .all()
    )


def get_active_token(db: Session, provider: str) -> Optional[str]:
    """Retorna o refresh_token da conta mais recente ativa (compat. legada)."""
    acc = (
        db.query(EmailAccount)
        .filter(EmailAccount.provider == provider, EmailAccount.active.is_(True))
        .order_by(EmailAccount.id.desc())
        .first()
    )
    return acc.refresh_token if acc else None
