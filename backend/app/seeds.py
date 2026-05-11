"""Cria admin inicial e tabelas se ainda não existirem (PoC)."""
import logging

from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.models import *  # noqa: F401,F403  -- registra todos os modelos no metadata

log = logging.getLogger(__name__)


def init_db() -> None:
    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError as e:
        log.error("Falha ao conectar no banco: %s", e)
        raise

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
