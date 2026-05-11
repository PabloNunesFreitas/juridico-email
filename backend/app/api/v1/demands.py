from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.demand import Bank, Demand, DemandStatus
from app.models.message import Message
from app.models.user import User, UserRole
from app.schemas.demand import AssignIn, DemandDetail, DemandOut, DemandUpdate, ReplyIn, StatusIn
from app.schemas.log import AuditLogOut
from app.models.audit_log import AuditLog
from app.services import demand_service
from app.providers import get_provider_for_account

router = APIRouter(prefix="/demands", tags=["demands"])


def _base_query(db: Session):
    return db.query(Demand).options(joinedload(Demand.assigned_user), joinedload(Demand.email_account))


@router.get("", response_model=List[DemandOut])
def list_demands(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    status: Optional[DemandStatus] = None,
    bank: Optional[Bank] = None,
    assigned_user_id: Optional[int] = None,
    email_account_id: Optional[int] = None,
    unassigned: bool = False,
    q: Optional[str] = Query(None, description="Busca por remetente, cliente ou assunto"),
):
    query = _base_query(db)
    if user.role != UserRole.ADMIN:
        query = query.filter(Demand.assigned_user_id == user.id)
    if status:
        query = query.filter(Demand.status == status)
    if bank:
        query = query.filter(Demand.bank == bank)
    if unassigned:
        query = query.filter(Demand.assigned_user_id.is_(None))
    elif assigned_user_id is not None:
        query = query.filter(Demand.assigned_user_id == assigned_user_id)
    if email_account_id is not None:
        query = query.filter(Demand.email_account_id == email_account_id)
    if q:
        query = _apply_search(query, q)
    return query.order_by(Demand.last_message_at.desc()).limit(2000).all()


def _apply_search(query, q: str):
    """Busca em sender, cliente, assunto, NUP e corpo (body_text) das mensagens."""
    like = f"%{q.lower()}%"
    # Subquery para encontrar demandas com mensagens cujo corpo bate com o termo
    body_match_demand_ids = (
        Message.__table__.select()
        .with_only_columns(Message.demand_id)
        .where(Message.body_text.ilike(like))
        .distinct()
    )
    return query.filter(
        Demand.sender_email.ilike(like)
        | Demand.sender_name.ilike(like)
        | Demand.client_name.ilike(like)
        | Demand.subject.ilike(like)
        | Demand.nup.ilike(like)
        | Demand.id.in_(body_match_demand_ids)
    )


@router.get("/my", response_model=List[DemandOut])
def my_demands(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    q: Optional[str] = Query(None),
    status: Optional[DemandStatus] = None,
):
    query = _base_query(db).filter(Demand.assigned_user_id == user.id)
    if status:
        query = query.filter(Demand.status == status)
    if q:
        query = _apply_search(query, q)
    return query.order_by(Demand.last_message_at.desc()).limit(2000).all()


@router.get("/unassigned", response_model=List[DemandOut])
def unassigned_demands(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    q: Optional[str] = Query(None),
    status: Optional[DemandStatus] = None,
):
    query = _base_query(db).filter(Demand.assigned_user_id.is_(None))
    if status:
        query = query.filter(Demand.status == status)
    if q:
        query = _apply_search(query, q)
    return query.order_by(Demand.last_message_at.desc()).limit(2000).all()


@router.get("/{demand_id}", response_model=DemandDetail)
def get_demand(demand_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    demand = _base_query(db).options(joinedload(Demand.messages)).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    if user.role != UserRole.ADMIN and demand.assigned_user_id not in (None, user.id):
        raise HTTPException(status_code=403, detail="Sem permissão para esta demanda")
    return demand


@router.patch("/{demand_id}", response_model=DemandOut)
def update_demand(demand_id: int, payload: DemandUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    if user.role != UserRole.ADMIN and demand.assigned_user_id != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(demand, field, value)
    db.commit()
    db.refresh(demand)
    return demand


@router.patch("/{demand_id}/assign", response_model=DemandOut)
def assign(
    demand_id: int,
    payload: AssignIn,
    bulk: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Atribui demanda. Se bulk=true, tambem atribui todas as outras demandas do
    mesmo remetente que estejam sem responsavel (ou ja com este mesmo usuario).
    Demandas atribuidas a outros usuarios sao mantidas como estao."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Apenas admins podem atribuir")
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    target = db.query(User).filter(User.id == payload.user_id, User.active.is_(True)).first()
    if not target:
        raise HTTPException(status_code=404, detail="Usuário inválido")
    return demand_service.assign_demand(db, demand, target, user, bulk=bulk)


@router.post("/{demand_id}/unassign", response_model=DemandOut)
def unassign(demand_id: int, keep_rule: bool = False, bulk: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Remove o responsavel da demanda (volta para 'Nao atribuidas'). Apenas admin.
    Por padrao remove tambem a regra de continuidade do remetente.
    Use ?keep_rule=true para manter a regra.
    Use ?bulk=true para remover responsavel de todas as demandas do mesmo remetente."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Apenas admins podem remover responsaveis")
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda nao encontrada")
    if demand.assigned_user_id is None:
        raise HTTPException(status_code=400, detail="Demanda ja esta sem responsavel")
    return demand_service.unassign_demand(db, demand, user, remove_rule=not keep_rule, bulk=bulk)


@router.post("/{demand_id}/assume", response_model=DemandOut)
def assume(demand_id: int, bulk: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    try:
        return demand_service.assume_demand(db, demand, user, bulk=bulk)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{demand_id}/status", response_model=DemandOut)
def change_status(demand_id: int, payload: StatusIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    if user.role != UserRole.ADMIN and demand.assigned_user_id != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para alterar status")
    return demand_service.change_status(db, demand, payload.status, user)


@router.post("/{demand_id}/reply", response_model=DemandDetail)
def reply_demand(
    demand_id: int,
    payload: ReplyIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Envia resposta por e-mail ao remetente da demanda."""
    demand = (
        _base_query(db)
        .options(joinedload(Demand.messages))
        .filter(Demand.id == demand_id)
        .first()
    )
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    if user.role != UserRole.ADMIN and demand.assigned_user_id != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para responder esta demanda")
    if not demand.email_account:
        raise HTTPException(status_code=400, detail="Demanda sem conta de e-mail associada — não é possível enviar resposta")

    provider = get_provider_for_account(demand.email_account)
    from_addr = demand.email_account.email_address
    subject = demand.subject or ""

    try:
        ext_id = provider.send_reply(
            to=demand.sender_email,
            from_addr=from_addr,
            subject=subject,
            body_text=payload.body_text,
            thread_id=demand.external_thread_id or None,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falha ao enviar e-mail: {e}")

    now = datetime.utcnow()
    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    msg = Message(
        demand_id=demand.id,
        external_message_id=ext_id,
        direction="out",
        sender_email=from_addr,
        sender_name=None,
        subject=reply_subject,
        body_text=payload.body_text,
        body_html=None,
        received_at=now,
        has_attachments=False,
    )
    db.add(msg)
    demand.last_message_at = now
    db.commit()

    return (
        _base_query(db)
        .options(joinedload(Demand.messages))
        .filter(Demand.id == demand_id)
        .first()
    )


@router.get("/{demand_id}/logs", response_model=List[AuditLogOut])
def demand_logs(demand_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    if user.role != UserRole.ADMIN and demand.assigned_user_id != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão")
    return db.query(AuditLog).filter(AuditLog.demand_id == demand_id).order_by(AuditLog.created_at.desc()).all()
