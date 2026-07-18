from datetime import date, datetime
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict, Field


# ─── Strategic Goals ─────────────────────────────────────────────────────────

class GoalBase(BaseModel):
    codigo: str
    titulo: str
    area: str
    fecha_inicio: Optional[date] = None
    fecha_fin_meta: Optional[date] = None
    peso_porcentaje: Optional[float] = None
    estado: str = "activo"
    milestone_id: Optional[int] = None   # meta-de-hito -> its company HITO (unify-strategy-execution)


class GoalCreate(GoalBase):
    pass


class GoalUpdate(BaseModel):
    titulo: Optional[str] = None
    area: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin_meta: Optional[date] = None
    peso_porcentaje: Optional[float] = None
    estado: Optional[str] = None
    milestone_id: Optional[int] = None


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
    anio: Optional[int] = None          # annual cycle dimension (unify-strategy-execution)
    ciclo_id: Optional[int] = None
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
    anio: Optional[int] = None
    ciclo_id: Optional[int] = None
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


# ─── Strategy cascade (change strategy-cascade) ───────────────────────────────

class GeneratePlansRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal_ids: List[int]


class GeneratePlansResponse(BaseModel):
    planes_creados: int
    planes_actualizados: int
    plans: List[PlanOut]


class PlanApproveResponse(BaseModel):
    plan_id: int
    estado: str
    tareas_creadas: int
    responsable: Optional[str] = None


# ─── Plan quarterly goals (change plan-quarterly-milestones) ──────────────────
# The quarter (Q1–Q4) lives on the PLAN, not the hito (model §12, D9). The per-quarter `pct` is
# DERIVED from real task completion at read time and is never stored (D10, option C).

class QuarterlyGoalIn(BaseModel):
    trimestre: int = Field(..., ge=1, le=4)
    meta: str
    objetivo_medible: Optional[str] = None


class QuarterlyGoalOut(BaseModel):
    trimestre: int
    meta: Optional[str] = None
    objetivo_medible: Optional[str] = None
    pct: Optional[float] = None          # DERIVED; None means "sin datos" (no contributing work)


class PlanQuartersIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quarters: List[QuarterlyGoalIn]


class PlanQuartersOut(BaseModel):
    plan_id: int
    area: Optional[str] = None
    quarters: List[QuarterlyGoalOut]


# ─── Hito roll-up linkage (change populate-hito-rollup) ───────────────────────

class MilestoneLinkIn(BaseModel):
    """PUT body to set/change/clear a meta-de-hito's hito link. null clears the link."""
    model_config = ConfigDict(extra="forbid")
    milestone_id: Optional[int] = None


class MetaHitoLink(BaseModel):
    meta_id: int
    codigo: Optional[str] = None
    milestone_id: Optional[int] = None
    hito_titulo: Optional[str] = None


class LinkMetasHitosOut(BaseModel):
    estado: str                              # "linked" | "sin_hitos" (honest empty)
    linked: int                              # number of metas linked this run
    mensaje: Optional[str] = None            # human-readable note (e.g. "no hay hitos para enlazar")
    links: List[MetaHitoLink] = []
    hitos_recomputados: List[int] = []       # ids of hitos whose pct was recomputed


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
    # change unify-strategy-execution: two origins + EDT/project/hito links.
    origen: str = "directa"             # directa | proyecto
    project_id: Optional[int] = None
    edt_node_id: Optional[int] = None   # fixes prior ORM<->schema drift (was unassignable via API)
    milestone_id: Optional[int] = None  # optional hito override (the ~20% rule)


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
    # google_task_id / google_calendar_event_id are backend-owned: populated by the
    # routing/sync paths, never by user edits. Exposing them here let update_task's
    # blind setattr overwrite the keys sync_google reconciles by (mass-assignment).
    stakeholder_id: Optional[int] = None
    # change unify-strategy-execution
    origen: Optional[str] = None
    project_id: Optional[int] = None
    edt_node_id: Optional[int] = None
    milestone_id: Optional[int] = None


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
    
# ─── EDT Nodes ───────────────────────────────────────────────────────────────

class EdtNodeBase(BaseModel):
    codigo: str
    nivel: int = 1
    nombre: str
    descripcion_dict: Optional[str] = None
    responsable: Optional[str] = None
    accountable: Optional[str] = None
    consulted: Optional[List[str]] = None
    informed: Optional[List[str]] = None
    predecesores: Optional[List[str]] = None
    costo_estimado: float = 0.0
    duracion_dias: int = 0
    porcentaje_avance: int = 0
    es_paquete_trabajo: bool = True
    es_hito: bool = False
    estado: str = "planificado"
    alerta: Optional[str] = None

class EdtNodeCreate(EdtNodeBase):
    parent_id: Optional[int] = None

class EdtNodePatch(BaseModel):
    codigo: Optional[str] = None
    nombre: Optional[str] = None
    descripcion_dict: Optional[str] = None
    responsable: Optional[str] = None
    accountable: Optional[str] = None
    consulted: Optional[List[str]] = None
    informed: Optional[List[str]] = None
    predecesores: Optional[List[str]] = None
    costo_estimado: Optional[float] = None
    duracion_dias: Optional[int] = None
    porcentaje_avance: Optional[int] = None
    estado: Optional[str] = None
    alerta: Optional[str] = None

class EdtNodeOut(EdtNodeBase):
    id: int
    project_id: int
    parent_id: Optional[int] = None
    # Valores calculados
    costo_hijos_sum: Optional[float] = None
    num_hijos: Optional[int] = None
    model_config = {"from_attributes": True}
