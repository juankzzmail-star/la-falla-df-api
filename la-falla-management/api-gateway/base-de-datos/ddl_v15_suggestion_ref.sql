-- ddl_v15 (change gentil-task-coverage): machine-readable target on coverage suggestions.
-- JSON {"kind":"plan"|"hito","id":N,"area":...}; NULL on ordinary (morning) suggestions.
-- Also self-applied lazily by the app at startup (_coverage._ensure_ref_column), so running
-- this file manually is optional — it exists for the record and for fresh provisioning.
ALTER TABLE daily_suggestions ADD COLUMN IF NOT EXISTS ref TEXT;
