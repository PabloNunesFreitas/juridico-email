from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_admin
from app.core.encryption import encrypt_password
from app.models.app_config import AppConfig
from app.models.audit_log import AuditLog
from app.models.comment import Comment
from app.models.demand import Demand
from app.models.demand_share import DemandShare
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


@router.post("/accounts/imap", response_model=AccountOut)
def add_imap_account(payload: IMAPAccountIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Adiciona uma conta IMAP/SMTP (ex: mail.acl.com.br)."""
    # Verifica se já existe
    existing = db.query(EmailAccount).filter(
        EmailAccount.email_address == payload.email_address,
        EmailAccount.provider == "imap"
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Esta conta IMAP já foi adicionada")

    # Cria nova conta
    acc = EmailAccount(
        provider="imap",
        email_address=payload.email_address,
        imap_host=payload.imap_host,
        imap_port=payload.imap_port,
        smtp_host=payload.smtp_host,
        smtp_port=payload.smtp_port,
        password=encrypt_password(payload.password),
        color=payload.color,
        active=True,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


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
    needs_reconnect: bool = False

    class Config:
        from_attributes = True


class IMAPAccountIn(BaseModel):
    email_address: str
    password: str
    imap_host: str = "mail.acl.com.br"
    imap_port: int = 993
    smtp_host: str = "mail.acl.com.br"
    smtp_port: int = 587
    color: str = "#6366f1"


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


def _split_demands_by_activity(db: Session, demand_ids: list[int]):
    """Separa demandas em dois grupos:
    - 'safe_to_delete': sem movimentação alguma (apagar é seguro)
    - 'keep': tiveram movimentação — serão desvinculadas, não apagadas

    Uma demanda é considerada "movimentada" se qualquer uma destas condições for verdadeira:
      - assigned_user_id IS NOT NULL  (advogado atribuído)
      - folder_id IS NOT NULL         (movida para pasta)
      - archived = True               (arquivada)
      - status != 'Caixa de Entrada'  (status alterado manualmente)
      - tem ao menos um comentário
      - tem ao menos um compartilhamento
    """
    if not demand_ids:
        return [], []

    # Demandas com movimentação por campos próprios
    moved_ids = {
        r[0] for r in db.query(Demand.id).filter(
            Demand.id.in_(demand_ids),
            (
                (Demand.assigned_user_id.isnot(None)) |
                (Demand.folder_id.isnot(None)) |
                (Demand.archived.is_(True)) |
                (Demand.status != "Caixa de Entrada")
            )
        ).all()
    }

    # Demandas com comentários
    commented_ids = {
        r[0] for r in db.query(Comment.demand_id).filter(
            Comment.demand_id.in_(demand_ids)
        ).distinct().all()
    }

    # Demandas com compartilhamentos
    shared_ids = {
        r[0] for r in db.query(DemandShare.demand_id).filter(
            DemandShare.demand_id.in_(demand_ids)
        ).distinct().all()
    }

    keep_ids = moved_ids | commented_ids | shared_ids
    safe_to_delete = [d for d in demand_ids if d not in keep_ids]
    keep = [d for d in demand_ids if d in keep_ids]
    return safe_to_delete, keep


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    acc = db.query(EmailAccount).filter(EmailAccount.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Conta não encontrada")

    # Coleta IDs de todas as demandas desta conta
    all_demand_ids = [
        r[0] for r in db.query(Demand.id).filter(Demand.email_account_id == account_id).all()
    ]

    # Separa demandas que podem ser apagadas das que têm movimentação
    safe_to_delete, keep_ids = _split_demands_by_activity(db, all_demand_ids)

    # Desvincula demandas com movimentação (preserva dados, remove apenas o vínculo com a conta)
    if keep_ids:
        db.query(Demand).filter(Demand.id.in_(keep_ids)).update(
            {"email_account_id": None}, synchronize_session=False
        )

    # Remove audit logs apenas das demandas seguras para apagar
    if safe_to_delete:
        db.query(AuditLog).filter(AuditLog.demand_id.in_(safe_to_delete)).delete(synchronize_session=False)
        db.query(Demand).filter(Demand.id.in_(safe_to_delete)).delete(synchronize_session=False)

    acc.active = False
    acc.access_token = None
    acc.refresh_token = None
    db.commit()

    log_event(
        db, event_type="OAUTH_DISCONNECTED",
        description=(
            f"{admin.name} desconectou {acc.provider} ({acc.email_address}): "
            f"{len(safe_to_delete)} demandas apagadas, {len(keep_ids)} preservadas (com movimentação)"
        ),
        user_id=admin.id,
        metadata={
            "provider": acc.provider,
            "email": acc.email_address,
            "demands_removed": len(safe_to_delete),
            "demands_preserved": len(keep_ids),
        },
    )
    return {
        "ok": True,
        "demands_removed": len(safe_to_delete),
        "demands_preserved": len(keep_ids),
    }
