from datetime import datetime
from sqlalchemy import Column, Integer, Text, DateTime, Boolean, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from .db import Base


class Stakeholder(Base):
    __tablename__ = "stakeholders_master"

    id                          = Column(Integer, primary_key=True, index=True)
    nombre                      = Column(Text)
    rol                         = Column(Text)
    correo                      = Column(Text)
    telefono                    = Column(Text)
    ubicacion                   = Column(Text)
    direccion                   = Column(Text)
    nit                         = Column(Text)
    observaciones               = Column(Text)
    observaciones_post_contacto = Column(Text)
    servicios                   = Column(Text)
    redes                       = Column(Text)
    quien_contacta              = Column(Text)
    clasificacion               = Column(Text)
    clasificacion_negocio       = Column(Text)
    linkedin_url                = Column(Text)
    fuente_archivo              = Column(Text)
    fuente_hoja                 = Column(Text)
    activo                      = Column(Boolean, nullable=False, server_default="true")
    extras                      = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    fecha_carga                 = Column(DateTime(timezone=True), server_default=func.now())
    fecha_actualizacion         = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Interaction(Base):
    __tablename__ = "interactions"

    id             = Column(Integer, primary_key=True, index=True)
    stakeholder_id = Column(Integer, ForeignKey("stakeholders_master.id", ondelete="SET NULL"), nullable=True)
    campaign       = Column(Text, nullable=False)
    canal          = Column(Text, nullable=False)
    direccion      = Column(Text, nullable=False)
    mensaje        = Column(Text)
    status         = Column(Text, default="sent")
    timestamp      = Column(DateTime(timezone=True), server_default=func.now())
