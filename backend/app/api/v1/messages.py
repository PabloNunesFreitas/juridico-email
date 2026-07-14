import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.attachment import Attachment
from app.models.message import Message
from app.models.demand import Demand
from app.models.demand_share import DemandShare
from app.models.user import User, UserRole
from app.providers import get_provider_for_account
from app.services import attachment_storage as _store

log = logging.getLogger("messages")

router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("/{message_id}/attachments/{att_id}/download")
def download_attachment(
    message_id: int,
    att_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    att = db.query(Attachment).filter(Attachment.id == att_id, Attachment.message_id == message_id).first()
    if not att:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")

    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")

    demand = db.query(Demand).filter(Demand.id == msg.demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demanda não encontrada")

    # Mesma regra de visibilidade do get_demand: admin, responsável, demanda
    # não atribuída (None) ou compartilhada. Sem o None, o anexo de uma demanda
    # da caixa "Não atribuídas" abria para o admin mas dava 403 para a equipe.
    if user.role != UserRole.ADMIN and demand.assigned_user_id not in (None, user.id):
        shared = db.query(DemandShare).filter(
            DemandShare.demand_id == demand.id, DemandShare.shared_with_id == user.id
        ).first()
        if not shared:
            raise HTTPException(status_code=403, detail="Sem permissão")

    # --- CAMINHO 1: arquivo já em disco (não depende de API externa) ----------
    if att.storage_path and _store.exists(att.storage_path):
        try:
            data = _store.load(att.storage_path)
            safe_name = att.filename.encode("ascii", errors="replace").decode("ascii")
            return Response(
                content=data,
                media_type=att.mime_type or "application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
            )
        except Exception as exc:
            # Arquivo corrompido / removido do disco — tenta fallback via API.
            log.warning("Falha ao ler anexo do disco (id=%d, path=%s): %s", att.id, att.storage_path, exc)

    # --- CAMINHO 2: fallback — busca na API do provedor ----------------------
    if not demand.email_account:
        raise HTTPException(status_code=400, detail="Demanda sem conta de e-mail associada")

    if not att.external_attachment_id or not msg.external_message_id:
        raise HTTPException(
            status_code=400,
            detail="Anexo não encontrado em disco e dados incompletos para buscá-lo na API — re-sincronize os e-mails",
        )

    provider = get_provider_for_account(demand.email_account)
    try:
        data = provider.get_attachment(msg.external_message_id, att.external_attachment_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falha ao baixar anexo: {e}")

    # Aproveita e salva em disco para próximas requisições (cache tardio).
    try:
        account_id = demand.email_account_id or 0
        rel = _store.save(
            data=data,
            account_id=account_id,
            message_external_id=msg.external_message_id,
            att_db_id=att.id,
            filename=att.filename or "attachment",
        )
        att.storage_path = rel
        db.commit()
        log.info("Anexo cacheado em disco após download (id=%d): %s", att.id, rel)
    except Exception as exc:
        log.warning("Não foi possível cachear anexo em disco (id=%d): %s", att.id, exc)
        # Não impede a entrega ao usuário.

    safe_name = att.filename.encode("ascii", errors="replace").decode("ascii")
    return Response(
        content=data,
        media_type=att.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )
