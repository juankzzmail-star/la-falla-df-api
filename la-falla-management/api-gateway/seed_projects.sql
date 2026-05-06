-- Seed de proyectos de prueba — La Falla D.F. · Centro de Mando v1.4
-- Ejecutar DESPUÉS de ddl_v2.sql (las tablas ya deben existir)

INSERT INTO projects (codigo, nombre, area, presupuesto, ejecutado, estado)
VALUES
  ('rc02',   'Rutas Cafeteras 02',   'Proyectos',    120000000, 86400000, 'activo'),
  ('pileje',  'Piloto Eje',           'Audiovisual',   45000000, 27900000, 'activo'),
  ('labris',  'Laboratorio Risaralda','Investigacion', 30000000, 18000000, 'activo'),
  ('acmi26',  'Cumbre ACMI 2026',     'Comercial',     65000000, 22100000, 'activo')
ON CONFLICT (codigo) DO NOTHING;

-- Entregables Rutas Cafeteras 02
WITH p AS (SELECT id FROM projects WHERE codigo='rc02')
INSERT INTO deliverables (project_id, titulo, completado, orden)
SELECT p.id, titulo, completado, orden FROM p, (VALUES
  ('Rough cut episodio 1',        TRUE,  0),
  ('Guion episodio 2',            TRUE,  1),
  ('Rodaje episodio 2 (día 3/5)', FALSE, 2),
  ('Post-producción ep. 1',       FALSE, 3),
  ('Entrega final ep. 1',         FALSE, 4)
) AS t(titulo, completado, orden)
ON CONFLICT DO NOTHING;

-- Entregables Piloto «Eje»
WITH p AS (SELECT id FROM projects WHERE codigo='pileje')
INSERT INTO deliverables (project_id, titulo, completado, orden)
SELECT p.id, titulo, completado, orden FROM p, (VALUES
  ('Casting confirmado',  TRUE,  0),
  ('Locaciones scout',    TRUE,  1),
  ('Rodaje (día 3/5)',    FALSE, 2),
  ('Edición piloto',      FALSE, 3)
) AS t(titulo, completado, orden)
ON CONFLICT DO NOTHING;

-- Entregables Laboratorio Risaralda
WITH p AS (SELECT id FROM projects WHERE codigo='labris')
INSERT INTO deliverables (project_id, titulo, completado, orden)
SELECT p.id, titulo, completado, orden FROM p, (VALUES
  ('Mapeo territorial',            TRUE,  0),
  ('Talleres comunitarios (4/6)',  FALSE, 1),
  ('Documento síntesis',           FALSE, 2)
) AS t(titulo, completado, orden)
ON CONFLICT DO NOTHING;

-- Entregables Cumbre ACMI 2026
WITH p AS (SELECT id FROM projects WHERE codigo='acmi26')
INSERT INTO deliverables (project_id, titulo, completado, orden)
SELECT p.id, titulo, completado, orden FROM p, (VALUES
  ('Programa confirmado',       TRUE,  0),
  ('Invitados nacionales',      TRUE,  1),
  ('Invitados internacionales', FALSE, 2),
  ('Producción evento',         FALSE, 3),
  ('Cobertura audiovisual',     FALSE, 4)
) AS t(titulo, completado, orden)
ON CONFLICT DO NOTHING;
