from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_admin
from app.models.app_config import AppConfig
from app.models.audit_log import AuditLog
from app.models.demand import Demand
from app.models.email_account import EmailAccount
from app.models.user import User
from app.services.audit_service import log_event

router = APIRouter(prefix="/settings", tags=["settings"])


# ── email-provider ──────────────────────────────────────────────────────────

class EmailProviderIn(BaseModel):
    provider: str
    email_address: str


class EmailProviderOut(BaseModel):
    provider: str
    email_address: str
    active: bool


@router.get("/email-provider", response_model=EmailProviderOut)
def get_provider(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    acc = db.query(EmailAccount).filter(EmailAccount.active.is_(True)).order_by(EmailAccount.id.desc()).first()
    if acc:
        return EmailProviderOut(provider=acc.provider, email_address=acc.email_address, active=acc.active)
    return EmailProviderOut(provider=settings.EMAIL_PROVIDER, email_address=settings.CENTRAL_EMAIL, active=True)


@router.post("/email-provider", response_model=EmailProviderOut)
def set_provider(payload: EmailProviderIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    acc = db.query(EmailAccount).filter(EmailAccount.email_address == payload.email_address).first()
    if not acc:
        acc = EmailAccount(provider=payload.provider, email_address=payload.email_address, active=True)
        db.add(acc)
    else:
        acc.provider = payload.provider
        acc.active = True
    db.commit()
    db.refresh(acc)
    return EmailProviderOut(provider=acc.provider, email_address=acc.email_address, active=acc.active)


# ── credentials ─────────────────────────────────────────────────────────────

def _cfg_get(db: Session, key: str) -> Optional[str]:
    row = db.query(AppConfig).filter(AppConfig.key == key).first()
    return row.value if row else None


def _cfg_set(db: Session, key: str, value: str) -> None:
    row = db.query(AppConfig).filter(AppConfig.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppConfig(key=key, value=value))


class GmailCredIn(BaseModel):
    client_id: str
    client_secret: str


class OutlookCredIn(BaseModel):
    client_id: str
    client_secret: str
    tenant_id: Optional[str] = ""


class GmailCredOut(BaseModel):
    client_id: str
    client_secret_set: bool


class OutlookCredOut(BaseModel):
    client_id: str
    client_secret_set: bool
    tenant_id: str


@router.get("/credentials/gmail", response_model=GmailCredOut)
def get_gmail_creds(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    client_id = _cfg_get(db, "gmail_client_id") or settings.GMAIL_CLIENT_ID or ""
    secret = _cfg_get(db, "gmail_client_secret") or settings.GMAIL_CLIENT_SECRET or ""
    return GmailCredOut(client_id=client_id, client_secret_set=bool(secret))


@router.post("/credentials/gmail", response_model=GmailCredOut)
def save_gmail_creds(payload: GmailCredIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    _cfg_set(db, "gmail_client_id", payload.client_id.strip())
    if payload.client_secret.strip():
        _cfg_set(db, "gmail_client_secret", payload.client_secret.strip())
    db.commit()
    secret_set = bool(_cfg_get(db, "gmail_client_secret"))
    return GmailCredOut(client_id=payload.client_id.strip(), client_secret_set=secret_set)


@router.get("/credentials/outlook", response_model=OutlookCredOut)
def get_outlook_creds(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    client_id = _cfg_get(db, "outlook_client_id") or settings.OUTLOOK_CLIENT_ID or ""
    secret = _cfg_get(db, "outlook_client_secret") or settings.OUTLOOK_CLIENT_SECRET or ""
    tenant = _cfg_get(db, "outlook_tenant_id") or settings.OUTLOOK_TENANT_ID or ""
    return OutlookCredOut(client_id=client_id, client_secret_set=bool(secret), tenant_id=tenant)


@router.post("/credentials/outlook", response_model=OutlookCredOut)
def save_outlook_creds(payload: OutlookCredIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    _cfg_set(db, "outlook_client_id", payload.client_id.strip())
    if payload.client_secret.strip():
        _cfg_set(db, "outlook_client_secret", payload.client_secret.strip())
    _cfg_set(db, "outlook_tenant_id", (payload.tenant_id or "").strip())
    db.commit()
    secret_set = bool(_cfg_get(db, "outlook_client_secret"))
    return OutlookCredOut(
        client_id=payload.client_id.strip(),
        client_secret_set=secret_set,
        tenant_id=(payload.tenant_id or "").strip(),
    )


# ── accounts ─────────────────────────────────────────────────────────────────

class AccountOut(BaseModel):
    id: int
    provider: str
    email_address: str
    color: str
    active: bool

    class Config:
        from_attributes = True


class AccountColorIn(BaseModel):
    color: str


@router.get("/accounts", response_model=List[AccountOut])
def list_accounts(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(EmailAccount).filter(EmailAccount.active.is_(True)).order_by(EmailAccount.id).all()


@router.patch("/accounts/{account_id}/color", response_model=AccountOut)
def update_account_color(account_id: int, payload: AccountColorIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    acc = db.query(EmailAccount).filter(EmailAccount.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    color = payload.color.strip()
    if not color.startswith("#") or len(color) not in (4, 7):
        raise HTTPException(status_code=400, detail="Cor inválida (use formato #RRGGBB)")
    acc.color = color
    db.commit()
    db.refresh(acc)
    return acc


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    acc = db.query(EmailAccount).filter(EmailAccount.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    # Coleta IDs das demandas desta conta + demandas sem conta (modo legado/orphãs)
    demand_ids_this = [
        r[0] for r in db.query(Demand.id).filter(Demand.email_account_id == account_id).all()
    ]
    demand_ids_null = [
        r[0] for r in db.query(Demand.id).filter(Demand.email_account_id.is_(None)).all()
    ]
    all_demand_ids = list(set(demand_ids_this + demand_ids_null))
    n_demands = len(all_demand_ids)

    # Remove audit logs vinculados a essas demandas
    if all_demand_ids:
        db.query(AuditLog).filter(AuditLog.demand_id.in_(all_demand_ids)).delete(synchronize_session=False)

    # Remove as demandas (mensagens e anexos caem por CASCADE no banco)
    if demand_ids_this:
        db.query(Demand).filter(Demand.email_account_id == account_id).delete(synchronize_session=False)
    if demand_ids_null:
        db.query(Demand).filter(Demand.email_account_id.is_(None)).delete(synchronize_session=False)

    acc.active = False
    acc.access_token = None
    acc.refresh_token = None
    db.commit()

    log_event(
        db, event_type="OAUTH_DISCONNECTED",
        description=f"{admin.name} desconectou {acc.provider} ({acc.email_address}) e apagou {n_demands} demandas",
        user_id=admin.id, metadata={"provider": acc.provider, "email": acc.email_address, "demands_removed": n_demands},
    )
    return {"ok": True, "demands_removed": n_demands}
