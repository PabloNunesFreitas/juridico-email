from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.demand import Demand
from app.models.folder import Folder
from app.models.user import User
from app.schemas.folder import FolderCreate, FolderOut, FolderRename

router = APIRouter(prefix="/folders", tags=["folders"])


def _folder_out(f: Folder, db: Session) -> FolderOut:
    count = db.query(Demand).filter(Demand.folder_id == f.id).count()
    return FolderOut(
        id=f.id,
        name=f.name,
        user_id=f.user_id,
        created_at=f.created_at,
        demand_count=count,
    )


@router.get("", response_model=List[FolderOut])
def list_folders(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    folders = db.query(Folder).filter(Folder.user_id == user.id).order_by(Folder.name).all()
    return [_folder_out(f, db) for f in folders]


@router.post("", response_model=FolderOut, status_code=201)
def create_folder(payload: FolderCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nome não pode ser vazio")
    if db.query(Folder).filter(Folder.user_id == user.id, Folder.name == name).first():
        raise HTTPException(status_code=400, detail="Já existe uma pasta com este nome")
    folder = Folder(name=name, user_id=user.id)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return _folder_out(folder, db)


@router.patch("/{folder_id}", response_model=FolderOut)
def rename_folder(folder_id: int, payload: FolderRename, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == user.id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Pasta não encontrada")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nome não pode ser vazio")
    folder.name = name
    db.commit()
    db.refresh(folder)
    return _folder_out(folder, db)


@router.delete("/{folder_id}", status_code=204)
def delete_folder(folder_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == user.id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Pasta não encontrada")
    # Retorna as demandas desta pasta para a caixa de entrada
    db.query(Demand).filter(Demand.folder_id == folder_id).update({"folder_id": None})
    db.delete(folder)
    db.commit()


@router.get("/{folder_id}/demands")
def list_folder_demands(folder_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.user_id == user.id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Pasta não encontrada")
    from app.schemas.demand import DemandOut
    from sqlalchemy.orm import joinedload
    demands = (
        db.query(Demand)
        .options(joinedload(Demand.assigned_user), joinedload(Demand.email_account))
        .filter(Demand.folder_id == folder_id)
        .order_by(Demand.last_message_at.desc())
        .all()
    )
    return demands
