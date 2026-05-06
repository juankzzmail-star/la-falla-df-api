from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from ..db import get_db
from ..models import InboxItem

router = APIRouter(prefix="/inbox", tags=["inbox"])


class InboxOut(BaseModel):
    id: int
    tipo: str
    texto: str
    origen: str
    procesado: bool
    created_at: datetime

    class Config:
        from_attributes = True


class InboxCreate(BaseModel):
    tipo: str = "note"
    texto: str
    origen: str = "Captura rápida"


class InboxPatch(BaseModel):
    texto: Optional[str] = None
    procesado: Optional[bool] = None


@router.get("", response_model=List[InboxOut])
def list_inbox(procesado: Optional[bool] = None, db: Session = Depends(get_db)):
    q = db.query(InboxItem)
    if procesado is not None:
        q = q.filter(InboxItem.procesado == procesado)
    return q.order_by(InboxItem.created_at.desc()).all()


@router.post("", response_model=InboxOut, status_code=201)
def create_inbox_item(body: InboxCreate, db: Session = Depends(get_db)):
    item = InboxItem(**body.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{item_id}", response_model=InboxOut)
def update_inbox_item(item_id: int, body: InboxPatch, db: Session = Depends(get_db)):
    item = db.get(InboxItem, item_id)
    if not item:
        raise HTTPException(404, "Item no encontrado")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def delete_inbox_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(InboxItem, item_id)
    if not item:
        raise HTTPException(404, "Item no encontrado")
    db.delete(item)
    db.commit()
