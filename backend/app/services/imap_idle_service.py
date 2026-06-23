"""IMAP IDLE para notificações em tempo real de novos emails.

O `imaplib` padrão do Python não implementa o comando IDLE, então aqui ele é
feito via comandos crus (send/readline) sobre a conexão existente. Ao detectar
atividade na INBOX (EXISTS/RECENT), encerra o IDLE, dispara um sync e volta a
escutar. Cada janela de IDLE é reaberta a cada ~25 min (o servidor derruba o
IDLE por volta de 29 min).
"""
import logging
import select
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.models.email_account import EmailAccount
from app.core.database import SessionLocal
from app.providers import get_provider_for_account
from app.services.email_sync_service import _sync_one_account

log = logging.getLogger("imap_idle")

# Controla se o serviço está rodando
_idle_thread: Optional[threading.Thread] = None
_idle_stop_event = threading.Event()

# Janela de cada IDLE antes de reabrir (segundos). < 29 min do servidor.
IDLE_WINDOW_SECONDS = 1500
# Timeout de leitura do socket durante o IDLE (permite checar stop_event).
IDLE_READ_TIMEOUT = 60


def start_imap_idle():
    """Inicia listener IMAP IDLE para cada conta."""
    global _idle_thread

    if _idle_thread and _idle_thread.is_alive():
        log.info("[idle] já rodando")
        return

    log.info("[idle] iniciando...")
    _idle_stop_event.clear()
    _idle_thread = threading.Thread(target=_idle_loop, daemon=True)
    _idle_thread.start()
    log.info("[idle] thread iniciada")


def stop_imap_idle():
    """Para o listener IMAP IDLE."""
    global _idle_thread

    _idle_stop_event.set()
    if _idle_thread:
        _idle_thread.join(timeout=5)
    log.info("[idle] parado")


def _idle_loop():
    """Descobre contas IMAP ativas e abre uma thread de IDLE para cada uma."""
    db = SessionLocal()
    try:
        accounts = db.query(EmailAccount).filter(
            EmailAccount.provider == "imap",
            EmailAccount.active.is_(True),
        ).all()
        account_ids = [a.id for a in accounts]
    finally:
        db.close()

    log.info(f"[idle] {len(account_ids)} conta(s) IMAP ativa(s)")
    if not account_ids:
        log.info("[idle] nenhuma conta IMAP para monitorar")
        return

    threads = []
    for account_id in account_ids:
        t = threading.Thread(
            target=_idle_for_account,
            args=(account_id,),
            daemon=True,
            name=f"idle-account-{account_id}",
        )
        t.start()
        threads.append(t)

    _idle_stop_event.wait()
    for t in threads:
        t.join(timeout=5)


def _wait_for_activity(imap, email_addr: str) -> bool:
    """Abre UMA janela de IDLE. Retorna True se houve atividade na caixa.

    Retorna False se a janela expirou sem novidades (basta reabrir o IDLE).
    Lança exceção se a conexão cair (o chamador reconecta).
    """
    tag = imap._new_tag()
    imap.send(b"%s IDLE\r\n" % tag)
    resp = imap.readline()
    if not resp.startswith(b"+"):
        raise ConnectionError(f"IDLE não aceito pelo servidor: {resp!r}")

    log.info(f"[idle] {email_addr}: aguardando novos emails (IDLE)...")
    sock = imap.socket()
    activity = False
    deadline = time.time() + IDLE_WINDOW_SECONDS
    try:
        while not _idle_stop_event.is_set() and time.time() < deadline:
            # Espera por dados no socket sem mexer no timeout (evita o bug
            # "cannot read from timed out object" do imaplib após socket.timeout).
            ready, _, _ = select.select([sock], [], [], IDLE_READ_TIMEOUT)
            if not ready:
                continue  # sem novidade nesta janela; re-checa stop/deadline
            line = imap.readline()
            if not line:
                raise ConnectionError("conexão fechada pelo servidor durante IDLE")
            upper = line.upper()
            if b"EXISTS" in upper or b"RECENT" in upper:
                log.info(f"[idle] {email_addr}: atividade detectada ({line.strip()!r})")
                activity = True
                break
    finally:
        # Encerra o IDLE: envia DONE e consome até a resposta com a tag.
        try:
            imap.send(b"DONE\r\n")
            t0 = time.time()
            while time.time() - t0 < 10:
                l = imap.readline()
                if not l or l.startswith(tag):
                    break
        except Exception:
            pass
    return activity


def _idle_for_account(account_id: int):
    """Mantém o IDLE de uma conta, sincronizando ao detectar atividade."""
    # Resolve o e-mail uma vez (para logs); reconsulta a conta a cada ciclo.
    db0 = SessionLocal()
    try:
        acc0 = db0.query(EmailAccount).filter(EmailAccount.id == account_id).first()
        email_addr = acc0.email_address if acc0 else f"conta#{account_id}"
    finally:
        db0.close()

    while not _idle_stop_event.is_set():
        provider = None
        db = SessionLocal()
        try:
            account = db.query(EmailAccount).filter(EmailAccount.id == account_id).first()
            if not account or not account.active:
                log.info(f"[idle] {email_addr}: conta inativa/removida, encerrando")
                return

            provider = get_provider_for_account(account)
            imap = provider._get_imap()
            imap.select("INBOX")

            got_activity = _wait_for_activity(imap, email_addr)

            # Fecha a conexão do IDLE antes de sincronizar (sync abre a sua).
            try:
                provider._close_imap()
            except Exception:
                pass

            if got_activity and not _idle_stop_event.is_set():
                try:
                    # Usa SINCE recente: com multi-pasta, isso devolve só os
                    # e-mails dos últimos dias (incluindo o novo do INBOX),
                    # em vez de truncar nos N primeiros IDs de todas as pastas.
                    since = datetime.now(timezone.utc) - timedelta(days=2)
                    scanned, nd, nm = _sync_one_account(
                        db, provider, account_id, None, since, 1000, f"idle #{account_id}"
                    )
                    log.info(f"[idle] {email_addr}: sync = {nm} msgs, {nd} demandas")
                except Exception as e:
                    log.error(f"[idle] {email_addr}: erro no sync: {e}")
        except Exception as e:
            log.warning(f"[idle] {email_addr}: erro ({e}); reconectando em 30s")
            if provider:
                try:
                    provider._close_imap()
                except Exception:
                    pass
            _idle_stop_event.wait(30)
        finally:
            db.close()

    log.info(f"[idle] {email_addr}: parado")
