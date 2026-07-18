-- ddl_v13_milestone_peso.sql — change rigorous-progress-math
-- Additive: strategic-tier weight per hito. The 2030 roll-up becomes a budget-weighted average
-- (EVM EV/BAC style): v2030 = Σ(peso·avance)/Σpeso, NOT a simple average of the 16 hitos.
-- Default 1 reproduces today's equal-weight behavior exactly; the CEO raises peso for the
-- make-or-break hitos so strategy outvotes filler. No column is dropped.
ALTER TABLE roadmap_milestones ADD COLUMN IF NOT EXISTS peso NUMERIC(4,2) NOT NULL DEFAULT 1;
