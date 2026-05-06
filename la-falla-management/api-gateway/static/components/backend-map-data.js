/* BACKEND MAP DATA — La Falla D.F. · Centro de Mando v1.4 */
const MAP_DATA = {
  summary: { ok:12, warn:6, miss:5, tools:11 },

  uiElements: [
    // Panel General
    { id:'pulso', name:'Pulso del Colectivo', desc:'Heatmap 4x7 salud humana por dirección/día. Fórmula: Salud = Σ(S_GCF+S_GP+S_GI+S_GA)/4',
      endpoint:'GET /health-heatmap', tables:['stakeholder_health_log','area_kpi_config'], workflow:'WF-GM-01 · 6AM', status:'ok',
      gap:'Datos hardcoded. Conectar endpoint. Las 4 direcciones mapean a: Clementino (GCF), JC (GP), Beto (GI), Iván (GA).' },

    { id:'2030', name:'Hacia 2030 · Radial Gauge', desc:'4 arcos: Eje Estrat. 58%, Captación 65%, Entregas 78%, Riesgo 22%',
      endpoint:'GET /roadmap-2030', tables:['roadmap_milestones','strategic_goals','roadmap_versions'], workflow:'WF-GM-03 · lunes 8AM', status:'ok',
      gap:'Porcentajes hardcoded. Drill-down con checklist de hitos alineado con tabla roadmap_milestones (Sprint 1).' },

    { id:'caja', name:'Aire en la Caja', desc:'Barras 12 meses. Drill-down con flujos 90 días.',
      endpoint:'GET /financial-snapshots', tables:['financial_snapshots','financial_flows'], workflow:'WF-GM-01 vía Google Sheets Quinaya', status:'warn',
      gap:'Endpoint no listado explícitamente en api-gerencia. Confirmar si es GET /dashboard/financial o agregar a FastAPI.' },

    { id:'lectura', name:'Lectura del Día', desc:'3 sugerencias IA · Aceptar/Corregir/Eliminar',
      endpoint:'GET /openclaw-executive-feed · PATCH /suggestions/{id}/status', tables:['executive_feed_cache','daily_suggestions'], workflow:'WF-GM-05 · 6:30AM (Sprint 6)', status:'warn',
      gap:'UI usa Claude API directamente hoy (fallback válido). En producción: leer de executive_feed_cache. Las acciones ✓✎× deben PATCH al endpoint.' },

    { id:'upload', name:'Subir Recurso', desc:'PDF/DOCX/Link + modal intención (3 opciones)',
      endpoint:'POST /ingest/resource', tables:['operational_assets'], workflow:'WF-GM-06 · invalidación cache (Sprint 6)', status:'ok',
      gap:'3 intenciones → intent_type correcto. Links Google Drive → source_url. Alineado.' },

    { id:'claw', name:'Gentil Chat Drawer', desc:'Chat con Gentil · selector 3 modelos (Haiku/Sonnet/Opus)',
      endpoint:'WebSocket port 18789 / Chatwoot', tables:[], workflow:'—', status:'warn',
      gap:'Actualmente window.claude.complete(). Producción: conectar a Gentil vía port 18789. LLM Router: Haiku 50%, Sonnet 35%, Opus 15%.' },

    { id:'sidebar', name:'Sidebar · Bandeja de Entrada', desc:'Notas de Captura Rápida + docs diferidos',
      endpoint:'GET /inbox · POST /inbox', tables:['strategic_decisions','inbox_items'], workflow:'WF-GM-02 · webhook notifications', status:'warn',
      gap:'Bandeja local (estado React). En producción: leer de strategic_decisions o tabla dedicada inbox_items (agregar).' },

    { id:'directorio', name:'Sidebar · Directorio Contactos', desc:'Stakeholders con edición/eliminación inline',
      endpoint:'GET/POST/PATCH/DELETE /stakeholders', tables:['stakeholders'], workflow:'—', status:'ok',
      gap:'Tabla stakeholders existe. CRUD completo alineado. Agregar campo linkedin a schema.' },

    { id:'fab', name:'FAB · Captura Rápida', desc:'Nota que va a Bandeja de Entrada',
      endpoint:'POST /inbox', tables:['inbox_items'], workflow:'WF-GM-05 procesa al final del día', status:'warn',
      gap:'Necesita endpoint POST /inbox o equivalente en api-gerencia. WF-GM-05 consume bandeja.' },

    { id:'proyectos', name:'Dashboard de Proyectos', desc:'4 proyectos · presupuesto · checklist · docs vinculados',
      endpoint:'GET /projects · GET /projects/{id}', tables:['projects','deliverables','project_documents'], workflow:'WF-GM-03 reporta estado', status:'warn',
      gap:'Estructura de datos alineada. Endpoints existen implícitamente. Confirmar en api-gerencia docs.' },

    { id:'rail', name:'Rail · Tablero Ejecutivo', desc:'Foco semana · hito próximo · riesgo abierto',
      endpoint:'GET /dashboard/summary', tables:['risks','roadmap_milestones','cross_area_synergies'], workflow:'WF-GM-01 alimenta resumen', status:'ok',
      gap:'Datos del tablero ejecutivo vienen de dashboard/summary. Alineado con tabla risks y milestones.' },

    { id:'risk', name:'Mapa de Riesgos 4×4', desc:'Impact vs Probabilidad · 5 pins activos',
      endpoint:'GET /risks', tables:['risks'], workflow:'—', status:'ok',
      gap:'Tabla risks con campos impact, probability, area_id. Completamente alineado.' },

    { id:'exec-seg', name:'Ejecución 2030 · 16 segmentos', desc:'Hitos completados vs pendientes vs en riesgo',
      endpoint:'GET /roadmap-2030', tables:['roadmap_milestones'], workflow:'—', status:'ok',
      gap:'Mapea directamente a roadmap_milestones.status (done/in_progress/delayed/pending).' },
  ],

  missing: [
    { name:'Indicadores por área configurables', desc:'Los KPIs de cada Dirección deben ser editables por el CEO. Tabla area_kpi_config existe pero la UI no tiene formulario de edición aún.', endpoint:'PATCH /kpi-config/{area_id}' },
    { name:'Estado de Workflows n8n en header', desc:'Los dots de estado (POSTGRES · N8N · CHATWOOT) son estáticos. Conectar a GET /health/services.', endpoint:'GET /health/services' },
    { name:'Versionado de documentos estratégicos', desc:'La UI muestra lista de docs subidos pero sin historial de versiones. Agregar GET /resources/{id}/versions.', endpoint:'GET /resources/{id}/versions' },
    { name:'Notificaciones push / alertas activas', desc:'WF-GM-02 envía webhooks de alertas. La UI no tiene listener de WebSocket para alertas en tiempo real.', endpoint:'WebSocket /ws/alerts' },
    { name:'Acciones aprobación/rechazo de planes IA', desc:'Los botones Aceptar/Corregir/Eliminar de la Lectura del Día no llaman al backend. Necesita PATCH /suggestions/{id}/status.', endpoint:'PATCH /suggestions/{id}/status' },
  ],

  gentilConfig: {
    models: [
      { name:'Claude Haiku 4.5', pct:50, use:'Consultas operativas rápidas. Respuestas cortas.' },
      { name:'Claude Sonnet', pct:35, use:'Análisis de documentos, planes estratégicos.' },
      { name:'Claude Opus', pct:15, use:'Decisiones de alto impacto, síntesis ejecutiva.' },
    ],
    mcpTools: [
      'list_databases','get_table_info','query_table',
      'create_record','update_record','delete_record',
      'create_task','list_tasks','update_task_status',
      'search_contacts','create_contact'
    ],
    port:18789,
    apiKey:'e2443bb...51e31c1',
    files:['SOUL.md','MEMORY.md','IDENTITY_GERENCIA.md'],
  },
};

window.MAP_DATA = MAP_DATA;
