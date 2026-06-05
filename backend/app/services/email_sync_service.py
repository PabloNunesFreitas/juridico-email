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


PARALLEL = 10       # workers paralelos de download
CHUNK_SIZE = 200    # salva no banco a cada N mensagens baixadas (mantém RAM limitada)


def _download_and_cache_attachments(provider, pm, msg_db_id: int, account_id: Optional[int], db) -> None:
    """
    Baixa os bytes de cada anexo da mensagem via API e persiste em disco.

    Erros de download individual são logados mas NÃO interrompem o sync:
    o registro do anexo continua no banco com storage_path=None, permitindo
    tentativa de fallback via API na hora do download pelo usuário.
    """
    from app.services import attachment_storage as _store

    attachments = db.query(Attachment).filter(Attachment.message_id == msg_db_id).all()
    for att in attachments:
        if att.storage_path and _store.exists(att.storage_path):
            # Já salvo em disco — nada a fazer.
            continue
        if not att.external_attachment_id or not pm.external_id:
            log.warning("[sync] anexo id=%d sem external_id, pulando cache", att.id)
            continue
        try:
            data = provider.get_attachment(pm.external_id, att.external_attachment_id)
            rel = _store.save(
                data=data,
                account_id=account_id or 0,
                message_external_id=pm.external_id,
                att_db_id=att.id,
                filename=att.filename or "attachment",
            )
            att.storage_path = rel
            log.debug("[sync] anexo id=%d salvo em disco: %s", att.id, rel)
        except Exception as exc:
            # Falha de rede, quota, token — não bloqueia o restante.
            log.warning(
                "[sync] falha ao cachear anexo id=%d (%s): %s",
                att.id, att.filename, exc,
            )


def _save_chunk(chunk: list, account_id, actor, label: str, chunk_num: int, provider=None) -> tuple:
    """Salva um lote de mensagens em sessão própria. Retorna (new_demands, new_messages)."""
    from app.core.database import SessionLocal as _SessionLocal
    chunk_db = _SessionLocal()
    nd = nm = 0
    try:
        for pm in chunk:
            try:
                with chunk_db.begin_nested():
                    demand, created = _find_or_create_demand(chunk_db, pm)
                    if created:
                        demand.email_account_id = account_id
                        nd += 1
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
                    chunk_db.add(msg)
                    chunk_db.flush()
                    for a in pm.attachments:
                        chunk_db.add(Attachment(
                            message_id=msg.id,
                            filename=_sanitize(a.filename, 255),
                            mime_type=_sanitize(a.mime_type, 120),
                            size=a.size,
                            external_attachment_id=_sanitize(a.external_id, 255),
                            # storage_path será preenchido logo após o flush abaixo
                        ))
                    if pm.received_at > demand.last_message_at:
                        demand.last_message_at = pm.received_at
                    log_event(
                        chunk_db, event_type="MESSAGE_RECEIVED",
                        description=f"Nova mensagem de {pm.sender_email}",
                        demand_id=demand.id,
                        user_id=actor.id if actor else None,
                        metadata={"external_message_id": pm.external_id}, commit=False,
                    )
                # Os Attachment agora têm id (flush foi feito dentro do begin_nested).
                # Baixa e salva os bytes em disco enquanto ainda estamos na sessão.
                if pm.attachments and provider is not None:
                    _download_and_cache_attachments(
                        provider=provider,
                        pm=pm,
                        msg_db_id=msg.id,
                        account_id=account_id,
                        db=chunk_db,
                    )
                nm += 1
            except Exception as e:
                from sqlalchemy.exc import IntegrityError
                if isinstance(e, IntegrityError):
                    log.debug("[sync] chunk %d msg %s duplicada, ignorando", chunk_num, pm.external_id)
                else:
                    log.warning("[sync] chunk %d msg %s falhou: %s", chunk_num, pm.external_id, e)
        chunk_db.commit()
    except Exception as e:
        log.error("[sync] chunk %d commit falhou: %s", chunk_num, e)
        try:
            chunk_db.rollback()
        except Exception:
            pass
    finally:
        chunk_db.close()
    return nd, nm


def _sync_one_account(db: Session, provider, account_id: Optional[int], actor: Optional[User], since: Optional[datetime], limit: int, label: str):
    """Sincroniza uma conta em lotes (download + save intercalados). Retorna (scanned, new_demands, new_messages)."""
    try:
        all_ids = provider.list_message_ids(since=since, limit=limit)
    except Exception as e:
        log.error("[sync] falha ao listar IDs (%s): %s", label, e)
        log_event(db, event_type="SYNC_ERROR", description=f"Falha ao listar IDs ({label}): {e}", user_id=actor.id if actor else None)
        raise

    if not all_ids:
        log.info("[sync] caixa vazia (%s)", label)
        return 0, 0, 0

    existing_ids = {
        row[0] for row in db.query(Message.external_message_id)
        .filter(Message.external_message_id.in_(all_ids)).all()
    }
    new_ids = [i for i in all_ids if i not in existing_ids]
    log.info("[sync] %s: %d IDs, %d novos", label, len(all_ids), len(new_ids))
    SYNC_STATE.set_total(scanned=len(all_ids), to_fetch=len(new_ids))

    if not new_ids:
        return len(all_ids), 0, 0

    total_new_demands = 0
    total_new_messages = 0
    total_fetched = 0
    chunks = [new_ids[i:i + CHUNK_SIZE] for i in range(0, len(new_ids), CHUNK_SIZE)]
    log.info("[sync] %s: %d lotes de até %d msgs, %d workers", label, len(chunks), CHUNK_SIZE, PARALLEL)

    def _fetch_one(ext_id: str, _prov=provider):
        try:
            return ext_id, _prov.get_message_by_id(ext_id), None
        except Exception as e:
            return ext_id, None, str(e)

    for chunk_num, chunk_ids in enumerate(chunks, start=1):
        log.info("[sync] %s: lote %d/%d — baixando %d msgs...", label, chunk_num, len(chunks), len(chunk_ids))
        downloaded: list = []

        with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
            futures = {pool.submit(_fetch_one, eid): eid for eid in chunk_ids}
            for fut in as_completed(futures, timeout=3600):
                try:
                    ext_id, pm, err = fut.result(timeout=120)
                except Exception as e:
                    log.warning("[sync] future erro: %s", e)
                    continue
                total_fetched += 1
                if err or pm is None:
                    if err:
                        log.warning("[sync] falha ao baixar %s: %s", ext_id, err)
                    continue
                if pm.body_html and len(pm.body_html) > 100_000:
                    pm.body_html = pm.body_html[:100_000] + "\n[...truncado...]"
                downloaded.append(pm)
                SYNC_STATE.tick(
                    fetched=total_fetched,
                    new_messages=total_new_messages,
                    new_demands=total_new_demands,
                    last=f"📥 Baixando: {pm.subject or pm.sender_email}",
                )

        if not downloaded:
            continue

        downloaded.sort(key=lambda m: m.received_at)
        log.info("[sync] %s: lote %d — salvando %d msgs...", label, chunk_num, len(downloaded))
        SYNC_STATE.tick(
            fetched=total_fetched,
            new_messages=total_new_messages,
            new_demands=total_new_demands,
            last=f"💾 Salvando lote {chunk_num}/{len(chunks)} ({len(downloaded)} msgs)...",
        )

        nd, nm = _save_chunk(downloaded, account_id, actor, label, chunk_num, provider=provider)
        total_new_demands += nd
        total_new_messages += nm
        downloaded.clear()  # libera memória do lote
        log.info("[sync] %s: lote %d concluído — %d msgs, %d demandas", label, chunk_num, nm, nd)

    from app.core.database import SessionLocal as _SessionLocal
    final_db = _SessionLocal()
    try:
        log_event(
            final_db, event_type="SYNC_COMPLETED",
            description=f"Sync {label}: {total_new_demands} demandas, {total_new_messages} msgs",
            user_id=actor.id if actor else None,
            metadata={"account_id": account_id, "new_demands": total_new_demands, "new_messages": total_new_messages},
        )
    finally:
        final_db.close()

    log.info("[sync] %s: CONCLUÍDO — %d msgs, %d demandas", label, total_new_messages, total_new_demands)
    return len(all_ids), total_new_demands, total_new_messages


def sync_inbox(db: Session, actor: Optional[User] = None, since: Optional[datetime] = None, limit: int = 100000) -> dict:
    if not SYNC_STATE.try_start():
        log.info("[sync] já em execução, pulando")
        return {"new_demands": 0, "new_messages": 0, "scanned": 0, "skipped": True}

    # Se não há mensagens no banco (primeiro sync), limita pela data configurada
    if since is None:
        from app.core.config import settings as _settings
        from app.core.database import SessionLocal as _SL
        _db2 = _SL()
        try:
            last = _last_received_at(_db2)
        finally:
            _db2.close()
        if last is None and _settings.SYNC_INITIAL_DAYS > 0:
            from datetime import timezone as _tz
            since = datetime.now(_tz.utc) - timedelta(days=_settings.SYNC_INITIAL_DAYS)
            log.info("[sync] primeiro sync: limitando a %d dias (%s)", _settings.SYNC_INITIAL_DAYS, since.date())
        else:
            since = last

    log.info("[sync] iniciando ...")
    total_scanned = total_new_demands = total_new_messages = 0
    last_error = None

    try:
        accounts_to_sync = _get_accounts_to_sync(db)
        if not accounts_to_sync:
            log.info("[sync] nenhuma conta conectada, pulando")
            return {"new_demands": 0, "new_messages": 0, "scanned": 0, "skipped": True}
        log.info("[sync] %d conta(s) para sincronizar", len(accounts_to_sync))

        for provider, account_id in accounts_to_sync:
            label = f"conta #{account_id}" if account_id else "legado"
            try:
                scanned, nd, nm = _sync_one_account(db, provider, account_id, actor, since, limit, label)
                total_scanned += scanned
                total_new_demands += nd
                total_new_messages += nm
            except Exception as e:
                last_error = str(e)
                err_low = str(e).lower()
                is_auth = any(kw in err_low for kw in ("401", "unauthorized", "invalid_grant", "invalid_token", "token", "credential", "403"))
                if is_auth and account_id:
                    try:
                        acc = db.query(EmailAccount).filter(EmailAccount.id == account_id).first()
                        if acc:
                            acc.needs_reconnect = True
                            db.commit()
                    except Exception:
                        pass
                continue
    finally:
        SYNC_STATE.finish(error=last_error)

    log.info("[sync] CONCLUIDO: %d msgs, %d demandas (%d contas)", total_new_messages, total_new_demands, len(accounts_to_sync))
    return {"new_demands": total_new_demands, "new_messages": total_new_messages, "scanned": total_scanned}
