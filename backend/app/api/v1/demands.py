from datetime import datetime
from typing import List, Optional

import json
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.comment import Comment
from app.models.demand import Bank, Demand, DemandStatus
from app.models.demand_share import DemandShare
from app.models.folder import Folder
from app.models.message import Message
from app.models.attachment import Attachment
from app.models.notification import Notification
from app.models.user import User, UserRole
from app.schemas.demand import AssignIn, CoAssigneeOut, ComposeIn, CommentOut, DemandDetail, DemandOut, DemandUpdate, ReplyIn, StatusIn
from app.services.audit_service import log_event

import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _clean_recipients(emails, campo: str = "Para") -> List[str]:
    """Valida/normaliza destinatários antes do envio.

    Lança HTTP 400 com mensagem clara (em vez de deixar o SMTP estourar um
    erro técnico) quando algum endereço está vazio ou malformado.
    """
    limpos: List[str] = []
    for raw in (emails or []):
        # Aceita vários endereços colados no mesmo campo (vírgula ou ponto-e-vírgula)
        for parte in re.split(r"[,;]", raw or ""):
            addr = parte.strip()
            if not addr:
                continue
            if "\n" in addr or "\r" in addr or not _EMAIL_RE.match(addr):
                raise HTTPException(
                    status_code=400,
                    detail=f"Endereço de e-mail inválido no campo {campo}: “{addr}”. "
                           f"Confira se está escrito corretamente (ex.: nome@dominio.com), "
                           f"sem espaços sobrando.",
                )
            limpos.append(addr)
    return limpos


import html as _html

_MAX_INLINE_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB por print


async def _read_inline_images(files) -> list:
    """Lê os prints (UploadFile de imagem) e devolve (filename, mime, bytes, cid)."""
    out = []
    for i, f in enumerate(files or []):
        content = await f.read()
        if not content:
            continue
        mime = (f.content_type or "").lower() or "image/png"
        if not mime.startswith("image/"):
            raise HTTPException(
                status_code=400,
                detail=f"O arquivo “{f.filename or 'sem nome'}” não é uma imagem — só dá para inserir imagens no corpo.",
            )
        if len(content) > _MAX_INLINE_IMAGE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"A imagem “{f.filename or 'print'}” é muito grande (máx. 10 MB).",
            )
        out.append((f.filename or f"print{i}.png", mime, content, f"print{i}@juridico"))
    return out


def _build_html_body(body_text: str, inline: list) -> str:
    """Monta o corpo em HTML a partir do texto digitado + prints embutidos (cid)."""
    esc = _html.escape(body_text or "").replace("\r\n", "\n").replace("\n", "<br>")
    parts = [f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px">{esc}</div>']
    for (_fn, _mt, _data, cid) in inline:
        parts.append(f'<div style="margin-top:12px"><img src="cid:{cid}" style="max-width:100%;height:auto" /></div>')
    return "".join(parts)


from email.utils import make_msgid


def _domain_of(addr: str) -> str:
    return ((addr or "").split("@")[-1] or "juridico").strip() or "juridico"


def _pick_reply_target(demand):
    """Mensagem à qual a resposta se encadeia: a mais recente recebida (com
    external_message_id); se não houver recebida, a mais recente qualquer."""
    msgs = [m for m in (demand.messages or []) if m.external_message_id]
    if not msgs:
        return None
    inbound = [m for m in msgs if (m.direction or "in") == "in"]
    pool = inbound or msgs
    return max(pool, key=lambda m: m.received_at)


def _child_thread_index(parent_b64):
    """Estende o Thread-Index do e-mail original com um bloco de 5 bytes,
    tornando a resposta um "filho" da mesma conversa no Outlook. Devolve None
    se não houver Thread-Index no original ou se algo falhar."""
    if not parent_b64:
        return None
    try:
        import base64 as _b64, struct as _struct, time as _time
        raw = _b64.b64decode(parent_b64)
        if len(raw) < 22:  # cabeçalho válido tem no mínimo 22 bytes
            return None
        block = _struct.pack(">IB", int(_time.time()) & 0xFFFFFFFF, 0)  # 5 bytes
        return _b64.b64encode(raw + block).decode("ascii")
    except Exception:
        return None


def _strip_html_to_text(html_str: str) -> str:
    if not html_str:
        return ""
    import re as _re
    t = _re.sub(r"(?is)<(script|style).*?</\1>", "", html_str)
    t = _re.sub(r"(?is)<br\s*/?>", "\n", t)
    t = _re.sub(r"(?is)</p>|</div>", "\n", t)
    t = _re.sub(r"(?is)<[^>]+>", "", t)
    return _html.unescape(t).strip()


def _quote_target(demand):
    """Mensagem a ser citada na resposta: a mais recente da conversa com corpo."""
    msgs = [m for m in (demand.messages or []) if (m.body_text or m.body_html)]
    if not msgs:
        return None
    return max(msgs, key=lambda m: m.received_at)


def _build_reply_bodies(demand, new_text: str, inline: list):
    """Monta (texto, html) da resposta incluindo o histórico citado (estilo
    Outlook). Se não houver o que citar, devolve o texto simples (e html só se
    houver print embutido)."""
    new_html = _build_html_body(new_text, inline)
    t = _quote_target(demand)
    if not t:
        return new_text, (new_html if inline else None)
    when = t.received_at.strftime("%d/%m/%Y %H:%M") if t.received_at else ""
    who_p = f"{t.sender_name} <{t.sender_email}>" if t.sender_name else (t.sender_email or "")
    # HTML citado
    who_h = (f"{_html.escape(t.sender_name)} &lt;{_html.escape(t.sender_email or '')}&gt;"
             if t.sender_name else _html.escape(t.sender_email or ""))
    orig_html = t.body_html or ("<div>" + _html.escape(t.body_text or "").replace("\n", "<br>") + "</div>")
    quote_html = (
        '<div style="border-top:1px solid #ccc;margin-top:16px;padding-top:8px;font-family:Arial,Helvetica,sans-serif;font-size:14px">'
        f"<b>De:</b> {who_h}<br><b>Enviada em:</b> {when}<br>"
        f"<b>Para:</b> {_html.escape(t.recipient_emails or '')}<br>"
        f"<b>Assunto:</b> {_html.escape(t.subject or '')}</div><br>"
        f"{orig_html}"
    )
    send_html = new_html + quote_html
    # Texto citado
    orig_text = t.body_text or _strip_html_to_text(t.body_html)
    quote_text = (
        "\n\n________________________________\n"
        f"De: {who_p}\nEnviada em: {when}\n"
        f"Para: {t.recipient_emails or ''}\nAssunto: {t.subject or ''}\n\n"
        f"{orig_text or ''}"
    )
    send_text = (new_text or "") + quote_text
    return send_text, send_html


def _thread_headers_for_reply(provider, demand, from_addr):
    """Best-effort: gera Message-ID próprio e busca In-Reply-To/References/
    Thread-Index do e-mail original para encadear a resposta no Outlook/Gmail.
    Nunca lança — se falhar, devolve só o Message-ID e o envio segue sem encadear."""
    message_id = make_msgid(domain=_domain_of(from_addr))
    in_reply_to = None
    references = None
    thread_index = None
    try:
        target = _pick_reply_target(demand)
        getter = getattr(provider, "get_thread_headers", None)
        if target and getter:
            h = getter(target.external_message_id) or {}
            parent = h.get("message_id")
            if parent:
                in_reply_to = parent
                chain = h.get("references")
                references = f"{chain} {parent}" if chain else parent
            thread_index = _child_thread_index(h.get("thread_index"))
    except Exception:
        pass
    return message_id, in_reply_to, references, thread_index


def _friendly_send_error(e: Exception) -> str:
    """Traduz erros de envio SMTP para uma mensagem que o usuário entende."""
    txt = str(e).lower()
    if "501" in txt or "5.1.3" in txt or "recipient" in txt or "destinat" in txt:
        return ("O servidor de e-mail recusou o destinatário. "
                "Verifique se todos os endereços em Para/Cc estão corretos.")
    if "550" in txt or "554" in txt or "5.1.1" in txt:
        return ("O servidor de e-mail recusou a mensagem — o destinatário pode "
                "não existir ou estar bloqueado. Confira o endereço.")
    if "535" in txt or "auth" in txt:
        return "Falha de autenticação na conta de e-mail. Avise o administrador."
    return "Não foi possível enviar o e-mail. Tente novamente ou avise o administrador."


class CommentIn(BaseModel):
    content: str
    mentions: List[int] = []

class ShareIn(BaseModel):
    user_id: int
    note: Optional[str] = None
from app.schemas.log import AuditLogOut
from app.models.audit_log import AuditLog
from app.services import demand_service
from app.providers import get_provider_for_account

router = APIRouter(prefix="/demands", tags=["demands"])


def _base_query(db: Session):
    return db.query(Demand).options(joinedload(Demand.assigned_user), joinedload(Demand.email_account))


def _co_assignees(db: Session, demand_id: int) -> List[CoAssigneeOut]:
    from app.schemas.demand import UserMini
    rows = db.query(DemandShare).filter(
        DemandShare.demand_id == demand_id, DemandShare.is_co_assignee == True  # noqa: E712
    ).all()
    return [CoAssigneeOut(share_id=r.id, user=UserMini(id=r.shared_with.id, name=r.shared_with.name, email=r.shared_with.email)) for r in rows]


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
    query = _base_query(db).filter(Demand.archived == False)  # noqa: E712
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


@router.get("/stats")
def demands_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Contagens reais (COUNT) para o dashboard — sem o limite de 2000 da listagem."""
    base = db.query(Demand).filter(Demand.archived == False)  # noqa: E712
    if user.role != UserRole.ADMIN:
        base = base.filter(Demand.assigned_user_id == user.id)
    total = base.count()
    unassigned = base.filter(Demand.assigned_user_id.is_(None)).count()

    sq = db.query(Demand.status, func.count(Demand.id)).filter(Demand.archived == False)  # noqa: E712
    if user.role != UserRole.ADMIN:
        sq = sq.filter(Demand.assigned_user_id == user.id)
    by_status = {(s.value if hasattr(s, "value") else str(s)): c for s, c in sq.group_by(Demand.status).all()}
    return {"total": total, "unassigned": unassigned, "by_status": by_status}


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
    query = _base_query(db).filter(Demand.assigned_user_id == user.id, Demand.archived == False, Demand.folder_id.is_(None))  # noqa: E712
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
    query = _base_query(db).filter(Demand.assigned_user_id.is_(None), Demand.archived == False)  # noqa: E712
    if status:
        query = query.filter(Demand.status == status)
    if q:
        query = _apply_search(query, q)
    return query.order_by(Demand.last_message_at.desc()).limit(2000).all()


@router.get("/shared", response_model=List[DemandOut])
def shared_demands(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ids = [r[0] for r in db.query(DemandShare.demand_id).filter(DemandShare.shared_with_id == user.id).all()]
    if not ids:
        return []
    return _base_query(db).filter(Demand.id.in_(ids), Demand.archived == False).order_by(Demand.last_message_at.desc()).all()  # noqa: E712


@router.get("/archived-count")
def archived_count(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    count = db.query(Demand).filter(Demand.archived == True).count()  # noqa: E712
    return {"count": count}


@router.get("/archived", response_model=List[DemandOut])
def list_archived(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    q: Optional[str] = Query(None),
):
    query = _base_query(db).filter(Demand.archived == True)  # noqa: E712
    if q:
        query = _apply_search(query, q)
    return query.order_by(Demand.last_message_at.desc()).limit(2000).all()


@router.get("/{demand_id}", response_model=DemandDetail)
def get_demand(demand_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    demand = (
        _base_query(db)
        .options(joinedload(Demand.messages).joinedload(Message.attachments))
        .filter(Demand.id == demand_id)
        .first()
    )
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    if user.role != UserRole.ADMIN and demand.assigned_user_id not in (None, user.id):
        shared = db.query(DemandShare).filter(
            DemandShare.demand_id == demand_id, DemandShare.shared_with_id == user.id
        ).first()
        if not shared:
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
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    # Qualquer usuário pode atribuir uma demanda livre ou já dele (inclusive a um
    # colega), mas não pode "roubar" uma demanda que já é de outra pessoa — isso
    # só o admin faz. (O modo bulk em assign_demand já ignora demandas de terceiros.)
    if user.role != UserRole.ADMIN and demand.assigned_user_id not in (None, user.id):
        raise HTTPException(status_code=403, detail="Esta demanda já está com outro responsável — só o admin pode transferi-la.")
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
async def reply_demand(
    demand_id: int,
    body_text: str = Form(...),
    to_emails: str = Form("[]"),
    cc: str = Form("[]"),
    files: List[UploadFile] = File(default=[]),
    inline_images: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Envia resposta por e-mail ao remetente da demanda."""
    payload = ReplyIn(
        body_text=body_text,
        to_emails=json.loads(to_emails) or None,
        cc=json.loads(cc),
    )
    demand = (
        _base_query(db)
        .options(joinedload(Demand.messages))
        .filter(Demand.id == demand_id)
        .first()
    )
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    # Admin, responsável OU quem tem a demanda compartilhada pode responder
    # (mesma regra do comentário/compartilhamento — quem colabora consegue responder).
    if user.role != UserRole.ADMIN and demand.assigned_user_id != user.id:
        shared = db.query(DemandShare).filter(
            DemandShare.demand_id == demand_id, DemandShare.shared_with_id == user.id
        ).first()
        if not shared:
            raise HTTPException(status_code=403, detail="Sem permissão para responder esta demanda")
    if not demand.email_account:
        raise HTTPException(status_code=400, detail="Demanda sem conta de e-mail associada — não é possível enviar resposta")

    provider = get_provider_for_account(demand.email_account)
    from_addr = demand.email_account.email_address
    subject = demand.subject or ""
    # Resposta: garante o prefixo "Re:" (compose envia sem prefixo)
    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"

    primary_to = _clean_recipients(payload.to_emails or [demand.sender_email], "Para")
    if not primary_to:
        raise HTTPException(status_code=400, detail="Informe ao menos um destinatário no campo Para.")
    cc_clean = _clean_recipients(payload.cc or [], "Cc")

    attachments_data = []
    for f in files:
        content = await f.read()
        attachments_data.append((f.filename or "arquivo", f.content_type or "application/octet-stream", content))

    inline = await _read_inline_images(inline_images)
    # Corpo da resposta com o histórico citado (estilo Outlook). O que é
    # gravado no banco continua sendo só o texto novo (payload.body_text).
    send_text, send_html = _build_reply_bodies(demand, payload.body_text, inline)
    msg_id, in_reply_to, references, thread_index = _thread_headers_for_reply(provider, demand, from_addr)

    try:
        ext_id = provider.send_reply(
            to=primary_to[0],
            from_addr=from_addr,
            subject=reply_subject,
            body_text=send_text,
            thread_id=demand.external_thread_id or None,
            cc=(primary_to[1:] + cc_clean) or None,
            attachments=attachments_data or None,
            body_html=send_html,
            inline_images=inline or None,
            message_id=msg_id,
            in_reply_to=in_reply_to,
            references=references,
            thread_index=thread_index,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=_friendly_send_error(e))

    now = datetime.utcnow()
    all_recipients = (payload.to_emails or [demand.sender_email]) + (payload.cc or [])
    msg = Message(
        demand_id=demand.id,
        external_message_id=ext_id,
        direction="out",
        sent_by_user_id=user.id,
        sender_email=from_addr,
        sender_name=user.name,
        recipient_emails=", ".join(all_recipients),
        subject=reply_subject,
        body_text=payload.body_text,
        body_html=None,
        received_at=now,
        has_attachments=bool(attachments_data),
    )
    db.add(msg)
    demand.last_message_at = now
    log_event(db, event_type="REPLY_SENT",
        description=f"{user.name} respondeu a demanda #{demand_id}",
        user_id=user.id, demand_id=demand_id, commit=False)
    db.commit()

    return (
        _base_query(db)
        .options(joinedload(Demand.messages))
        .filter(Demand.id == demand_id)
        .first()
    )


@router.post("/{demand_id}/archive", response_model=DemandOut)
def archive_demand(
    demand_id: int,
    folder_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Move a demanda para uma pasta do arquivo morto."""
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    if user.role != UserRole.ADMIN and demand.assigned_user_id != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão")
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == user.id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Pasta não encontrada")
    demand.folder_id = folder_id
    log_event(db, event_type="DEMAND_MOVED_TO_FOLDER",
        description=f'{user.name} moveu a demanda #{demand_id} para a pasta "{folder.name}"',
        user_id=user.id, demand_id=demand_id, commit=False)
    # Notifica o responsável se for outra pessoa
    if demand.assigned_user_id and demand.assigned_user_id != user.id:
        db.add(Notification(
            user_id=demand.assigned_user_id,
            demand_id=demand_id,
            type="DEMAND_MOVED_TO_FOLDER",
            message=f'Demanda movida para a pasta "{folder.name}": {(demand.subject or demand.sender_email or "")[:60]}',
        ))
    db.commit()
    return _base_query(db).filter(Demand.id == demand_id).first()


@router.post("/{demand_id}/unarchive", response_model=DemandOut)
def unarchive_demand(
    demand_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Remove a demanda de uma pasta organizacional, voltando para a caixa de entrada."""
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    if user.role != UserRole.ADMIN and demand.assigned_user_id != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão")
    demand.folder_id = None
    db.commit()
    return _base_query(db).filter(Demand.id == demand_id).first()


@router.post("/{demand_id}/close-archive", response_model=DemandOut)
def close_archive(
    demand_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Envia a demanda para o Arquivo Morto (casos finalizados)."""
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    if user.role != UserRole.ADMIN and demand.assigned_user_id != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão")
    demand.archived = True
    demand.folder_id = None
    log_event(db, event_type="DEMAND_ARCHIVED",
        description=f"{user.name} enviou a demanda #{demand_id} para o Arquivo Morto",
        user_id=user.id, demand_id=demand_id, commit=False)
    db.commit()
    return _base_query(db).filter(Demand.id == demand_id).first()


@router.post("/{demand_id}/reopen", response_model=DemandOut)
def reopen_demand(
    demand_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Restaura a demanda do Arquivo Morto de volta para a caixa de entrada."""
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    if user.role != UserRole.ADMIN and demand.assigned_user_id != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão")
    demand.archived = False
    db.commit()
    return _base_query(db).filter(Demand.id == demand_id).first()


@router.get("/{demand_id}/logs", response_model=List[AuditLogOut])
def demand_logs(demand_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    if user.role != UserRole.ADMIN and demand.assigned_user_id != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão")
    return db.query(AuditLog).filter(AuditLog.demand_id == demand_id).order_by(AuditLog.created_at.desc()).all()


@router.post("/{demand_id}/share")
def share_demand(
    demand_id: int,
    payload: ShareIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    if user.role != UserRole.ADMIN and demand.assigned_user_id != user.id:
        shared = db.query(DemandShare).filter(
            DemandShare.demand_id == demand_id, DemandShare.shared_with_id == user.id
        ).first()
        if not shared:
            raise HTTPException(status_code=403, detail="Sem permissão")
    target = db.query(User).filter(User.id == payload.user_id, User.active.is_(True)).first()
    if not target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if payload.user_id == user.id:
        raise HTTPException(status_code=400, detail="Não é possível compartilhar consigo mesmo")
    existing = db.query(DemandShare).filter(
        DemandShare.demand_id == demand_id, DemandShare.shared_with_id == payload.user_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Já compartilhado com este usuário")
    share = DemandShare(
        demand_id=demand_id,
        shared_by_id=user.id,
        shared_with_id=payload.user_id,
        note=payload.note,
    )
    db.add(share)
    subject_preview = (demand.subject or demand.sender_email or "")[:80]
    db.add(Notification(
        user_id=payload.user_id,
        demand_id=demand_id,
        type="DEMAND_SHARED",
        message=f"{user.name} compartilhou uma demanda com você: {subject_preview}",
    ))
    db.commit()
    return {"ok": True}


@router.get("/{demand_id}/comments", response_model=List[CommentOut])
def list_comments(demand_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    if user.role != UserRole.ADMIN and demand.assigned_user_id != user.id:
        shared = db.query(DemandShare).filter(
            DemandShare.demand_id == demand_id, DemandShare.shared_with_id == user.id
        ).first()
        if not shared:
            raise HTTPException(status_code=403, detail="Sem permissão")
    comments = db.query(Comment).filter(Comment.demand_id == demand_id).order_by(Comment.created_at.asc()).all()
    return [
        CommentOut(
            id=c.id, demand_id=c.demand_id, user_id=c.user_id,
            user_name=c.user.name if c.user else "—",
            content=c.content, created_at=c.created_at,
        )
        for c in comments
    ]


@router.post("/{demand_id}/comments", response_model=CommentOut)
def add_comment(
    demand_id: int,
    payload: CommentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="Comentário vazio")
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    if user.role != UserRole.ADMIN and demand.assigned_user_id != user.id:
        shared = db.query(DemandShare).filter(
            DemandShare.demand_id == demand_id, DemandShare.shared_with_id == user.id
        ).first()
        if not shared:
            raise HTTPException(status_code=403, detail="Sem permissão para comentar")
    comment = Comment(demand_id=demand_id, user_id=user.id, content=payload.content.strip())
    db.add(comment)

    subject_preview = (demand.subject or demand.sender_email or "")[:60]
    notified: set = {user.id}
    if demand.assigned_user_id and demand.assigned_user_id not in notified:
        db.add(Notification(
            user_id=demand.assigned_user_id, demand_id=demand_id, type="COMMENT_ADDED",
            message=f"{user.name} comentou em: {subject_preview}",
        ))
        notified.add(demand.assigned_user_id)
    prev_commenters = db.query(Comment.user_id).filter(
        Comment.demand_id == demand_id, Comment.user_id != user.id
    ).distinct().all()
    for (uid,) in prev_commenters:
        if uid not in notified:
            db.add(Notification(
                user_id=uid, demand_id=demand_id, type="COMMENT_ADDED",
                message=f"{user.name} comentou em: {subject_preview}",
            ))
            notified.add(uid)
    shared_users = db.query(DemandShare.shared_with_id).filter(DemandShare.demand_id == demand_id).all()
    for (uid,) in shared_users:
        if uid not in notified:
            db.add(Notification(
                user_id=uid, demand_id=demand_id, type="COMMENT_ADDED",
                message=f"{user.name} comentou em: {subject_preview}",
            ))
            notified.add(uid)
    for uid in payload.mentions:
        if uid != user.id:
            db.add(Notification(
                user_id=uid, demand_id=demand_id, type="COMMENT_MENTION",
                message=f"{user.name} mencionou você em: {subject_preview}",
            ))
    # Marca menções pendentes do autor como respondidas
    db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.demand_id == demand_id,
        Notification.type == "COMMENT_MENTION",
        Notification.responded == False,  # noqa: E712
    ).update({"responded": True})
    db.commit()
    db.refresh(comment)
    return CommentOut(
        id=comment.id, demand_id=comment.demand_id, user_id=comment.user_id,
        user_name=user.name, content=comment.content, created_at=comment.created_at,
    )


@router.delete("/{demand_id}/share/{share_id}")
def unshare_demand(
    demand_id: int,
    share_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    share = db.query(DemandShare).filter(DemandShare.id == share_id, DemandShare.demand_id == demand_id).first()
    if not share:
        raise HTTPException(status_code=404, detail="Compartilhamento não encontrado")
    if share.shared_by_id != user.id and user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Sem permissão")
    db.delete(share)
    db.commit()
    return {"ok": True}


# ── Co-responsáveis ─────────────────────────────────────────────────────────

@router.post("/{demand_id}/co-assign", response_model=DemandOut)
def co_assign(
    demand_id: int,
    payload: AssignIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Adiciona um usuário como co-responsável (cria/atualiza share com is_co_assignee=True)."""
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    if user.role != UserRole.ADMIN and demand.assigned_user_id != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão")
    target = db.query(User).filter(User.id == payload.user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    share = db.query(DemandShare).filter(
        DemandShare.demand_id == demand_id, DemandShare.shared_with_id == payload.user_id
    ).first()
    if share:
        share.is_co_assignee = True
    else:
        share = DemandShare(
            demand_id=demand_id, shared_by_id=user.id,
            shared_with_id=payload.user_id, is_co_assignee=True,
        )
        db.add(share)
    subject_preview = (demand.subject or demand.sender_email or "")[:60]
    db.add(Notification(
        user_id=payload.user_id, demand_id=demand_id, type="DEMAND_ASSIGNED",
        message=f"{user.name} te adicionou como co-responsável em: {subject_preview}",
    ))
    db.commit()
    result = _base_query(db).filter(Demand.id == demand_id).first()
    out = DemandOut.model_validate(result)
    out.co_assignees = _co_assignees(db, demand_id)
    return out


@router.delete("/{demand_id}/co-assign/{share_id}", response_model=DemandOut)
def co_unassign(
    demand_id: int,
    share_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Remove co-responsável."""
    share = db.query(DemandShare).filter(DemandShare.id == share_id, DemandShare.demand_id == demand_id).first()
    if not share:
        raise HTTPException(status_code=404, detail="Co-responsável não encontrado")
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if user.role != UserRole.ADMIN and demand.assigned_user_id != user.id and share.shared_with_id != user.id:
        raise HTTPException(status_code=403, detail="Sem permissão")
    db.delete(share)
    db.commit()
    result = _base_query(db).filter(Demand.id == demand_id).first()
    out = DemandOut.model_validate(result)
    out.co_assignees = _co_assignees(db, demand_id)
    return out


@router.post("/{demand_id}/join", response_model=DemandOut)
def join_shared_demand(
    demand_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Usuário aceita trabalhar junto (is_co_assignee=True) na demanda compartilhada."""
    demand = db.query(Demand).filter(Demand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")
    share = db.query(DemandShare).filter(
        DemandShare.demand_id == demand_id, DemandShare.shared_with_id == user.id
    ).first()
    if not share:
        raise HTTPException(status_code=403, detail="Demanda não compartilhada com você")
    share.is_co_assignee = True
    subject_preview = (demand.subject or demand.sender_email or "")[:60]
    if demand.assigned_user_id and demand.assigned_user_id != user.id:
        db.add(Notification(
            user_id=demand.assigned_user_id, demand_id=demand_id, type="DEMAND_ASSIGNED",
            message=f"{user.name} entrou como co-responsável em: {subject_preview}",
        ))
    db.commit()
    result = _base_query(db).filter(Demand.id == demand_id).first()
    out = DemandOut.model_validate(result)
    out.co_assignees = _co_assignees(db, demand_id)
    return out


# ── Compor novo e-mail ───────────────────────────────────────────────────────

@router.post("/compose")
async def compose_email(
    to_emails: str = Form(...),
    cc: str = Form("[]"),
    subject: str = Form(...),
    body_text: str = Form(...),
    account_id: Optional[int] = Form(None),
    files: List[UploadFile] = File(default=[]),
    inline_images: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Envia um novo e-mail (não vinculado a uma demanda existente)."""
    from app.models.email_account import EmailAccount
    to_list: List[str] = _clean_recipients(json.loads(to_emails), "Para")
    cc_list: List[str] = _clean_recipients(json.loads(cc), "Cc")
    if not to_list:
        raise HTTPException(status_code=400, detail="Informe ao menos um destinatário no campo Para.")
    if account_id:
        account = db.query(EmailAccount).filter(EmailAccount.id == account_id, EmailAccount.active == True).first()  # noqa: E712
    else:
        account = db.query(EmailAccount).filter(EmailAccount.active == True).first()  # noqa: E712
    if not account:
        raise HTTPException(status_code=400, detail="Nenhuma conta de e-mail configurada")

    attachments_data = []
    for f in files:
        content = await f.read()
        attachments_data.append((f.filename or "arquivo", f.content_type or "application/octet-stream", content))

    inline = await _read_inline_images(inline_images)
    body_html = _build_html_body(body_text, inline) if inline else None

    provider = get_provider_for_account(account)
    ext_id = None
    try:
        ext_id = provider.send_reply(
            to=to_list[0],
            from_addr=account.email_address,
            subject=subject,
            body_text=body_text,
            cc=(to_list[1:] + cc_list) or None,
            attachments=attachments_data or None,
            body_html=body_html,
            inline_images=inline or None,
            message_id=make_msgid(domain=_domain_of(account.email_address)),
        )
    except NotImplementedError:
        raise HTTPException(status_code=400, detail="Provider atual não suporta envio de e-mail")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=_friendly_send_error(e))

    # Registra o envio (aba "E-mails enviados" + agrupa respostas futuras no mesmo caso)
    from app.services.subject_parser import normalize_subject
    now = datetime.utcnow()
    primary = (to_list[0] or "").strip().lower()
    norm = normalize_subject(subject)
    demand = None
    if norm:
        demand = db.query(Demand).filter(
            Demand.sender_email == primary, Demand.normalized_subject == norm
        ).first()
    if not demand:
        demand = Demand(
            sender_email=primary[:180],
            subject=(subject or "")[:500],
            normalized_subject=(norm or "")[:500],
            status=DemandStatus.CAIXA_ENTRADA,
            last_message_at=now,
            email_account_id=account.id,
        )
        db.add(demand)
        db.flush()
    msg = Message(
        demand_id=demand.id,
        external_message_id=ext_id,
        direction="out",
        sent_by_user_id=user.id,
        sender_email=account.email_address,
        sender_name=user.name,
        recipient_emails=", ".join(to_list + cc_list),
        cc_emails=", ".join(cc_list) or None,
        subject=subject,
        body_text=body_text,
        received_at=now,
        has_attachments=bool(attachments_data),
    )
    db.add(msg)
    demand.last_message_at = now
    log_event(db, event_type="EMAIL_SENT",
        description=f"{user.name} enviou um novo e-mail para {primary}",
        user_id=user.id, demand_id=demand.id, commit=False)
    db.commit()
    return {"ok": True}
