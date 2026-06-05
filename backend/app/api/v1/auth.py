from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.main import limiter
from app.models.user import User
from app.schemas.auth import SetPasswordIn, TokenOut
from app.schemas.user import UserOut


class ThemeIn(BaseModel):
    theme: str

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
@limiter.limit("10/minute")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username.lower(), User.active.is_(True)).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
    return TokenOut(
        access_token=create_access_token(user.id, {"role": user.role.value}),
        must_change_password=user.must_change_password,
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/set-password", response_model=UserOut)
def set_password(payload: SetPasswordIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="As senhas não coincidem")
    if len(payload.new_password) < 12:
        raise HTTPException(status_code=400, detail="A senha deve ter pelo menos 12 caracteres")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    db.commit()
    db.refresh(user)
    return user


@router.patch("/me/theme", response_model=UserOut)
def set_theme(payload: ThemeIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    user.theme = payload.theme
    db.commit()
    db.refresh(user)
    return user
