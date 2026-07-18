from sqlalchemy import (
    Column, Integer, Text, Boolean, Numeric, Date, DateTime,
    ForeignKey, ARRAY, Table, UniqueConstraint, CheckConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from .db import Base


# `stakeholders_master` is owned/managed outside this service (it lives in the shared DB and is
# queried via raw SQL in routers/stakeholders.py — there is no mapped class). Register a minimal
# Table so the cross-area FKs on tasks/stakeholder_health_log resolve during ORM mapper
# configuration and flush; without it, an ORM Task INSERT raises NoReferencedTableError. No row is
# ever created through this Table and nothing calls metadata.create_all(). (unify-strategy-execution)
Table("stakeholders_master", Base.metadata, Column("id", Integer, primary_key=True))


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
    # change unify-strategy-execution: strategic_goals is the per-area "meta-de-hito"; this links it
    # to its company-wide HITO (roadmap_milestones). The cascade goals->plans->tasks is reused as-is.
    milestone_id    = Column(Integer, ForeignKey("roadmap_milestones.id", ondelete="SET NULL"), nullable=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class Plan(Base):
    __tablename__ = "plans"

    id                    = Column(Integer, primary_key=True, index=True)
    codigo                = Column(Text, unique=True, nullable=False)
    titulo                = Column(Text, nullable=False)
    area                  = Column(Text, nullable=False)
    goal_id               = Column(Integer, ForeignKey("strategic_goals.id", ondelete="SET NULL"), nullable=True)
    responsable           = Column(Text)
    # change unify-strategy-execution: annual cycle dimension (1 plan per area per year).
    anio                  = Column(Integer)
    ciclo_id              = Column(Integer, ForeignKey("roadmap_cycles.id", ondelete="SET NULL"), nullable=True)
    fecha_inicio          = Column(Date)
    fecha_fin_planificada = Column(Date)
    baseline_curva_s      = Column(JSONB)
    pct_completado_real   = Column(Numeric(5, 2), nullable=False, default=0)
    pct_completado_plan   = Column(Numeric(5, 2), nullable=False, default=0)
    estado                = Column(Text, nullable=False, default="activo")
    created_at            = Column(DateTime(timezone=True), server_default=func.now())
    updated_at            = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PlanQuarterlyGoal(Base):
    """change plan-quarterly-milestones: a plan's quarterly goal (Q1–Q4). The quarter lives on the PLAN,
    not the hito (model §12, D9). The per-quarter % is DERIVED from real task completion at read time and
    is never stored here. Mirrors ddl_v12_plan_quarters.sql."""
    __tablename__ = "plan_quarterly_goals"

    id               = Column(Integer, primary_key=True, index=True)
    plan_id          = Column(Integer, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True)
    trimestre        = Column(Integer, nullable=False)        # 1..4 (CHECK lives in the DDL)
    meta             = Column(Text, nullable=False)
    objetivo_medible = Column(Text)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("plan_id", "trimestre", name="uq_plan_quarterly_goal"),
        CheckConstraint("trimestre BETWEEN 1 AND 4", name="ck_plan_quarterly_trimestre"),
    )


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
    # change unify-strategy-execution: two task origins + optional hito override (the ~20% rule).
    project_id               = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    milestone_id             = Column(Integer, ForeignKey("roadmap_milestones.id", ondelete="SET NULL"), nullable=True)
    origen                   = Column(Text, nullable=False, default="directa")   # directa | proyecto
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
    # Gentil's strategic analysis (ddl_v14, DeepSeek V4 Pro deep brain)
    analisis_gentil     = Column(Text)                          # executive read: why this risk matters now
    plan_mitigacion     = Column(Text)                          # JSON array of concrete mitigation steps
    fecha_analisis      = Column(DateTime(timezone=True))       # when Gentil last analysed this risk


class RoadmapVersion(Base):
    __tablename__ = "roadmap_versions"

    id          = Column(Integer, primary_key=True, index=True)
    nombre      = Column(Text, nullable=False)
    descripcion = Column(Text)
    activa      = Column(Boolean, nullable=False, default=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class RoadmapCycle(Base):
    """change unify-strategy-execution: the annual planning cycle (cadence). A plan belongs to one
    cycle (plans.ciclo_id). Distinct from RoadmapVersion (strategy snapshot). One active at a time."""
    __tablename__ = "roadmap_cycles"

    id         = Column(Integer, primary_key=True, index=True)
    anio       = Column(Integer, nullable=False, unique=True)
    nombre     = Column(Text)
    estado     = Column(Text, nullable=False, default="activo")   # activo | archivado
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RoadmapMilestone(Base):
    __tablename__ = "roadmap_milestones"

    id                    = Column(Integer, primary_key=True, index=True)
    titulo                = Column(Text, nullable=False)
    orden                 = Column(Integer, nullable=False, default=0)
    estado                = Column(Text, nullable=False, default="pendiente")   # done | in_progress | delayed | pending
    area                  = Column(Text)   # NULLABLE: hitos are company-wide (unify-strategy-execution)
    # change unify-strategy-execution: explicit year/quarter for the per-quarter roadmap and filters.
    anio                  = Column(Integer)
    trimestre             = Column(Integer)   # 1..4
    fecha_inicio          = Column(DateTime(timezone=True))
    fecha_fin_planificada = Column(DateTime(timezone=True))
    fecha_completado      = Column(DateTime(timezone=True))
    depends_on            = Column(ARRAY(Integer))                              # IDs de hitos que deben completarse antes
    version_id            = Column(Integer, ForeignKey("roadmap_versions.id", ondelete="SET NULL"), nullable=True)
    pct_completado        = Column(Numeric(5, 2), nullable=False, default=0)
    # change rigorous-progress-math: strategic-tier weight (EVM "value" proxy, since hitos have no budget).
    # The 2030 roll-up is Σ(peso·avance)/Σpeso, NOT a simple average. Default 1 = today's equal weight;
    # the CEO raises it for make-or-break hitos so strategy outvotes filler.
    peso                  = Column(Numeric(4, 2), nullable=False, default=1)
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
    # change unify-strategy-execution: emergent project (won via convocatoria) linked to the strategy.
    plan_id      = Column(Integer, ForeignKey("plans.id", ondelete="SET NULL"), nullable=True)
    milestone_id = Column(Integer, ForeignKey("roadmap_milestones.id", ondelete="SET NULL"), nullable=True)
    anio         = Column(Integer)
    origen       = Column(Text, nullable=False, default="planeado")   # convocatoria | planeado
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
    # ── completeness-interview (ddl_v9): la pregunta empresarial y su respuesta ──
    domain         = Column(Text)                # dominio del especialista (riesgos, liquidez, ...)
    grupo          = Column(Text)                # 'enrich' | 'gap'
    pregunta       = Column(Text)                # copy de producto (es)
    campos_destino = Column(Text)                # campos destino, separados por coma
    respuesta      = Column(Text)                # respuesta cruda (auditoría)
    validada_en    = Column(DateTime(timezone=True))


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


# ─── Modelos Fase 3: Oportunidades (espejo de Airtable Modalidades) ─

class Oportunidad(Base):
    """Espejo de solo-lectura de Airtable `Modalidades` (área 02) + triage local del CEO.

    Airtable sigue siendo la fuente de verdad; n8n (WF-GM-06) empuja las convocatorias
    de alto ADN vía POST /api/oportunidades/sync (upsert por airtable_record_id).
    Los nombres de columna calzan 1:1 con ddl_v6_oportunidades.sql (sin deriva ORM↔DB).
    """
    __tablename__ = "oportunidades"

    id                 = Column(Integer, primary_key=True, index=True)
    airtable_record_id = Column(Text, nullable=False, unique=True)   # clave de upsert idempotente
    nombre             = Column(Text, nullable=False)
    programa           = Column(Text)
    entidad            = Column(Text)
    presupuesto        = Column(Text)                                 # texto libre, como en Airtable
    fecha_cierre       = Column(Date)
    url_convocatoria   = Column(Text)
    pdf_bases          = Column(Text)
    adn_score          = Column(Integer)                             # 0-100
    prioridad          = Column(Text)                                # PRIORITARIA | EXPLORAR | VIGILANCIA | Vencida
    justificacion_adn  = Column(Text)
    estado_seguimiento = Column(Text, nullable=False, default="nueva")  # nueva | en_revision | perseguir | descartada
    synced_at          = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at         = Column(DateTime(timezone=True), server_default=func.now())


class DocumentChunk(Base):
    """Indexed document chunks for RAG + semantic search.

    Aligned to the REAL table columns (change wire-document-rag, closes the prior ORM<->DB drift).
    `embedding` is a JSONB float array: the production Postgres `vector` (pgvector) library is missing,
    so similarity is computed in-app (see routers/rag.py), not via the `<=>` operator.
    """
    __tablename__ = "document_chunks"

    id          = Column(Integer, primary_key=True, index=True)
    source_type = Column(Text, nullable=False)   # 'documento' | 'riesgo' | 'contrato' | ...
    source_id   = Column(Text)
    source_name = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    chunk_text  = Column(Text, nullable=False)
    embedding   = Column(JSONB)                   # float array; in-app cosine (pgvector unused)
    # 'metadata' is reserved on the Declarative Base, so the Python attr is `meta`.
    meta        = Column("metadata", JSONB)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
