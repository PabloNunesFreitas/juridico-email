import secrets
import string
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_admin
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate, UserCreateOut, UserOut, UserUpdate
from app.services.audit_service import log_event

router = APIRouter(prefix="/users", tags=["users"])

_ALPHABET = string.ascii_letters + string.digits + "!@#$%"


def _generate_password(length: int = 12) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


@router.get("", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.post("", response_model=UserCreateOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    temp_password = _generate_password()
    user = User(
        name=payload.name,
        email=payload.email.lower(),
        password_hash=hash_password(temp_password),
        role=payload.role,
        active=payload.active,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_event(db, event_type="USER_CREATED", description=f"{admin.name} criou usuário {user.email}", user_id=admin.id, metadata={"new_user_id": user.id})
    return UserCreateOut(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        active=user.active,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
        temp_password=temp_password,
    )


@router.post("/{user_id}/reset-password", response_model=dict)
def reset_password(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    temp_password = _generate_password()
    user.password_hash = hash_password(temp_password)
    user.must_change_password = True
    db.commit()
    log_event(db, event_type="USER_UPDATED", description=f"{admin.name} redefiniu senha de {user.email}", user_id=admin.id, metadata={"target_user_id": user.id})
    return {"temp_password": temp_password, "email": user.email}


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if payload.name is not None:
        user.name = payload.name
    if payload.role is not None:
        user.role = payload.role
    if payload.active is not None:
        user.active = payload.active
    if payload.password:
        user.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    log_event(db, event_type="USER_UPDATED", description=f"{admin.name} atualizou usuário {user.email}", user_id=admin.id)
    return user


@router.delete("/{user_id}", status_code=204)
def deactivate_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.active = False
    db.commit()
    log_event(db, event_type="USER_DEACTIVATED", description=f"{admin.name} desativou {user.email}", user_id=admin.id)
