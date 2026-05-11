"""
Sincronização de e-mails — núcleo do PoC.

Para cada mensagem do provider:
  1. Localiza demanda via thread_id (ou cria via remetente+normalized_subject como fallback).
  2. Se demanda nova, aplica regra de continuidade automática (assignment_rules).
  3. Faz upsert de Message (idempotente por external_message_id).
  4. Registra logs.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.demand import Demand, DemandStatus
from app.models.email_account import EmailAccount
from app.models.message import Message
from app.models.attachment import Attachment
from app.models.user import User
from app.providers import get_email_provider, get_provider_for_account
from app.providers.email_provider import ProviderMessage
from app.services.audit_service import log_event
from app.services.demand_service import find_continuity_user
from app.services.subject_parser import normalize_subject, parse_subject
from app.services.sync_state import SYNC_STATE

log = logging.getLogger("sync")


def _last_received_at(db: Session) -> Optional[datetime]:
    last = db.query(func.max(Message.received_at)).scalar()
    if not last:
        return None
    return last - timedelta(minutes=1)


def _find_or_create_demand(db: Session, msg: ProviderMessage) -> Tuple[Demand, bool]:
    demand = None
    if msg.thread_id:
        demand = db.query(Demand).filter(Demand.external_thread_id == msg.thread_id).first()
    if not demand:
        norm = normalize_subject(msg.subject)
        if norm:
            demand = db.query(Demand).filter(
                Demand.sender_email == msg.sender_email.lower(),
                Demand.normalized_subject == norm,
            ).first()
    if demand:
        return demand, False

    parsed = parse_subject(msg.subject)

    def _trunc(s, n):
        if s is None:
            return None
        s = s.replace("\x00", "")
        return s[:n]

    demand = Demand(
        external_thread_id=_trunc(msg.thread_id, 255),
        sender_email=_trunc(msg.sender_email.lower(), 180),
        sender_name=_trunc(msg.sender_name, 180),
        subject=_trunc(msg.subject, 500),
        normalized_subject=_trunc(normalize_subject(msg.subject), 500),
        client_name=_trunc(parsed.get("client_name"), 180),
        nup=_trunc(parsed.get("nup"), 60),
        bank=parsed.get("bank"),
        status=parsed.get("status") or DemandStatus.CAIXA_ENTRADA,
        last_message_at=msg.received_at,
        email_account_id=None,
    )
    db.add(demand)
    db.flush()
    auto_user_id = find_continuity_user(db, msg.sender_email)
    if auto_user_id:
        demand.assigned_user_id = auto_user_id
        log_event(
            db, event_type="DEMAND_AUTO_ASSIGNED",
            description=f"Continuidade automática: vínculo do remetente {msg.sender_email}",
            user_id=None, demand_id=demand.id,
            metadata={"assigned_user_id": auto_user_id, "rule": "sender_email"},
            commit=False,
        )
    log_event(db, event_type="DEMAND_CREATED", description=f"Nova demanda de {msg.sender_email}", demand_id=demand.id, commit=False)
    return demand, True


def _sanitize(s, max_len=None):
    if s is None:
        return None
    s = s.replace("\x00", "")
    if max_len and len(s) > max_len:
        s = s[:max_len]
    return s


def _get_accounts_to_sync(db: Session):
    active = db.query(EmailAccount).filter(EmailAccount.active.is_(True)).all()
    return [(get_provider_for_account(acc), acc.id) for acc in active]


def _sync_one_account(db: Session, provider, account_id: Optional[int], actor: Optional[User], since: Optional[datetime], limit: int, label: str):
    """Sincroniza uma conta. Retorna (scanned, new_demands, new_messages)."""
    try:
        all_ids = provider.list_message_ids(since=since, limit=limit)
    except Exception as e:
        log.error("[sync] falha ao listar IDs (%s): %s", label, e)
        log_event(db, event_type="SYNC_ERROR", description=f"Falha ao listar IDs ({label}): {e}", user_id=actor.id if actor else None)
        raise

    if not all_ids:
        log.info("[sync] caixa vazia (%s)", label)
        return len(all_ids), 0, 0

    existing_ids = {
        row[0] for row in db.query(Message.external_message_id)
        .filter(Message.external_message_id.in_(all_ids)).all()
    }
    new_ids = [i for i in all_ids if i not in existing_ids]
    log.info("[sync] %s: %d IDs, %d novos", label, len(all_ids), len(new_ids))
    SYNC_STATE.set_total(scanned=len(all_ids), to_fetch=len(new_ids))

    if not new_ids:
        return len(all_ids), 0, 0

    PARALLEL = 5
    new_demands = 0
    new_messages = 0

    def _fetch_one(ext_id: str, _prov=provider):
        try:
            return ext_id, _prov.get_message_by_id(ext_id), None
        except Exception as e:
            return ext_id, None, str(e)

    log.info("[sync] FASE 1 (%s): baixando %d mensagens...", label, len(new_ids))
    downloaded: list = []
    fetched_count = 0
    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        futures = {pool.submit(_fetch_one, eid): eid for eid in new_ids}
        for fut in as_completed(futures, timeout=3600):
            try:
                ext_id, pm, err = fut.result(timeout=120)
            except Exception as e:
                log.warning("[sync] future erro: %s", e)
                continue
            fetched_count += 1
            if err or pm is None:
                if err:
                    log.warning("[sync] falha ao baixar %s: %s", ext_id, err)
                continue
            if pm.body_html and len(pm.body_html) > 100_000:
                pm.body_html = pm.body_html[:100_000] + "\n[...truncado...]"
            downloaded.append(pm)
            SYNC_STATE.tick(fetched=fetched_count, new_messages=0, new_demands=0,
                            last=f"📥 Baixando: {pm.subject or pm.sender_email}")
            if fetched_count % 100 == 0:
                log.info("[sync] FASE 1 progresso: %d/%d baixadas", fetched_count, len(new_ids))

    log.info("[sync] FASE 1 (%s): %d mensagens em memória. Iniciando FASE 2...", label, len(downloaded))
    SYNC_STATE.tick(fetched=len(downloaded), new_messages=0, new_demands=0,
                    last=f"💾 Salvando {len(downloaded)} mensagens no banco...")

    from app.core.database import SessionLocal as _SessionLocal
    try:
        db.close()
    except Exception:
        pass
    db = _SessionLocal()

    downloaded.sort(key=lambda m: m.received_at)
    log.info("[sync] FASE 2 (%s): iniciando loop de inserção", label)
    failed_count = 0

    for pm in downloaded:
        try:
            with db.begin_nested():
                demand, created = _find_or_create_demand(db, pm)
                if created:
                    demand.email_account_id = account_id
                    new_demands += 1
                elif demand.email_account_id is None and account_id:
                    demand.email_account_id = account_id
                msg = Message(
                    demand_id=demand.id,
                    external_message_id=_sanitize(pm.external_id, 255),
                    direction="in",
                    sender_email=_sanitize(pm.sender_email, 180),
                    sender_name=_sanitize(pm.sender_name, 180),
                    recipient_emails=_sanitize(",".join(pm.recipients)),
                    subject=_sanitize(pm.subject, 500),
                    body_text=_sanitize(pm.body_text),
                    body_html=_sanitize(pm.body_html),
                    received_at=pm.received_at,
                    has_attachments=bool(pm.attachments),
                )
                db.add(msg)
                db.flush()
                for a in pm.attachments:
                    db.add(Attachment(
                        message_id=msg.id,
                        filename=_sanitize(a.filename, 255),
                        mime_type=_sanitize(a.mime_type, 120),
                        size=a.size,
                        external_attachment_id=_sanitize(a.external_id, 255),
                    ))
                if pm.received_at > demand.last_message_at:
                    demand.last_message_at = pm.received_at
                log_event(
                    db, event_type="MESSAGE_RECEIVED",
                    description=f"Nova mensagem de {pm.sender_email}",
                    demand_id=demand.id, user_id=actor.id if actor else None,
                    metadata={"external_message_id": pm.external_id}, commit=False,
                )
            new_messages += 1
        except Exception as e:
            failed_count += 1
            log.warning("[sync] FASE 2: msg %s falhou: %s", pm.external_id, e)
            continue
        SYNC_STATE.tick(fetched=fetched_count, new_messages=new_messages, new_demands=new_demands,
                        last=f"💾 Salvando {new_messages}/{len(downloaded)}: {pm.subject or pm.sender_email}")
        if new_messages % 200 == 0:
            db.commit()

    try:
        db.commit()
    except Exception:
        pass

    log_event(
        db, event_type="SYNC_COMPLETED",
        description=f"Sync {label}: {new_demands} demandas, {new_messages} msgs",
        user_id=actor.id if actor else None,
        metadata={"account_id": account_id, "new_demands": new_demands, "new_messages": new_messages},
    )
    log.info("[sync] %s: %d novas mensagens, %d novas demandas", label, new_messages, new_demands)
    return len(all_ids), new_demands, new_messages


def sync_inbox(db: Session, actor: Optional[User] = None, since: Optional[datetime] = None, limit: int = 100000) -> dict:
    if not SYNC_STATE.try_start():
        log.info("[sync] já em execução, pulando")
        return {"new_demands": 0, "new_messages": 0, "scanned": 0, "skipped": True}

    log.info("[sync] iniciando ...")
    accounts_to_sync = _get_accounts_to_sync(db)
    if not accounts_to_sync:
        SYNC_STATE.finish()
        log.info("[sync] nenhuma conta conectada, pulando")
        return {"new_demands": 0, "new_messages": 0, "scanned": 0, "skipped": True}
    log.info("[sync] %d conta(s) para sincronizar", len(accounts_to_sync))

    total_scanned = total_new_demands = total_new_messages = 0
    last_error = None

    for provider, account_id in accounts_to_sync:
        label = f"conta #{account_id}" if account_id else "legado"
        try:
            scanned, nd, nm = _sync_one_account(db, provider, account_id, actor, since, limit, label)
            total_scanned += scanned
            total_new_demands += nd
            total_new_messages += nm
        except Exception as e:
            last_error = str(e)
            continue

    SYNC_STATE.finish(error=last_error)
    log.info("[sync] CONCLUIDO: %d msgs, %d demandas (%d contas)", total_new_messages, total_new_demands, len(accounts_to_sync))
    return {"new_demands": total_new_demands, "new_messages": total_new_messages, "scanned": total_scanned}
