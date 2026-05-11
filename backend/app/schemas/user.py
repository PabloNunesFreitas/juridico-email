from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from app.models.user import UserRole


class UserBase(BaseModel):
    name: str
    email: EmailStr
    role: UserRole = UserRole.USER
    active: bool = True


class UserCreate(UserBase):
    pass


class UserCreateOut(BaseModel):
    id: int
    name: str
    email: str
    role: UserRole
    active: bool
    must_change_password: bool
    created_at: datetime
    temp_password: str

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[UserRole] = None
    active: Optional[bool] = None
    password: Optional[str] = None


class UserOut(UserBase):
    id: int
    must_change_password: bool
    created_at: datetime

    class Config:
        from_attributes = True
