from datetime import datetime
from typing import Optional, Any, Dict
from pydantic import BaseModel, ConfigDict


# ---------- Classify ----------

class ClassifyRequest(BaseModel):
    nombre:                      Optional[str] = None
    rol:                         Optional[str] = None
    correo:                      Optional[str] = None
    telefono:                    Optional[str] = None
    observaciones:               Optional[str] = None
    observaciones_post_contacto: Optional[str] = None
    servicios:                   Optional[str] = None
    direccion:                   Optional[str] = None
    ubicacion:                   Optional[str] = None
    fuente_hojas:                Optional[str] = None


class ClassifyResponse(BaseModel):
    clasificacion: str
    razon:         str


# ---------- Stakeholder ----------
#
# `extra="allow"` permite que el cliente (Apps Script) mande columnas
# desconocidas. El endpoint las mueve al JSONB `extras` automáticamente.

class StakeholderCreate(BaseModel):
    model_config = ConfigDict(extra="allow")

    nombre:                      Optional[str] = None
    rol:                         Optional[str] = None
    correo:                      Optional[str] = None
    telefono:                    Optional[str] = None
    ubicacion:                   Optional[str] = None
    direccion:                   Optional[str] = None
    nit:                         Optional[str] = None
    observaciones:               Optional[str] = None
    observaciones_post_contacto: Optional[str] = None
    servicios:                   Optional[str] = None
    redes:                       Optional[str] = None
    quien_contacta:              Optional[str] = None
    linkedin_url:                Optional[str] = None
    fuente_archivo:              Optional[str] = None
    fuente_hoja:                 Optional[str] = None
    extras:                      Optional[Dict[str, Any]] = None


class StakeholderUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")

    nombre:                      Optional[str] = None
    rol:                         Optional[str] = None
    correo:                      Optional[str] = None
    telefono:                    Optional[str] = None
    ubicacion:                   Optional[str] = None
    direccion:                   Optional[str] = None
    nit:                         Optional[str] = None
    observaciones:               Optional[str] = None
    observaciones_post_contacto: Optional[str] = None
    servicios:                   Optional[str] = None
    redes:                       Optional[str] = None
    quien_contacta:              Optional[str] = None
    linkedin_url:                Optional[str] = None
    fuente_archivo:              Optional[str] = None
    fuente_hoja:                 Optional[str] = None
    clasificacion_negocio:       Optional[str] = None
    activo:                      Optional[bool] = None
    extras:                      Optional[Dict[str, Any]] = None


class StakeholderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="allow")

    id:                          int
    nombre:                      Optional[str] = None
    rol:                         Optional[str] = None
    correo:                      Optional[str] = None
    telefono:                    Optional[str] = None
    ubicacion:                   Optional[str] = None
    direccion:                   Optional[str] = None
    nit:                         Optional[str] = None
    observaciones:               Optional[str] = None
    observaciones_post_contacto: Optional[str] = None
    servicios:                   Optional[str] = None
    redes:                       Optional[str] = None
    quien_contacta:              Optional[str] = None
    linkedin_url:                Optional[str] = None
    fuente_archivo:              Optional[str] = None
    fuente_hoja:                 Optional[str] = None
    clasificacion:               Optional[str] = None
    clasificacion_negocio:       Optional[str] = None
    activo:                      Optional[bool] = True
    extras:                      Optional[Dict[str, Any]] = None
    fecha_carga:                 Optional[datetime] = None
    fecha_actualizacion:         Optional[datetime] = None


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

    model_config = ConfigDict(from_attributes=True)


# ---------- LinkedIn ingest (Chrome extension) ----------

class LinkedInIngest(BaseModel):
    linkedin_url:    str
    nombre:          Optional[str] = None
    headline:        Optional[str] = None
    empresa:         Optional[str] = None
    mensaje_enviado: Optional[str] = None
