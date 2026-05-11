"""
Sync periódica em background usando APScheduler.

Roda dentro do mesmo processo do FastAPI. Para PoC isso basta; em produção
recomenda-se Celery/Redis ou um worker separado.
"""
import logging
from typing import Optional

import httpx
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.email_sync_service import sync_inbox

log = logging.getLogger(__name__)
_scheduler: Optional[BackgroundScheduler] = None


def _job() -> None:
    db = SessionLocal()
    try:
        result = sync_inbox(db)
        if result.get("new_messages", 0) > 0:
            log.info("[auto-sync] %s", result)
    except Exception as e:
        log.warning("[auto-sync] falhou: %s", e)
    finally:
        db.close()


def _ping_job() -> None:
    try:
        with httpx.Client(timeout=10) as client:
            client.get(settings.SELF_PING_URL)
        log.debug("[keep-alive] ping ok")
    except Exception as e:
        log.warning("[keep-alive] ping falhou: %s", e)


def start_scheduler() -> None:
    global _scheduler
    if not settings.AUTO_SYNC_ENABLED:
        log.info("[scheduler] auto-sync desativado por config")
        return
    if _scheduler is not None:
        return
    from datetime import datetime, timedelta
    _scheduler = BackgroundScheduler(timezone="UTC")
    interval = max(5, settings.AUTO_SYNC_INTERVAL_SECONDS)
    _scheduler.add_job(
        _job,
        "interval",
        seconds=interval,
        id="email-sync",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now() + timedelta(seconds=2),
    )
    if settings.SELF_PING_URL:
        _scheduler.add_job(
            _ping_job,
            "interval",
            minutes=10,
            id="keep-alive",
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now() + timedelta(minutes=10),
        )
        log.info("[scheduler] keep-alive ativado → %s", settings.SELF_PING_URL)
    _scheduler.start()
    log.info("[scheduler] auto-sync iniciada (intervalo=%ss)", settings.AUTO_SYNC_INTERVAL_SECONDS)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
