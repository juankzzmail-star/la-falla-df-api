from sqlalchemy import (
    Column, Integer, Text, Boolean, Numeric, Date, DateTime,
    ForeignKey, ARRAY,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from .db import Base


# ─── Modelos existentes ────────────────────────────────────────

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
    edt_node_id              = Column(Integer, ForeignKey("edt_nodes.id", ondelete="SET NULL"), nullable=True)
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


# ─── Modelos v2: Centro de Mando ──────────────────────────────

class Risk(Base):
    __tablename__ = "risks"

    id                  = Column(Integer, primary_key=True, index=True)
    descripcion         = Column(Text, nullable=False)
    area                = Column(Text, nullable=False)
    impacto             = Column(Integer, nullable=False)        # 1-5
    probabilidad        = Column(Integer, nullable=False)        # 1-5
    nivel_riesgo        = Column(Integer, nullable=False)        # impacto × probabilidad
    estado_mitigacion   = Column(Text, nullable=False, default="monitoreado")
    responsable         = Column(Text)
    origen              = Column(Text, nullable=False, default="ceo_manual")  # openclaw_auto | ceo_manual | director_area
    fecha_identificacion = Column(DateTime(timezone=True), server_default=func.now())
    fecha_revision      = Column(DateTime(timezone=True))
    # Campos nuevos para EDT project-scoped risks
    project_id          = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    estrategia          = Column(Text, default="Mitigar")      # Mitigar | Evitar | Transferir | Aceptar
    plan_accion         = Column(Text)
    causa               = Column(Text)
    efecto              = Column(Text)
    paquete             = Column(Text)


class RoadmapVersion(Base):
    __tablename__ = "roadmap_versions"

    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(Text, nullable=False)
    descripcion = Column(Text)
    activa      = Column(Boolean, nullable=False, default=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class RoadmapMilestone(Base):
    __tablename__ = "roadmap_milestones"

    id                    = Column(Integer, primary_key=True, index=True)
    titulo                = Column(Text, nullable=False)
    orden                 = Column(Integer, nullable=False, default=0)
    estado                = Column(Text, nullable=False, default="pendiente")   # done | in_progress | delayed | pending
    area                  = Column(Text)
    fecha_inicio          = Column(DateTime(timezone=True))
    fecha_fin_planificada = Column(DateTime(timezone=True))
    fecha_completado      = Column(DateTime(timezone=True))
    depends_on            = Column(ARRAY(Integer))                              # IDs de hitos que deben completarse antes
    version_id            = Column(Integer, ForeignKey("roadmap_versions.id", ondelete="SET NULL"), nullable=True)
    pct_completado        = Column(Numeric(5, 2), nullable=False, default=0)
    created_at            = Column(DateTime(timezone=True), server_default=func.now())
    updated_at            = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FinancialSnapshot(Base):
    __tablename__ = "financial_snapshots"

    id                    = Column(Integer, primary_key=True, index=True)
    fecha                 = Column(Date, nullable=False)
    caja_operativa        = Column(Numeric(18, 2), nullable=False, default=0)
    reservas_estrategicas = Column(Numeric(18, 2), nullable=False, default=0)
    credito_disponible    = Column(Numeric(18, 2), nullable=False, default=0)
    gasto_mensual_promedio = Column(Numeric(18, 2), nullable=False, default=0)
    liquidez_total        = Column(Numeric(18, 2), nullable=False, default=0)   # calculado: caja+reservas+crédito
    meses_respiracion     = Column(Numeric(6, 2), nullable=False, default=0)    # liquidez_total / gasto_mensual
    created_at            = Column(DateTime(timezone=True), server_default=func.now())


class FinancialFlow(Base):
    __tablename__ = "financial_flows"

    id              = Column(Integer, primary_key=True, index=True)
    tipo            = Column(Text, nullable=False)       # cobro_pendiente | gasto_recurrente | gasto_unico
    descripcion     = Column(Text, nullable=False)
    monto           = Column(Numeric(18, 2), nullable=False)   # positivo=ingreso, negativo=egreso
    horizonte_dias  = Column(Integer)
    frecuencia      = Column(Text)                      # mensual | trimestral | anual
    fecha_estimada  = Column(Date)
    origen          = Column(Text)                      # FDC | nomina | rodaje | impuestos | etc.
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class InboxItem(Base):
    __tablename__ = "inbox_items"

    id         = Column(Integer, primary_key=True, index=True)
    tipo       = Column(Text, nullable=False, default="note")   # note | doc | link
    texto      = Column(Text, nullable=False)
    origen     = Column(Text, nullable=False, default="Captura rápida")
    procesado  = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Project(Base):
    __tablename__ = "projects"

    id          = Column(Integer, primary_key=True, index=True)
    codigo      = Column(Text, unique=True, nullable=False)
    nombre      = Column(Text, nullable=False)
    area        = Column(Text, nullable=False)
    presupuesto = Column(Numeric(18, 2), nullable=False, default=0)
    ejecutado   = Column(Numeric(18, 2), nullable=False, default=0)
    estado      = Column(Text, nullable=False, default="activo")
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Deliverable(Base):
    __tablename__ = "deliverables"

    id         = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    titulo     = Column(Text, nullable=False)
    completado = Column(Boolean, nullable=False, default=False)
    orden      = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DailySuggestion(Base):
    __tablename__ = "daily_suggestions"

    id          = Column(Integer, primary_key=True, index=True)
    fecha       = Column(Date, nullable=False)
    tag         = Column(Text, nullable=False)   # PROYECTOS | COMERCIAL | AUDIOVISUAL | INVEST.
    titulo      = Column(Text, nullable=False)
    cuerpo      = Column(Text)
    estado      = Column(Text, nullable=False, default="pendiente")  # pendiente | aceptada | editada | eliminada
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class AreaKpiConfig(Base):
    __tablename__ = "area_kpi_config"

    id               = Column(Integer, primary_key=True, index=True)
    area             = Column(Text, nullable=False, unique=True)
    kpi_code         = Column(Text, nullable=False)
    label            = Column(Text, nullable=False)
    formula_expr     = Column(Text)
    target           = Column(Numeric(18, 2))
    period           = Column(Text, default="mensual")
    updated_at       = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OperationalAsset(Base):
    """Tabla polimórfica: reemplaza research_documents + audiovisual_pieces."""
    __tablename__ = "operational_assets"

    id              = Column(Integer, primary_key=True, index=True)
    area            = Column(Text, nullable=False)
    asset_type      = Column(Text, nullable=False)   # documento_investigacion | pieza_audiovisual | alianza | publicacion | territorio_mapeado | reporte
    titulo          = Column(Text, nullable=False)
    estado          = Column(Text, nullable=False, default="activo")
    url_externa     = Column(Text)
    engagement_metric = Column(Numeric(10, 2))
    intent_type     = Column(Text)                   # plan | obs | pend
    asset_metadata  = Column(JSONB)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class ExecutiveFeedCache(Base):
    __tablename__ = "executive_feed_cache"

    id            = Column(Integer, primary_key=True, index=True)
    scope         = Column(Text, nullable=False)          # global | area_GCF | area_GP | area_GI | area_GA
    content       = Column(JSONB, nullable=False)
    generated_at  = Column(DateTime(timezone=True), server_default=func.now())
    expires_at    = Column(DateTime(timezone=True))
    trigger_event = Column(Text)                          # cron_daily | risk_high | milestone_blocked | etc.


class DashboardPendingPanel(Base):
    """Registra paneles del dashboard que no tienen datos aún."""
    __tablename__ = "dashboard_pending_panels"

    id          = Column(Integer, primary_key=True, index=True)
    panel_id    = Column(Text, nullable=False)   # 'caja', 'riesgos', '2030', etc.
    endpoint    = Column(Text, nullable=False)
    razon       = Column(Text)
    llena_con   = Column(Text)                   # qué documento/comando lo resuelve
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    resuelto_en = Column(DateTime(timezone=True))  # NULL = sigue pendiente


# ─── Modelos v4: EDT + RAG ─────────────────────────────────────

class EdtNode(Base):
    """EDT (Estructura de Desglose del Trabajo) node — forma árbol jerárquico por proyecto."""
    __tablename__ = "edt_nodes"

    id                 = Column(Integer, primary_key=True, index=True)
    project_id         = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    parent_id          = Column(Integer, ForeignKey("edt_nodes.id", ondelete="CASCADE"), nullable=True)
    codigo             = Column(Text, nullable=False)
    nivel              = Column(Integer, nullable=False, default=1)
    nombre             = Column(Text, nullable=False)
    descripcion_dict   = Column(Text)
    responsable        = Column(Text)
    accountable        = Column(Text)
    consulted          = Column(ARRAY(Text))
    informed           = Column(ARRAY(Text))
    predecesores       = Column(ARRAY(Text))
    costo_estimado     = Column(Numeric(12, 2), default=0)
    duracion_dias      = Column(Integer, default=0)
    porcentaje_avance  = Column(Integer, default=0)
    es_paquete_trabajo = Column(Boolean, default=True)
    es_hito            = Column(Boolean, default=False)
    estado             = Column(Text, default="planificado")
    alerta             = Column(Text)
    approved_by        = Column(Text)
    approved_at        = Column(DateTime(timezone=True))
    created_at         = Column(DateTime(timezone=True), server_default=func.now())


class DocumentChunk(Base):
    """Chunks de documentos indexados para RAG + búsqueda semántica."""
    __tablename__ = "document_chunks"

    id            = Column(Integer, primary_key=True, index=True)
    document_id   = Column(Text, nullable=False)
    document_name = Column(Text, nullable=False)
    document_type = Column(Text)  # 'riesgo' | 'contrato' | 'acta' | 'estrategia' | 'financiero'
    chunk_index   = Column(Integer, nullable=False)
    content       = Column(Text, nullable=False)
    # embedding: vector(1024) — se agrega post-pgvector install con ALTER TABLE
    metadata_obj  = Column(JSONB)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
