-- ddl_v12_plan_quarters.sql — change plan-quarterly-milestones
-- Additive: the quarterly goals (Q1–Q4) live on the PLAN, not the hito (model §12, D9–D11).
-- The per-quarter % is DERIVED from real task completion (never stored here). No column is dropped;
-- roadmap_milestones.trimestre stays (now vestigial) and plans.baseline_curva_s stays (now legacy).

CREATE TABLE IF NOT EXISTS plan_quarterly_goals (
    id                INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id           INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    trimestre         INTEGER NOT NULL CHECK (trimestre BETWEEN 1 AND 4),
    meta              TEXT    NOT NULL,
    objetivo_medible  TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (plan_id, trimestre)
);

-- One plan's four quarters are read together; index the FK for the per-plan lookup.
CREATE INDEX IF NOT EXISTS ix_plan_quarterly_goals_plan_id ON plan_quarterly_goals (plan_id);
