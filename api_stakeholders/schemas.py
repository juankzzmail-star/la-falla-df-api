from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr


# ---------- Classify ----------

class ClassifyRequest(BaseModel):
    nombre:       Optional[str] = None
    rol:          Optional[str] = None
    correo:       Optional[str] = None
    telefono:     Optional[str] = None
    observaciones: Optional[str] = None
    servicios:    Optional[str] = None
    direccion:    Optional[str] = None
    ubicacion:    Optional[str] = None
    fuente_hojas: Optional[str] = None


class ClassifyResponse(BaseModel):
    clasificacion: str
    razon:         str


# ---------- Stakeholder ----------

class StakeholderCreate(BaseModel):
    nombre:        Optional[str] = None
    rol:           Optional[str] = None
    correo:        Optional[str] = None
    telefono:      Optional[str] = None
    ubicacion:     Optional[str] = None
    direccion:     Optional[str] = None
    nit:           Optional[str] = None
    observaciones: Optional[str] = None
    servicios:     Optional[str] = None
    redes:         Optional[str] = None
    quien_contacta: Optional[str] = None
    linkedin_url:  Optional[str] = None
    fuente_archivo: Optional[str] = None
    fuente_hoja:   Optional[str] = None


class StakeholderOut(StakeholderCreate):
    id:                    int
    clasificacion:         Optional[str] = None
    clasificacion_negocio: Optional[str] = None
    fecha_carga:           Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------- Interaction ----------

class InteractionCreate(BaseModel):
    stakeholder_id: Optional[int] = None
    campaign:       str
    canal:          str
    direccion:      str
    mensaje:        Optional[str] = None
    status:         Optional[str] = "sent"


class InteractionOut(InteractionCreate):
    id:        int
    timestamp: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------- LinkedIn ingest (Chrome extension) ----------

class LinkedInIngest(BaseModel):
    linkedin_url:    str
    nombre:          Optional[str] = None
    headline:        Optional[str] = None
    empresa:         Optional[str] = None
    mensaje_enviado: Optional[str] = None
