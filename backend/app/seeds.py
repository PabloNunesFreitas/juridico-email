"""Cria admin inicial e tabelas se ainda não existirem (PoC)."""
import logging

from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.models import *  # noqa: F401,F403  -- registra todos os modelos no metadata

log = logging.getLogger(__name__)


_COLUMN_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS theme VARCHAR(20) DEFAULT 'cinza'",
    "ALTER TABLE demands ADD COLUMN IF NOT EXISTS folder_id INTEGER REFERENCES folders(id) ON DELETE SET NULL",
    "ALTER TABLE demands ADD COLUMN IF NOT EXISTS archived BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE demand_shares ADD COLUMN IF NOT EXISTS is_co_assignee BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS responded BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE email_accounts ADD COLUMN IF NOT EXISTS needs_reconnect BOOLEAN NOT NULL DEFAULT FALSE",
]


def _run_migrations() -> None:
    with engine.connect() as conn:
        for sql in _COLUMN_MIGRATIONS:
            try:
                conn.execute(__import__("sqlalchemy").text(sql))
                conn.commit()
            except Exception as e:
                log.warning("Migration ignorada (%s): %s", sql[:60], e)
                conn.rollback()


def init_db() -> None:
    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError as e:
        log.error("Falha ao conectar no banco: %s", e)
        raise

    _run_migrations()

    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == settings.SEED_ADMIN_EMAIL.lower()).first():
            admin = User(
                name="Administrador",
                email=settings.SEED_ADMIN_EMAIL.lower(),
                password_hash=hash_password(settings.SEED_ADMIN_PASSWORD),
                role=UserRole.ADMIN,
                active=True,
            )
            db.add(admin)
            db.commit()
            log.info("Admin seed criado: %s", settings.SEED_ADMIN_EMAIL)
    finally:
        db.close()
