from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class FolderCreate(BaseModel):
    name: str


class FolderRename(BaseModel):
    name: str


class FolderOut(BaseModel):
    id: int
    name: str
    user_id: int
    created_at: datetime
    demand_count: int = 0

    class Config:
        from_attributes = True


class FolderMini(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True
