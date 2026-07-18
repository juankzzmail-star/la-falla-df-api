-- ddl_v14: Gentil's strategic analysis on each risk (powered by DeepSeek V4 Pro).
--
-- Fills the long-promised "Heartbeat Matutino" placeholder in the Risk Map modal:
-- per-risk executive analysis + a concrete mitigation plan, written by Gentil's deep
-- brain (DeepSeek V4 Pro) — reserved for strategic reasoning, not the daily Groq path.
--
--  analisis_gentil : free-text executive read of the risk (why it matters now).
--  plan_mitigacion : JSON array of concrete mitigation steps (the frontend renders a <ul>).
--  fecha_analisis  : when Gentil last analysed this risk (drives staleness on the radar).

ALTER TABLE risks ADD COLUMN IF NOT EXISTS analisis_gentil TEXT;
ALTER TABLE risks ADD COLUMN IF NOT EXISTS plan_mitigacion TEXT;
ALTER TABLE risks ADD COLUMN IF NOT EXISTS fecha_analisis  TIMESTAMPTZ;
