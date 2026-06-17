"""IMAP IDLE para notificações em tempo real de novos emails."""
import logging
import threading
import time
from typing import Optional

from app.models.email_account import EmailAccount
from app.core.database import SessionLocal
from app.providers import get_provider_for_account
from app.services.email_sync_service import _sync_one_account

log = logging.getLogger("imap_idle")

# Controla se o serviço está rodando
_idle_thread: Optional[threading.Thread] = None
_idle_stop_event = threading.Event()


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
    """Loop principal que mantém IDLE aberto e escuta por novos emails."""
    db = SessionLocal()

    try:
        # Busca contas IMAP ativas
        accounts = db.query(EmailAccount).filter(
            EmailAccount.provider == "imap",
            EmailAccount.active.is_(True)
        ).all()

        log.info(f"[idle] encontradas {len(accounts)} conta(s) IMAP ativa(s)")
        if not accounts:
            log.info("[idle] nenhuma conta IMAP para monitorar")
            db.close()
            return

        # Para cada conta IMAP, roda IDLE em thread separada
        threads = []
        for account in accounts:
            t = threading.Thread(
                target=_idle_for_account,
                args=(account.id,),
                daemon=True,
                name=f"idle-account-{account.id}"
            )
            t.start()
            threads.append(t)

        # Aguarda até stop signal
        _idle_stop_event.wait()

        # Aguarda threads
        for t in threads:
            t.join(timeout=5)

    finally:
        db.close()


def _idle_for_account(account_id: int):
    """IDLE para uma conta específica."""
    db = SessionLocal()

    try:
        account = db.query(EmailAccount).filter(EmailAccount.id == account_id).first()
        if not account:
            return

        provider = get_provider_for_account(account)

        log.info(f"[idle] {account.email_address}: iniciando IDLE")

        # Conecta e seleciona INBOX
        imap = provider._get_imap()
        imap.select("INBOX")

        # Modo IDLE
        try:
            imap.idle()
        except Exception as e:
            log.warning(f"[idle] {account.email_address}: servidor não suporta IDLE ({e}) - usando sync periódico")
            return
        log.info(f"[idle] {account.email_address}: aguardando novos emails...")

        while not _idle_stop_event.is_set():
            try:
                # Aguarda resposta do servidor (~29 minutos timeout padrão)
                response = imap.idle_check(timeout=60)  # 60s timeout

                if response:
                    log.info(f"[idle] {account.email_address}: novo email detectado!")

                    # Sai do IDLE, faz sync, retorna ao IDLE
                    imap.idle_done()

                    # Faz sync imediato da nova mensagem
                    try:
                        scanned, nd, nm = _sync_one_account(
                            db, provider, account.id, None, None, 1
                        )
                        log.info(f"[idle] {account.email_address}: sync = {nm} msgs, {nd} demandas")
                    except Exception as e:
                        log.error(f"[idle] {account.email_address}: erro no sync: {e}")

                    # Retorna ao IDLE
                    imap.idle()

            except Exception as e:
                log.warning(f"[idle] {account.email_address}: erro: {e}")
                # Reconecta
                try:
                    imap.idle_done()
                except:
                    pass
                imap = provider._get_imap()
                imap.select("INBOX")
                imap.idle()

        # Encerra IDLE
        try:
            imap.idle_done()
            imap.close()
        except:
            pass

        log.info(f"[idle] {account.email_address}: parado")

    except Exception as e:
        log.error(f"[idle] {account.email_address}: erro fatal: {e}")

    finally:
        db.close()
