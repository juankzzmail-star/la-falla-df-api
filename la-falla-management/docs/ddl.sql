-- ============================================================
-- DDL: Sistema de Gestión Estratégica — La Falla DF
-- Base: la_falla_df (PostgreSQL en EasyPanel)
-- ============================================================

-- ─── 1. Objetivos estratégicos 2030 ─────────────────────────
CREATE TABLE IF NOT EXISTS strategic_goals (
    id               SERIAL PRIMARY KEY,
    codigo           TEXT UNIQUE NOT NULL,
    titulo           TEXT NOT NULL,
    area             TEXT NOT NULL CHECK (area IN ('Comercial','Proyectos','Investigacion','Audiovisual')),
    fecha_inicio     DATE,
    fecha_fin_meta   DATE,
    peso_porcentaje  NUMERIC(5,2),
    estado           TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo','pausado','cerrado')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── 2. Planes operativos por área ───────────────────────────
CREATE TABLE IF NOT EXISTS plans (
    id                    SERIAL PRIMARY KEY,
    codigo                TEXT UNIQUE NOT NULL,
    titulo                TEXT NOT NULL,
    area                  TEXT NOT NULL CHECK (area IN ('Comercial','Proyectos','Investigacion','Audiovisual')),
    goal_id               INTEGER REFERENCES strategic_goals(id) ON DELETE SET NULL,
    responsable           TEXT,
    fecha_inicio          DATE,
    fecha_fin_planificada DATE,
    baseline_curva_s      JSONB,
    pct_completado_real   NUMERIC(5,2) NOT NULL DEFAULT 0,
    pct_completado_plan   NUMERIC(5,2) NOT NULL DEFAULT 0,
    estado                TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo','pausado','cerrado')),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── 3. Tareas atómicas ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
    id                       SERIAL PRIMARY KEY,
    plan_id                  INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    titulo                   TEXT NOT NULL,
    responsable              TEXT,
    area                     TEXT,
    fecha_inicio             DATE,
    fecha_vencimiento        DATE,
    fecha_completada         DATE,
    prioridad                TEXT NOT NULL DEFAULT 'media' CHECK (prioridad IN ('critica','alta','media','baja')),
    es_hito                  BOOLEAN NOT NULL DEFAULT FALSE,
    estado                   TEXT NOT NULL DEFAULT 'pendiente'
                             CHECK (estado IN ('pendiente','en_progreso','completada','bloqueada','cancelada')),
    motivo_bloqueo           TEXT,
    url_entregable           TEXT,
    peso_pct                 NUMERIC(5,2) NOT NULL DEFAULT 0,
    google_task_id           TEXT,
    google_calendar_event_id TEXT,
    stakeholder_id           INTEGER REFERENCES stakeholders_master(id) ON DELETE SET NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── 4. Historial de salud de stakeholders ───────────────────
CREATE TABLE IF NOT EXISTS stakeholder_health_log (
    id                           SERIAL PRIMARY KEY,
    stakeholder_id               INTEGER NOT NULL REFERENCES stakeholders_master(id) ON DELETE CASCADE,
    salud                        TEXT NOT NULL CHECK (salud IN ('verde','amarillo','rojo')),
    razon                        TEXT,
    dias_sin_contacto            INTEGER,
    calculado_en                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resultado_ultima_interaccion TEXT CHECK (resultado_ultima_interaccion IN ('positivo','neutro','negativo','bloqueo'))
);

-- ─── 5. Extender tabla interactions (existente) ───────────────
ALTER TABLE interactions
    ADD COLUMN IF NOT EXISTS resultado        TEXT DEFAULT 'neutro'
        CHECK (resultado IN ('positivo','neutro','negativo','bloqueo')),
    ADD COLUMN IF NOT EXISTS es_hito_proyecto BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS plan_id          INTEGER REFERENCES plans(id) ON DELETE SET NULL;

-- ─── 6. Índices ───────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_tasks_plan_id           ON tasks(plan_id);
CREATE INDEX IF NOT EXISTS idx_tasks_estado            ON tasks(estado);
CREATE INDEX IF NOT EXISTS idx_tasks_area              ON tasks(area);
CREATE INDEX IF NOT EXISTS idx_tasks_responsable       ON tasks(responsable);
CREATE INDEX IF NOT EXISTS idx_tasks_fecha_vencimiento ON tasks(fecha_vencimiento);
CREATE INDEX IF NOT EXISTS idx_health_log_stakeholder  ON stakeholder_health_log(stakeholder_id);
CREATE INDEX IF NOT EXISTS idx_health_log_calculado_en ON stakeholder_health_log(calculado_en DESC);

-- ─── 7. Vista: KPI macro por área (para dashboard CEO) ───────
CREATE OR REPLACE VIEW v_dashboard_ceo AS
SELECT
    p.area,
    COUNT(t.id)                                                              AS total_tareas,
    COUNT(t.id) FILTER (WHERE t.estado = 'completada')                      AS completadas,
    COUNT(t.id) FILTER (WHERE t.estado = 'bloqueada')                       AS bloqueadas,
    COUNT(t.id) FILTER (WHERE t.estado NOT IN ('completada','cancelada')
                          AND t.fecha_vencimiento < CURRENT_DATE)           AS vencidas,
    COALESCE(ROUND(AVG(p.pct_completado_real), 2), 0)                       AS pct_real,
    COALESCE(ROUND(AVG(p.pct_completado_plan), 2), 0)                       AS pct_planificado,
    CASE
        WHEN COUNT(t.id) FILTER (WHERE t.estado = 'bloqueada') > 0                      THEN 'rojo'
        WHEN COUNT(t.id) FILTER (WHERE t.estado NOT IN ('completada','cancelada')
                                   AND t.fecha_vencimiento < CURRENT_DATE) > 0          THEN 'amarillo'
        ELSE 'verde'
    END                                                                      AS semaforo
FROM plans p
LEFT JOIN tasks t ON t.plan_id = p.id
WHERE p.estado = 'activo'
GROUP BY p.area;

-- ─── 8. Vista: Curva S real acumulada por plan ────────────────
CREATE OR REPLACE VIEW v_curva_s_real AS
SELECT
    p.id                                                                          AS plan_id,
    p.titulo                                                                      AS plan_titulo,
    p.area,
    to_char(date_trunc('week', t.fecha_completada), 'IYYY-"W"IW')                AS semana,
    SUM(t.peso_pct) OVER (
        PARTITION BY p.id
        ORDER BY date_trunc('week', t.fecha_completada)
        ROWS UNBOUNDED PRECEDING
    )                                                                             AS pct_real_acumulado
FROM plans p
JOIN tasks t ON t.plan_id = p.id
WHERE t.estado = 'completada'
  AND t.fecha_completada IS NOT NULL;

-- ─── 9. Vista: Última salud por stakeholder ───────────────────
CREATE OR REPLACE VIEW v_stakeholder_health_current AS
SELECT DISTINCT ON (shl.stakeholder_id)
    shl.id,
    shl.stakeholder_id,
    shl.salud,
    shl.razon,
    shl.dias_sin_contacto,
    shl.calculado_en,
    shl.resultado_ultima_interaccion,
    sm.nombre                AS stakeholder_nombre,
    sm.clasificacion_negocio
FROM stakeholder_health_log shl
JOIN stakeholders_master sm ON sm.id = shl.stakeholder_id
ORDER BY shl.stakeholder_id, shl.calculado_en DESC;

-- ─── 10. Datos iniciales de prueba ────────────────────────────
INSERT INTO strategic_goals (codigo, titulo, area, fecha_fin_meta, peso_porcentaje)
VALUES
    ('COM-2030-01', 'Consolidar cartera de 50 clientes premium',      'Comercial',     '2030-12-31', 30),
    ('PRY-2030-01', 'Ejecutar 20 proyectos audiovisuales anuales',     'Proyectos',     '2030-12-31', 25),
    ('INV-2030-01', 'Posicionamiento como referente en 3 verticales',  'Investigacion', '2030-12-31', 20),
    ('AUD-2030-01', 'Producción propia con distribución nacional',     'Audiovisual',   '2030-12-31', 25)
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO plans (codigo, titulo, area, goal_id, responsable, fecha_inicio, fecha_fin_planificada,
                   baseline_curva_s, pct_completado_plan)
SELECT
    p.codigo, p.titulo, p.area, g.id, p.responsable, p.fecha_inicio, p.fecha_fin,
    p.baseline, p.pct_plan
FROM (VALUES
    ('COM-PLAN-2026', 'Plan Comercial Q2 2026', 'Comercial',     'COM-2030-01',
     'JC', '2026-04-01'::date, '2026-06-30'::date,
     '[{"semana":"2026-W14","pct_planificado":10},{"semana":"2026-W18","pct_planificado":30},{"semana":"2026-W22","pct_planificado":60},{"semana":"2026-W26","pct_planificado":100}]'::jsonb,
     25.0),
    ('PRY-PLAN-2026', 'Plan Proyectos Q2 2026', 'Proyectos',     'PRY-2030-01',
     'Iván', '2026-04-01'::date, '2026-06-30'::date,
     '[{"semana":"2026-W14","pct_planificado":10},{"semana":"2026-W18","pct_planificado":35},{"semana":"2026-W22","pct_planificado":70},{"semana":"2026-W26","pct_planificado":100}]'::jsonb,
     20.0),
    ('INV-PLAN-2026', 'Plan Investigación Q2 2026', 'Investigacion', 'INV-2030-01',
     'Beto', '2026-04-01'::date, '2026-06-30'::date,
     '[{"semana":"2026-W14","pct_planificado":15},{"semana":"2026-W18","pct_planificado":40},{"semana":"2026-W22","pct_planificado":75},{"semana":"2026-W26","pct_planificado":100}]'::jsonb,
     15.0),
    ('AUD-PLAN-2026', 'Plan Audiovisual Q2 2026', 'Audiovisual',  'AUD-2030-01',
     'Clementino', '2026-04-01'::date, '2026-06-30'::date,
     '[{"semana":"2026-W14","pct_planificado":5},{"semana":"2026-W18","pct_planificado":25},{"semana":"2026-W22","pct_planificado":60},{"semana":"2026-W26","pct_planificado":100}]'::jsonb,
     10.0)
) AS p(codigo, titulo, area, goal_codigo, responsable, fecha_inicio, fecha_fin, baseline, pct_plan)
JOIN strategic_goals g ON g.codigo = p.goal_codigo
ON CONFLICT (codigo) DO NOTHING;

-- Tareas de prueba por plan
INSERT INTO tasks (plan_id, titulo, responsable, area, fecha_inicio, fecha_vencimiento, prioridad, es_hito, peso_pct, estado)
SELECT p.id, t.titulo, t.responsable, p.area, t.fi, t.fv, t.prioridad, t.hito, t.peso, t.estado
FROM (VALUES
    ('COM-PLAN-2026', 'Prospección 10 nuevos contactos premium', 'JC',    '2026-04-15'::date, '2026-04-30'::date, 'alta',   false, 20.0, 'completada'),
    ('COM-PLAN-2026', 'Reunión de cierre con 5 prospectos',      'JC',    '2026-05-15'::date, '2026-05-30'::date, 'alta',   true,  30.0, 'en_progreso'),
    ('COM-PLAN-2026', 'Firma de 3 contratos nuevos',             'JC',    '2026-06-01'::date, '2026-06-20'::date, 'critica',true,  50.0, 'pendiente'),
    ('PRY-PLAN-2026', 'Kick-off proyecto audiovisual Q2',        'Iván',  '2026-04-05'::date, '2026-04-15'::date, 'alta',   true,  25.0, 'completada'),
    ('PRY-PLAN-2026', 'Entrega pre-producción',                  'Iván',  '2026-05-01'::date, '2026-05-20'::date, 'alta',   false, 35.0, 'en_progreso'),
    ('PRY-PLAN-2026', 'Entrega final y facturación',             'Iván',  '2026-06-15'::date, '2026-06-30'::date, 'critica',true,  40.0, 'pendiente'),
    ('INV-PLAN-2026', 'Mapeo de verticales de mercado',          'Beto',  '2026-04-01'::date, '2026-04-20'::date, 'media',  false, 30.0, 'completada'),
    ('INV-PLAN-2026', 'Reporte de inteligencia competitiva',     'Beto',  '2026-05-01'::date, '2026-05-25'::date, 'alta',   true,  40.0, 'en_progreso'),
    ('INV-PLAN-2026', 'Presentación a Clementino',              'Beto',  '2026-06-10'::date, '2026-06-20'::date, 'alta',   true,  30.0, 'pendiente'),
    ('AUD-PLAN-2026', 'Definición de línea editorial',          'Clementino','2026-04-05'::date,'2026-04-25'::date,'alta',  false, 20.0, 'completada'),
    ('AUD-PLAN-2026', 'Producción episodio piloto',             'Clementino','2026-05-01'::date,'2026-05-30'::date,'critica',true, 50.0, 'pendiente'),
    ('AUD-PLAN-2026', 'Distribución y lanzamiento',             'Clementino','2026-06-01'::date,'2026-06-30'::date,'critica',true, 30.0, 'pendiente')
) AS t(plan_codigo, titulo, responsable, fi, fv, prioridad, hito, peso, estado)
JOIN plans p ON p.codigo = t.plan_codigo
WHERE NOT EXISTS (SELECT 1 FROM tasks WHERE plan_id = p.id AND titulo = t.titulo);

-- Recalcular pct_completado_real desde tareas de prueba
UPDATE plans p
SET pct_completado_real = (
    SELECT COALESCE(SUM(peso_pct), 0)
    FROM tasks
    WHERE plan_id = p.id AND estado = 'completada'
);

-- ─── Verificación ─────────────────────────────────────────────
-- SELECT * FROM v_dashboard_ceo;
-- SELECT * FROM v_curva_s_real LIMIT 20;
