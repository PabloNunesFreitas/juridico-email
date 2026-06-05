from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_user, require_admin
from app.models.audit_log import AuditLog
from app.models.demand import Demand
from app.models.email_account import EmailAccount
from app.models.message import Message
from app.models.user import User
from app.schemas.demand import MessageOut
from app.services import oauth_service
from app.services.audit_service import log_event
from app.services.email_sync_service import sync_inbox
from app.services.sync_state import SYNC_STATE

router = APIRouter(prefix="/email", tags=["email"])


@router.post("/sync")
def sync(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    try:
        return sync_inbox(db, actor=admin)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falha ao sincronizar: {e}")


@router.get("/sync/status")
def sync_status(_: User = Depends(get_current_user)):
    """Snapshot in-memory do progresso atual da sincronização."""
    return SYNC_STATE.snapshot()


@router.get("/messages", response_model=List[MessageOut])
def list_messages(db: Session = Depends(get_db), _: User = Depends(get_current_user), limit: int = 100):
    return db.query(Message).order_by(Message.received_at.desc()).limit(limit).all()


@router.get("/messages/{message_id}", response_model=MessageOut)
def get_message(message_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")
    return msg


class OAuthStartIn(BaseModel):
    provider: str  # "gmail" | "outlook"
    client_id_override: Optional[str] = None
    client_secret_override: Optional[str] = None


class OAuthStartOut(BaseModel):
    authorize_url: str


def _public_base_url(request: Request) -> str:
    """URL base que o navegador usa para chamar o backend.
    Lida com proxy reverso via X-Forwarded headers; em PoC com Docker,
    usamos o Host enviado pelo navegador (ex.: localhost:8001)."""
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}"
    host = request.headers.get("host") or "localhost:8001"
    scheme = request.url.scheme or "http"
    return f"{scheme}://{host}"


@router.post("/oauth/start", response_model=OAuthStartOut)
def oauth_start(payload: OAuthStartIn, request: Request, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    try:
        url = oauth_service.start(
            payload.provider, _public_base_url(request), db,
            client_id_override=payload.client_id_override or None,
            client_secret_override=payload.client_secret_override or None,
        )
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return OAuthStartOut(authorize_url=url)


def _sync_in_background() -> None:
    """Roda sync_inbox em sessão própria (chamado via BackgroundTasks)."""
    db = SessionLocal()
    try:
        sync_inbox(db)
    except Exception:
        pass
    finally:
        db.close()


@router.get("/oauth/callback", response_class=HTMLResponse)
def oauth_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    error_description: str = Query(None),
):
    """Endpoint público (sem auth): provider OAuth precisa redirecionar pra cá.
    Segurança: state foi gerado no /start e é consumido aqui."""
    if error:
        return HTMLResponse(f"<h2>Erro OAuth: {error}</h2><p>{error_description or ''}</p>", status_code=400)
    if not code or not state:
        return HTMLResponse("<h2>Callback sem code/state</h2>", status_code=400)
    try:
        acc = oauth_service.callback(db, code=code, state=state, base_url=_public_base_url(request))
    except Exception as e:
        return HTMLResponse(f"<h2>Falha ao trocar tokens</h2><pre>{e}</pre>", status_code=400)
    # Reconexão bem-sucedida: limpa flag de reconexão necessária
    if acc.needs_reconnect:
        acc.needs_reconnect = False
        db.commit()
    log_event(db, event_type="OAUTH_CONNECTED", description=f"Conta {acc.provider} conectada: {acc.email_address}", metadata={"provider": acc.provider, "email": acc.email_address})
    # Dispara sync inicial em background — popup fecha imediatamente
    background_tasks.add_task(_sync_in_background)
    return HTMLResponse(
        f"""
        <html><body style='font-family:sans-serif;text-align:center;padding:40px'>
            <h2>✅ Conta {acc.provider} conectada</h2>
            <p>{acc.email_address}</p>
            <p>Sincronizando e-mails em segundo plano...</p>
            <p style='color:#666;font-size:13px'>Você pode fechar esta janela.</p>
            <script>setTimeout(()=>window.close(), 2000);</script>
        </body></html>
        """
    )


@router.post("/oauth/disconnect")
def oauth_disconnect(provider: str = Query(...), db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Desconecta o provider e apaga todos os dados sincronizados (demandas,
    mensagens, anexos, regras de atribuição, logs vinculados)."""
    if provider not in ("gmail", "outlook"):
        raise HTTPException(status_code=400, detail="Provider inválido")

    # Coleta apenas as contas e demandas do provider específico
    accounts = db.query(EmailAccount).filter(EmailAccount.provider == provider).all()
    account_ids = [a.id for a in accounts]

    demand_ids = [
        r[0] for r in db.query(Demand.id).filter(Demand.email_account_id.in_(account_ids)).all()
    ] if account_ids else []
    n_demands = len(demand_ids)

    # Limpa logs vinculados apenas a essas demandas
    if demand_ids:
        db.query(AuditLog).filter(AuditLog.demand_id.in_(demand_ids)).delete(synchronize_session=False)
        db.query(Demand).filter(Demand.email_account_id.in_(account_ids)).delete(synchronize_session=False)

    # Marca contas do provider como inativas e remove tokens
    for acc in accounts:
        acc.active = False
        acc.access_token = None
        acc.refresh_token = None
    db.commit()

    log_event(
        db, event_type="OAUTH_DISCONNECTED",
        description=f"{admin.name} desconectou {provider} e apagou {n_demands} demandas",
        user_id=admin.id, metadata={"provider": provider, "demands_removed": n_demands},
    )
    return {"ok": True, "demands_removed": n_demands}


class ConnectedAccountOut(BaseModel):
    provider: str
    email_address: str
    connected: bool


@router.get("/oauth/status", response_model=ConnectedAccountOut)
def oauth_status(provider: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    token = oauth_service.get_active_token(db, provider)
    if token:
        from app.models.email_account import EmailAccount
        acc = db.query(EmailAccount).filter(EmailAccount.provider == provider, EmailAccount.active.is_(True)).order_by(EmailAccount.id.desc()).first()
        return ConnectedAccountOut(provider=provider, email_address=acc.email_address if acc else "", connected=True)
    return ConnectedAccountOut(provider=provider, email_address="", connected=False)
