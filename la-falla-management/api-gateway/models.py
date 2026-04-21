from sqlalchemy import Column, Integer, Text, Boolean, Numeric, Date, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from .db import Base


class StrategicGoal(Base):
    __tablename__ = "strategic_goals"

    id              = Column(Integer, primary_key=True, index=True)
    codigo          = Column(Text, unique=True, nullable=False)
    titulo          = Column(Text, nullable=False)
    area            = Column(Text, nullable=False)
    fecha_inicio    = Column(Date)
    fecha_fin_meta  = Column(Date)
    peso_porcentaje = Column(Numeric(5, 2))
    estado          = Column(Text, nullable=False, default="activo")
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class Plan(Base):
    __tablename__ = "plans"

    id                    = Column(Integer, primary_key=True, index=True)
    codigo                = Column(Text, unique=True, nullable=False)
    titulo                = Column(Text, nullable=False)
    area                  = Column(Text, nullable=False)
    goal_id               = Column(Integer, ForeignKey("strategic_goals.id", ondelete="SET NULL"), nullable=True)
    responsable           = Column(Text)
    fecha_inicio          = Column(Date)
    fecha_fin_planificada = Column(Date)
    baseline_curva_s      = Column(JSONB)
    pct_completado_real   = Column(Numeric(5, 2), nullable=False, default=0)
    pct_completado_plan   = Column(Numeric(5, 2), nullable=False, default=0)
    estado                = Column(Text, nullable=False, default="activo")
    created_at            = Column(DateTime(timezone=True), server_default=func.now())
    updated_at            = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Task(Base):
    __tablename__ = "tasks"

    id                       = Column(Integer, primary_key=True, index=True)
    plan_id                  = Column(Integer, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False)
    titulo                   = Column(Text, nullable=False)
    responsable              = Column(Text)
    area                     = Column(Text)
    fecha_inicio             = Column(Date)
    fecha_vencimiento        = Column(Date)
    fecha_completada         = Column(Date)
    prioridad                = Column(Text, nullable=False, default="media")
    es_hito                  = Column(Boolean, nullable=False, default=False)
    estado                   = Column(Text, nullable=False, default="pendiente")
    motivo_bloqueo           = Column(Text)
    url_entregable           = Column(Text)
    peso_pct                 = Column(Numeric(5, 2), nullable=False, default=0)
    google_task_id           = Column(Text)
    google_calendar_event_id = Column(Text)
    stakeholder_id           = Column(Integer, ForeignKey("stakeholders_master.id", ondelete="SET NULL"), nullable=True)
    created_at               = Column(DateTime(timezone=True), server_default=func.now())
    updated_at               = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class StakeholderHealthLog(Base):
    __tablename__ = "stakeholder_health_log"

    id                           = Column(Integer, primary_key=True, index=True)
    stakeholder_id               = Column(Integer, ForeignKey("stakeholders_master.id", ondelete="CASCADE"), nullable=False)
    salud                        = Column(Text, nullable=False)
    razon                        = Column(Text)
    dias_sin_contacto            = Column(Integer)
    calculado_en                 = Column(DateTime(timezone=True), server_default=func.now())
    resultado_ultima_interaccion = Column(Text)
