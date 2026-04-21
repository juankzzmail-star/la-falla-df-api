from datetime import date, datetime
from typing import Optional, List, Any
from pydantic import BaseModel


# ─── Strategic Goals ─────────────────────────────────────────────────────────

class GoalBase(BaseModel):
    codigo: str
    titulo: str
    area: str
    fecha_inicio: Optional[date] = None
    fecha_fin_meta: Optional[date] = None
    peso_porcentaje: Optional[float] = None
    estado: str = "activo"


class GoalCreate(GoalBase):
    pass


class GoalUpdate(BaseModel):
    titulo: Optional[str] = None
    area: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin_meta: Optional[date] = None
    peso_porcentaje: Optional[float] = None
    estado: Optional[str] = None


class GoalOut(GoalBase):
    id: int
    created_at: datetime
    model_config = {"from_attributes": True}


# ─── Document Ingestion ───────────────────────────────────────────────────────

class DocumentIngestionRequest(BaseModel):
    url: Optional[str] = None
    content_text: Optional[str] = None
    content_base64: Optional[str] = None
    mime_type: Optional[str] = None


class DocumentIngestionResponse(BaseModel):
    metas_creadas: int
    metas_actualizadas: int
    goals: List[GoalOut]


# ─── Plans ───────────────────────────────────────────────────────────────────

class PlanBase(BaseModel):
    codigo: str
    titulo: str
    area: str
    goal_id: Optional[int] = None
    responsable: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin_planificada: Optional[date] = None
    estado: str = "activo"


class PlanCreate(PlanBase):
    pass


class PlanUpdate(BaseModel):
    titulo: Optional[str] = None
    area: Optional[str] = None
    goal_id: Optional[int] = None
    responsable: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin_planificada: Optional[date] = None
    estado: Optional[str] = None


class CurvaSBaseline(BaseModel):
    baseline: List[dict]


class PlanOut(PlanBase):
    id: int
    baseline_curva_s: Optional[Any] = None
    pct_completado_real: float = 0
    pct_completado_plan: float = 0
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ─── Tasks ───────────────────────────────────────────────────────────────────

class TaskBase(BaseModel):
    plan_id: int
    titulo: str
    responsable: Optional[str] = None
    area: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_vencimiento: Optional[date] = None
    prioridad: str = "media"
    es_hito: bool = False
    estado: str = "pendiente"
    peso_pct: float = 0
    url_entregable: Optional[str] = None
    stakeholder_id: Optional[int] = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    titulo: Optional[str] = None
    responsable: Optional[str] = None
    area: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_vencimiento: Optional[date] = None
    prioridad: Optional[str] = None
    es_hito: Optional[bool] = None
    estado: Optional[str] = None
    peso_pct: Optional[float] = None
    url_entregable: Optional[str] = None
    motivo_bloqueo: Optional[str] = None
    google_task_id: Optional[str] = None
    google_calendar_event_id: Optional[str] = None
    stakeholder_id: Optional[int] = None


class TaskBlockRequest(BaseModel):
    motivo_bloqueo: str


class TaskOut(TaskBase):
    id: int
    fecha_completada: Optional[date] = None
    motivo_bloqueo: Optional[str] = None
    google_task_id: Optional[str] = None
    google_calendar_event_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ─── Stakeholder Health ───────────────────────────────────────────────────────

class HealthLogCreate(BaseModel):
    stakeholder_id: int
    salud: str
    razon: Optional[str] = None
    dias_sin_contacto: Optional[int] = None
    resultado_ultima_interaccion: Optional[str] = None


class HealthLogOut(HealthLogCreate):
    id: int
    calculado_en: datetime
    model_config = {"from_attributes": True}


# ─── Dashboard ───────────────────────────────────────────────────────────────

class AreaSummary(BaseModel):
    area: str
    total_tareas: int
    completadas: int
    bloqueadas: int
    vencidas: int
    pct_real: float
    pct_planificado: float
    semaforo: str


class AlertItem(BaseModel):
    tipo: str
    descripcion: str
    area: Optional[str] = None
    responsable: Optional[str] = None
    tarea_id: Optional[int] = None
    stakeholder_id: Optional[int] = None
