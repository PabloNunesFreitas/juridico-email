import base64
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

    if user.role != UserRole.ADMIN and demand.assigned_user_id != user.id:
        shared = db.query(DemandShare).filter(
            DemandShare.demand_id == demand.id, DemandShare.shared_with_id == user.id
        ).first()
        if not shared:
            raise HTTPException(status_code=403, detail="Sem permissão")

    if not demand.email_account:
        raise HTTPException(status_code=400, detail="Demanda sem conta de e-mail associada")

    if not att.external_attachment_id or not msg.external_message_id:
        raise HTTPException(status_code=400, detail="Dados do anexo incompletos — re-sincronize os e-mails")

    provider = get_provider_for_account(demand.email_account)
    try:
        data = provider.get_attachment(msg.external_message_id, att.external_attachment_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falha ao baixar anexo: {e}")

    safe_name = att.filename.encode("ascii", errors="replace").decode("ascii")
    return Response(
        content=data,
        media_type=att.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )
