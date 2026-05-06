/* Centro de Mando v1.4 — datos en vivo desde api-gerencia */
const { useState, useEffect, useRef, useMemo } = React;

/* Suscribe al ciclo de carga de api-client.js y devuelve la clave pedida */
function useApiData(key) {
  const [val, setVal] = useState(()=> window.__CM_DATA__ ? window.__CM_DATA__[key] : null);
  useEffect(()=>{
    const refresh = ()=> setVal(window.__CM_DATA__ ? window.__CM_DATA__[key] : null);
    window.__CM_LISTENERS__ = window.__CM_LISTENERS__ || [];
    window.__CM_LISTENERS__.push(refresh);
    return ()=>{ window.__CM_LISTENERS__ = (window.__CM_LISTENERS__||[]).filter(l=>l!==refresh); };
  },[key]);
  return val;
}

/* Carga datos de un área específica desde el API (on-demand al abrir deploy) */
const AREA_ID_MAP = { gcf:'Comercial', gp:'Proyectos', gi:'Investigacion', ga:'Audiovisual' };
function useAreaData(areaId) {
  const [data, setData] = useState(null);
  useEffect(()=>{
    if(!areaId){ setData(null); return; }
    const area = AREA_ID_MAP[areaId];
    if(!area){ setData(null); return; }
    const k = window.__API_KEY__ || '';
    const b = (window.__API_BASE__ || '').replace(/\/$/,'');
    fetch(`${b}/dashboard/area/${area}`, { headers: k ? {'X-API-Key':k} : {} })
      .then(r => r.ok ? r.json() : null)
      .then(setData)
      .catch(()=> setData(null));
  }, [areaId]);
  return data;
}

/* ============================================================
   ICONS
   ============================================================ */
const I = {
  sun:  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>,
  moon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>,
  coin: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="12" cy="12" r="8"/><path d="M12 7v10M9.5 9.5c0-1.1 1.1-2 2.5-2s2.5.9 2.5 2-1.1 2-2.5 2-2.5.9-2.5 2 1.1 2 2.5 2 2.5-.9 2.5-2"/></svg>,
  clap: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><rect x="3" y="6" width="18" height="14" rx="2"/><path d="M3 10h18M7 6l2 4M12 6l2 4M17 6l2 4"/></svg>,
  map:  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M9 3L3 5v16l6-2 6 2 6-2V3l-6 2-6-2z"/><path d="M9 3v16M15 5v16"/></svg>,
  cam:  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><rect x="2" y="7" width="14" height="12" rx="2"/><path d="M16 11l6-3v10l-6-3z"/></svg>,
  plus: '+', x:'×', send:'→', check:'✓', edit:'✎',
};

/* ============================================================
   HEADER
   ============================================================ */
function Header({ theme, onTheme, onOpenClaw, onUpload, onMenu }){
  const [now, setNow] = useState(new Date());
  useEffect(()=>{ const t=setInterval(()=>setNow(new Date()),1000); return ()=>clearInterval(t); },[]);
  const hh = String(now.getHours()).padStart(2,'0');
  const mm = String(now.getMinutes()).padStart(2,'0');
  const ss = String(now.getSeconds()).padStart(2,'0');
  const health = useApiData('health');
  const dot = (svc) => {
    const st = health ? health[svc] : null;
    return st === 'ok' ? 'ok' : st === 'error' ? 'err' : '';
  };
  return (
    <header className="hdr">
      <button className="hdr-menu" onClick={onMenu} title="Menú">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M2 4h14M2 9h14M2 14h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>
      </button>
      <div className="hdr-brand">
        <span className="wm">LA FALLA</span>
        <span className="nm">D.F.</span>
        <span className="slash">/</span>
        <span className="mod">Centro de Mando</span>
      </div>
      <div className="hdr-spacer"/>
      <div className="hdr-status">
        <span className="s"><span className={'d ' + dot('postgres')}/>POSTGRES</span>
        <span className="sep">·</span>
        <span className="s"><span className={'d ' + dot('n8n')}/>n8n</span>
        <span className="sep">·</span>
        <span className="s"><span className={'d ' + dot('chatwoot')}/>CHATWOOT</span>
        <span className="sep">·</span>
        <span className="s"><span className={'d ' + dot('drive')}/>DRIVE</span>
      </div>
      <span className="hdr-clock tabular">{hh}:{mm}:{ss}</span>
      <button className="hdr-upload" onClick={onUpload} title="Subir recurso">
        <span className="arr">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M7 11V3M7 3L3.5 6.5M7 3L10.5 6.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </span>
        SUBIR RECURSO
      </button>
      <button className="hdr-gentil" onClick={onOpenClaw}>
        <span className="pulse"/>
        <span className="gentil-brand-name">Gentil</span>
      </button>
      <button className="hdr-theme" onClick={onTheme} title="Tema">
        {theme==='dark' ? I.sun : I.moon}
      </button>
    </header>
  );
}

/* ============================================================
   SUB-HEADER (contexto + filtros + botones estratégicos)
   ============================================================ */
function SubHeader({ period, setPeriod, onRoadmap, onVision }){
  const today = new Date();
  const dia = today.toLocaleDateString('es-CO',{weekday:'long', day:'numeric', month:'long'});
  return (
    <div className="sub-hdr">
      <div className="context">
        <strong>{dia.charAt(0).toUpperCase()+dia.slice(1)}</strong> · cuatro áreas en marcha · 3 decisiones pendientes · foco del día: alianzas Q2
      </div>
      <div className="seg">
        {['Hoy','Semana','Mensual'].map(p => (
          <button key={p} className={period===p?'on':''} onClick={()=>setPeriod(p)}>{p}</button>
        ))}
      </div>
      <div className="year-btns">
        <button className="year-btn" onClick={onRoadmap}>
          <span className="lbl">Hoja de Ruta</span>
          <span>2026</span>
        </button>
        <button className="year-btn accent" onClick={onVision}>
          <span className="lbl">Visión</span>
          <span>2030</span>
        </button>
      </div>
    </div>
  );
}

/* ============================================================
   KPIs — 3 gráficos principales (clickables, abren detalle)
   ============================================================ */

// ---- PULSO: heatmap de áreas × días ----
// Valores: 4=Óptimo (feedback>4.5, 0h extra) | 3=Estable (≤40h) | 2=Fricción (sobrecosto/caída) | 1=Crítico (>50h o <10% libres)
const PULSO_ROWS = [
  { area:'GCF · Comercial',   values:[3,3,4,4,3,3,4], score:78 },
  { area:'GP  · Proyectos',   values:[3,2,2,1,1,2,2], score:64 },  // Rutas Cafeteras 02: presión escalando
  { area:'GI  · Investig.',   values:[4,4,4,3,4,4,3], score:82 },
  { area:'GA  · Audiovisual', values:[3,3,2,2,2,1,3], score:66 },  // Piloto día 3/5: intensidad alta
];
const DAYS = ['L','M','X','J','V','S','D'];

function PulsoViz({ compact=false, rows }){
  const data = rows || PULSO_ROWS;
  return (
    <div className={'pulso-heat' + (compact?' compact':'')}>
      {compact ? null : (
        <div className="pulso-head">
          <span className="pulso-axis">ÁREAS ↓ · DÍAS →</span>
          <div className="pulso-days">{DAYS.map(d=><span key={d}>{d}</span>)}</div>
        </div>
      )}
      <div className="pulso-rows">
        {data.map(r=>(
          <div key={r.area} className="pulso-row">
            {!compact && <span className="pulso-label">{r.area}</span>}
            <div className="pulso-cells">
              {r.values.map((v,i)=><span key={i} className={'px v'+v}/>)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---- HACIA 2030: radial gauge de arcos concéntricos ----
const VISION_ARCS = [
  { label:'RIESGO',      value:22, color:'#E8A02C' },
  { label:'ENTREGAS',    value:78, color:'var(--falla)' },
  { label:'CAPTACIÓN',   value:65, color:'var(--falla)' },
  { label:'EJE ESTRAT.', value:58, color:'var(--ink)'   },
];
function RadialViz({ size=180, arcs }){
  const data = arcs || VISION_ARCS;
  const cx = size/2, cy = size/2;
  const strokeW = size/14;
  return (
    <div className="radial-viz">
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size}>
        {data.map((a,i)=>{
          const r = (size/2) - strokeW/2 - i*(strokeW+2);
          const C = 2*Math.PI*r;
          const dash = (a.value/100) * C;
          return (
            <g key={a.label} transform={`rotate(-90 ${cx} ${cy})`}>
              <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--line)" strokeWidth={strokeW}/>
              <circle cx={cx} cy={cy} r={r} fill="none" stroke={a.color} strokeWidth={strokeW}
                      strokeLinecap="round" strokeDasharray={`${dash} ${C}`}/>
            </g>
          );
        })}
      </svg>
      <div className="radial-legend">
        {data.map(a=>(
          <div key={a.label} className="rl">
            <span className="rl-dot" style={{background:a.color}}/>
            <span className="rl-l">{a.label}</span>
            <span className="rl-v num-mono">{a.value}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---- AIRE: barras verticales de tendencia (caja 12 meses) ----
const CAJA_MONTHS = [
  ['M',6.4],['J',6.1],['J',5.8],['A',6.2],['S',6.9],['O',7.4],
  ['N',7.8],['D',8.1],['E',8.4],['F',8.7],['M',9.0],['A',9.2],
];
function CajaViz({ compact=false, months }){
  const data = months && months.length >= 2 ? months : CAJA_MONTHS;
  const max = Math.max(...data.map(m=>m[1]));
  return (
    <div className={'caja-bars' + (compact?' compact':'')}>
      {data.map(([m,v],i)=>{
        const isLast = i===data.length-1;
        return (
          <div key={i} className="cb-col">
            <div className={'cb-bar' + (isLast?' peak':'')}
                 style={{height: (v/max*100)+'%'}}/>
            {!compact && <span className="cb-m">{m}</span>}
          </div>
        );
      })}
    </div>
  );
}

function KPIs({ onOpen }){
  const pulso = useApiData('pulso');
  const arcs  = useApiData('arcs');
  const caja  = useApiData('caja');

  const saludScore = pulso ? Math.round(pulso.salud_global) : 72;
  const saludDelta = pulso ? (pulso.delta >= 0 ? '+' : '') + pulso.delta : '+4';
  const v2030arc   = arcs  ? arcs.find(a=>a.label==='EJE ESTRAT.') : null;
  const v2030val   = v2030arc ? Math.round(v2030arc.value) : 58;
  const cajaMonto  = caja ? caja.latest.total : 9.2;
  const cajaMeses  = caja ? caja.latest.meses : 9;

  return (
    <div className="kpis">
      <button className="kpi kpi-click" onClick={()=>onOpen('pulso')}>
        <div className="eye">PULSO DEL COLECTIVO</div>
        <h3>Salud operativa global</h3>
        <div className="big">
          <span className="n tabular">{saludScore}</span>
          <span className="u">/ 100</span>
          <span className={'delta ' + (pulso && pulso.delta < 0 ? 'dn' : 'up')}>{saludDelta}</span>
        </div>
        <div className="foot">Equilibrio entre áreas · 3 de 4 en verde</div>
        <PulsoViz compact rows={pulso ? pulso.rows : null}/>
        <span className="kpi-open">Ver detalle →</span>
      </button>

      <button className="kpi kpi-click" onClick={()=>onOpen('vision')}>
        <div className="eye">HACIA 2030</div>
        <h3>Ejecución estratégica</h3>
        <div className="big">
          <span className="n tabular">{v2030val}</span>
          <span className="u">%</span>
          <span className="delta up">+6</span>
        </div>
        <div className="foot">Captación adelantada · ejecución al ritmo</div>
        <div className="kpi-radial-mini">
          <RadialViz size={130} arcs={arcs}/>
        </div>
        <span className="kpi-open">Ver detalle →</span>
      </button>

      <button className="kpi kpi-click" onClick={()=>onOpen('caja')}>
        <div className="eye">AIRE EN LA CAJA</div>
        <h3>Liquidez operativa · 12 meses</h3>
        <div className="big">
          <span className="n tabular">{cajaMonto}</span>
          <span className="u">M COP</span>
          <span className="delta up">+0.8M</span>
        </div>
        <div className="foot">{cajaMeses} meses de respiración · tendencia al alza</div>
        <CajaViz months={caja ? caja.months : null}/>
        <span className="kpi-open">Ver detalle →</span>
      </button>
    </div>
  );
}

/* ============================================================
   LECTURA DEL DÍA — stack vertical
   ============================================================ */
const INITIAL_SUGS = [
  { id:'s1', tag:'PROYECTOS', title:'Revisar sobrecosto Rutas Cafeteras 02',
    body:'Desviación +7% detectada · 20 min para validar nueva línea base.' },
  { id:'s2', tag:'COMERCIAL', title:'Enviar propuesta a Gob. Risaralda',
    body:'Alianza abierta hace 12 días · ventana óptima esta semana.' },
  { id:'s3', tag:'AUDIOVISUAL', title:'Aprobar guion Cumbre ACMI',
    body:'Entrega compromiso: viernes · pendiente revisión final tuya.' },
  { id:'s4', tag:'INVEST.', title:'Archivar territorio piloto «Eje»',
    body:'Campo completo · listo para síntesis cartográfica.' },
];

function Lectura(){
  const apiSugs = useApiData('suggestions');
  const [sugs, setSugs] = useState(INITIAL_SUGS);
  const initialized = useRef(false);
  useEffect(()=>{
    if (apiSugs && !initialized.current) {
      initialized.current = true;
      setSugs(apiSugs);
    }
  }, [apiSugs]);
  const [leaving, setLeaving] = useState({});
  const [editSug, setEditSug] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [editBody, setEditBody] = useState('');

  const resolve = (id, estado='eliminada') => {
    setLeaving(p => ({...p, [id]:true}));
    setTimeout(()=> setSugs(list => list.filter(s=>s.id!==id)), 320);
    const k = window.__API_KEY__ || '';
    const b = (window.__API_BASE__ || '').replace(/\/$/,'');
    fetch(`${b}/dashboard/suggestions/${id}/status`, {
      method: 'PATCH',
      headers: {'Content-Type':'application/json', ...(k ? {'X-API-Key':k} : {})},
      body: JSON.stringify({estado}),
    }).catch(()=>{});
  };

  const openEdit = (s) => { setEditSug(s); setEditTitle(s.title); setEditBody(s.body); };
  const saveEdit = () => {
    if (!editSug) return;
    setSugs(list => list.map(s => s.id===editSug.id ? {...s, title:editTitle, body:editBody} : s));
    setEditSug(null);
  };

  const visible = sugs.slice(0,3);
  return (
    <div className="lectura">
      <div className="lectura-head">
        <div>
          <div className="t">LECTURA DEL DÍA · <span className="gentil-brand-name">Gentil</span></div>
          <h2>Tres movimientos <em>sugeridos</em></h2>
        </div>
        <div className="count tabular">{visible.length} / {sugs.length}</div>
      </div>
      <div className="sug-stack">
        {visible.length === 0 && (
          <div className="sug-empty">Todo resuelto por hoy. Respira.</div>
        )}
        {visible.map((s,i) => (
          <div key={s.id} className={'sug ' + (leaving[s.id]?'out':'')}>
            <span className="idx tabular">0{i+1}</span>
            <div className="body">
              <strong><span className="tag">{s.tag}</span>{s.title}</strong>
              <span>{s.body}</span>
            </div>
            <div className="sug-acts">
              <button className="ok" title="Aceptar" onClick={()=>resolve(s.id,'aceptada')}>{I.check}</button>
              <button title="Editar" onClick={()=>openEdit(s)}>{I.edit}</button>
              <button className="rm" title="Eliminar" onClick={()=>resolve(s.id,'eliminada')}>{I.x}</button>
            </div>
          </div>
        ))}
      </div>

      {editSug && (
        <div className="sug-edit-scrim" onClick={()=>setEditSug(null)}>
          <div className="sug-edit-box" onClick={e=>e.stopPropagation()}>
            <div className="sug-edit-hd">
              <span className="tag">{editSug.tag}</span>
              <span style={{fontFamily:'var(--f-sub)',fontSize:10,color:'var(--mute)',letterSpacing:'.1em'}}>EDITAR MOVIMIENTO</span>
              <button className="deploy-close" onClick={()=>setEditSug(null)} style={{marginLeft:'auto'}}>{I.x}</button>
            </div>
            <input
              className="sug-edit-title"
              value={editTitle}
              onChange={e=>setEditTitle(e.target.value)}
              placeholder="Título del movimiento…"
            />
            <textarea
              className="sug-edit-body"
              value={editBody}
              onChange={e=>setEditBody(e.target.value)}
              placeholder="Describe el contexto y la acción concreta…"
              rows={3}
            />
            <div className="sug-edit-acts">
              <button className="sug-edit-cancel" onClick={()=>setEditSug(null)}>Cancelar</button>
              <button className="sug-edit-save ok" onClick={saveEdit}>Guardar cambio</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ============================================================
   EJECUCIÓN 2030 + MAPA DE RIESGOS
   ============================================================ */
const SEGS_FALLBACK = [
  { s:'done', t:'Identidad de marca' },
  { s:'done', t:'Plataforma digital' },
  { s:'done', t:'Red de aliados 1' },
  { s:'done', t:'Piloto Eje' },
  { s:'done', t:'Alianzas ministerio' },
  { s:'done', t:'Modelo financiero' },
  { s:'done', t:'Equipo base' },
  { s:'done', t:'Gobierno de datos' },
  { s:'done', t:'Narrativa pública' },
  { s:'prog', t:'Cumbre ACMI (en curso)' },
  { s:'late', t:'Laboratorio Risaralda' },
  { s:'late', t:'Memoria 2025' },
  { s:'', t:'Red de aliados 2' },
  { s:'', t:'Circuito Audiovisual' },
  { s:'', t:'Territorio Caribe' },
  { s:'', t:'Escalado nacional' },
];

const SEG_DETAIL = {
  'Identidad de marca': {
    cuando:'Q1 2024', descripcion:'Logo, paleta visual, voz de marca y manual de identidad. Base de toda la comunicación de La Falla.',
    logros:['Sistema de identidad visual completo: logo, paleta, tipografía y tono','Manual de marca entregado a todas las áreas y aliados','Voz de marca definida y aplicada en todas las comunicaciones','Reconocimiento de marca validado por MinCultura y ACMI'],
    leccion:'El proceso tomó 3 meses de iteración — involucrar al equipo completo desde la primera sesión redujo el retrabajo a cero.',
  },
  'Plataforma digital': {
    cuando:'Q2 2024', descripcion:'Sitio web lafalla.co, perfiles de redes sociales y presencia digital unificada.',
    logros:['lafalla.co publicado y operativo con analíticas (GA4)','Presencia unificada en Instagram, LinkedIn y YouTube','Centro de Mando desplegado en VPS propio (este dashboard)','Infraestructura digital autónoma: no dependemos de terceros para operar'],
    leccion:'Optar por VPS self-hosted desde el inicio nos dio flexibilidad total para el Centro de Mando. En SaaS esto habría costado 3× y sin control.',
  },
  'Red de aliados 1': {
    cuando:'Q3 2024', descripcion:'Acuerdos con FDC, MinCultura y ACMI. Red inicial de alianzas estratégicas.',
    logros:['Acuerdo marco con FDC firmado y activo','Carta de intención con MinCultura (en renovación jun 2026)','Primer contacto formal con ACMI — derivó en la Cumbre 2026','8 aliados activos en el directorio de stakeholders'],
    leccion:'La relación con ACMI empezó como una exploración de contacto — convertirla en la Cumbre 2026 fue el mayor salto estratégico de este hito.',
  },
  'Piloto Eje': {
    cuando:'Q4 2024', descripcion:'Primer piloto audiovisual en el Eje Cafetero. Validación del modelo de producción territorial.',
    logros:['Piloto «Eje» completado: 5 días de rodaje, material editado','Modelo de producción territorial validado y documentado','Relaciones con comunidades del Eje establecidas para proyectos futuros','Material de muestra que abrió convocatorias 2025 con FDC'],
    leccion:'El piloto mostró que los rodajes en territorio rural necesitan el doble de tiempo logístico. Eso cambió cómo planificamos Rutas Cafeteras.',
  },
  'Alianzas ministerio': {
    cuando:'Q1 2025', descripcion:'Convenio firmado con MinCultura y RTVC. Respaldo institucional para expansión.',
    logros:['Convenio marco con MinCultura activo','Relación con RTVC establecida para distribución de contenido','Acceso a convocatorias cerradas de financiamiento público','Credencial institucional que abre puertas a cooperación internacional'],
    leccion:'El proceso de firma tomó 5 meses. Para la renovación en junio iniciamos gestión con 4 meses de anticipación — nunca más esperar el último mes.',
  },
  'Modelo financiero': {
    cuando:'Q1 2025', descripcion:'Plan financiero 2025-2030 validado por directivos. Proyecciones y fuentes de ingreso definidas.',
    logros:['Proyecciones 2025-2030 validadas y usadas como referencia en convocatorias','Mix de ingresos definido: 60% institucional · 30% comercial · 10% fondos','Política de reservas estratégicas aprobada y respetada','9+ meses de respiración mantenidos consistentemente'],
    leccion:'Separar reservas estratégicas de caja operativa fue la mejor decisión financiera — nos protegió durante el trimestre de menor captación sin tocar el plan.',
  },
  'Equipo base': {
    cuando:'Q2 2025', descripcion:'4 directoras + 2 externos clave contratados. Estructura organizacional operativa.',
    logros:['4 gerencias activas: Comercial, Proyectos, Investigación, Audiovisual','Quinaya lidera finanzas con seguimiento semanal en Google Sheets','Manuales de funciones por cargo elaborados y distribuidos','Estructura lista para escalar a 8+ personas en 2027'],
    leccion:'Definir los manuales de funciones antes de contratar fue clave — redujo ambigüedades y conflictos de rol en los primeros 6 meses.',
  },
  'Gobierno de datos': {
    cuando:'Q3 2025', descripcion:'PostgreSQL + n8n + OpenClaw/Gentil activos. Infraestructura de datos consolidada.',
    logros:['PostgreSQL con 18 tablas operativas y 554 contactos en stakeholders_master','n8n con 5 workflows activos (GM-01 a GM-04)','Gentil/OpenClaw conectado a todos los endpoints del Centro de Mando vía MCP','Este dashboard: datos en vivo, sin actualizaciones manuales'],
    leccion:'Unificar todo en un solo VPS con EasyPanel redujo el overhead operativo. Self-hosted vs SaaS nos ahorra ~$200/mes y nos da trazabilidad total.',
  },
  'Narrativa pública': {
    cuando:'Q1 2026', descripcion:'Marca posicionada en medios especializados y redes. Narrativa coherente con la visión 2030.',
    logros:['Posicionamiento como agencia de investigación audiovisual territorial','184K de alcance en 30 días (GA, datos en vivo)','Narrativa «investigación que se convierte en historia» validada por aliados','Presencia en Eje, Risaralda y exploración del Caribe'],
    leccion:'La narrativa que resonó fue más potente que «productora audiovisual» — el componente de investigación diferencia a La Falla de la competencia.',
  },
  'Cumbre ACMI (en curso)': {
    cuando:'Jun 2026', descripcion:'Evento audiovisual nacional posicionado para 2026. Guion en revisión, producción al 34% presupuestado. Hito crítico para el posicionamiento.',
    hecho:['Programa del evento confirmado y publicado','12 de 15 invitados nacionales confirmados','Propuesta enviada a invitados internacionales (gestión activa)','22M COP ejecutados sobre 65M presupuestados (34%)'],
    faltante:['Confirmación de al menos 2 invitados internacionales','Producción integral del evento: logística + audiovisual','Cobertura en vivo y post-producción del registro del evento','Cierre contractual con 3 proveedores pendientes de firma'],
    proximo_paso:'Confirmar mínimo 2 invitados internacionales antes del 15 de mayo — sin esto el programa no puede publicarse completo y la credibilidad del evento se ve afectada.',
  },
  'Laboratorio Risaralda': {
    cuando:'Jul 2026', descripcion:'Laboratorio permanente de investigación territorial en Risaralda. Retrasado 6 días — requiere intervención del Gerente General esta semana.',
    problemas:['Talleres comunitarios al 67%: 4 de 6 completados — retrasos logísticos en campo','Documento de síntesis sin iniciar: esperando cierre de talleres para arrancar','6 días de retraso acumulado sobre cronograma original','Bloquea parcialmente el material de referencia para la Cumbre ACMI'],
    mejora:'Debimos haber bloqueado las fechas de campo con 8 semanas de anticipación, no 3. La logística rural no perdona la planeación tardía — este es un patrón que no puede repetirse en Caribe.',
    plan_recuperacion:['Agendar talleres 5 y 6 para la semana del 12-16 de mayo (no negociable, cerrar hoy)','Iniciar síntesis parcial con los 4 talleres ya completados, no esperar al cierre','Reunión 1:1 con líder de proyectos antes del jueves de esta semana','Evaluar si el material parcial es suficiente para presentar avance en Cumbre ACMI'],
  },
  'Memoria 2025': {
    cuando:'May 2026', descripcion:'Publicación anual de procesos e impacto de La Falla. Retrasada 2 semanas — el contenido existe en GI, falta el proceso editorial.',
    problemas:['2 semanas de retraso sobre la fecha de publicación planificada','Síntesis editorial sin iniciar: equipo GI concentrado en trabajo de campo','Riesgo de que la Memoria no esté lista como material de posicionamiento para la Cumbre ACMI'],
    mejora:'La Memoria debió arrancar en paralelo con el trabajo de campo, no después de cerrarlo. El contenido de los 23 documentos de GI ya existe — era solo cuestión de asignar el recurso editorial a tiempo.',
    plan_recuperacion:['Solicitar a Gentil que genere un primer borrador desde los 23 documentos activos de GI (hoy mismo)','Asignar 1 persona de GI exclusivamente a edición por 5 días esta semana','Publicar versión digital antes del 20 de mayo (meta dura)','Tener versión impresa lista para la Cumbre ACMI en junio como material de sala'],
  },
  'Red de aliados 2': {
    cuando:'Q3 2026', descripcion:'Segunda red de alianzas: fondos privados, cooperación internacional y circuitos regionales. Pendiente de arranque.',
    requisitos:['Cumbre ACMI completada — genera contactos internacionales y credencial de convocatoria','Laboratorio Risaralda finalizado — valida la metodología territorial que se va a replicar','Memoria 2025 publicada — respaldo institucional ante nuevos aliados','Captación Q2 (620M) alcanzada — demuestra viabilidad financiera a aliados privados'],
    pasos:['Mapear fondos privados y cooperación internacional elegibles (post-Cumbre, agosto)','Diseñar propuesta de valor diferenciada por tipo de aliado: fondos, academia, sector privado','Lanzar campaña de alianzas en agosto-septiembre 2026 con Memoria como soporte','Cerrar 3 acuerdos formales antes de diciembre 2026'],
  },
  'Circuito Audiovisual': {
    cuando:'Q1 2027', descripcion:'Circuito propio de festivales y distribución de contenido audiovisual de La Falla. Pendiente.',
    requisitos:['Cumbre ACMI posicionada como referente — es la credencial del circuito','Laboratorio Risaralda activo generando contenido territorial de alta calidad','Al menos 5 piezas audiovisuales terminadas y listas para circular','Alianza con distribuidor nacional o plataforma de streaming para llegar al público'],
    pasos:['Definir curatoría: qué tipo de contenido circula y con qué criterio editorial','Mapear festivales nacionales e internacionales elegibles para el primer año','Diseñar el modelo económico del circuito (cobro por proyección / co-producción / patrocinio)','Lanzar primera edición en Q1 2027 con al menos 4 ciudades ancla'],
  },
  'Territorio Caribe': {
    cuando:'Q2 2027', descripcion:'Expansión territorial al norte del país: Barranquilla, Cartagena y Santa Marta. Exploración activa desde GI.',
    requisitos:['Red de aliados 2 activa con al menos 1 contacto ancla en la región','Metodología territorial validada y documentada desde Risaralda','Circuito audiovisual con presencia confirmada en el Caribe','Financiamiento asegurado para operación de 3 meses en nuevo territorio'],
    pasos:['Completar la exploración de GI: convertir contactos abiertos en aliados formales','Identificar aliado ancla en la región: academia, institución cultural o colectivo local','Diseñar plan de entrada: piloto de 3 meses en una ciudad antes de escalar','Lanzar presencia en 3 ciudades del Caribe en Q3 2027 con equipo local coordinado'],
  },
  'Escalado nacional': {
    cuando:'2028-2030', descripcion:'Presencia consolidada en 5+ ciudades colombianas. Objetivo final de la visión 2030.',
    requisitos:['Territorio Caribe operativo con al menos 1 producción completada','Circuito audiovisual con 2 ediciones anuales exitosas','Modelo financiero diversificado y autosostenible sin depender de una sola fuente','Equipo de 12+ personas con liderazgos regionales autónomos'],
    pasos:['Seleccionar las 5 ciudades ancla basadas en los datos acumulados de GI','Estructurar alianzas regionales en cada ciudad: academia + sector público + privado','Contratar coordinadores territoriales con raíz cultural en cada región','Posicionar a La Falla D.F. como el referente nacional de investigación audiovisual','Alcanzar autosostenibilidad en todas las sedes para cierre de 2030'],
  },
};
const SEG_STATE = { done:'✓ Completo', prog:'◐ En curso', late:'⚠ Retrasado', '':'○ Pendiente' };
const SEG_COLOR = { done:'#00FF41', prog:'var(--ink-3)', late:'#e89c2b', '':'var(--mute)' };

function MilestoneModal({ seg, onClose }){
  useEffect(()=>{
    if(!seg) return;
    const h = e=>{ if(e.key==='Escape') onClose(); };
    document.addEventListener('keydown', h);
    return ()=>document.removeEventListener('keydown', h);
  },[seg]);
  if(!seg) return null;
  const det = SEG_DETAIL[seg.t] || {};
  const color = SEG_COLOR[seg.s] || 'var(--mute)';
  const stLabel = SEG_STATE[seg.s] || '○ Pendiente';
  return (
    <div className="hito-scrim" onClick={onClose}>
      <div className="hito-box" onClick={e=>e.stopPropagation()}>
        <div className="hito-hd">
          <div style={{flex:1}}>
            <div className="hito-eye" style={{color}}>{stLabel} · {det.cuando||'—'}</div>
            <h3 className="hito-title">{seg.t}</h3>
            <p className="hito-desc">{det.descripcion}</p>
          </div>
          <button className="hito-close" onClick={onClose}>×</button>
        </div>
        <div className="hito-body">
          {seg.s==='done' && (<>
            <div className="hito-section">
              <div className="hito-section-lbl">✓ Logros de este hito</div>
              <ul className="hito-list hito-list-ok">
                {(det.logros||[]).map((l,i)=><li key={i}>{l}</li>)}
              </ul>
            </div>
            {det.leccion && (
              <div className="hito-section hito-insight">
                <div className="hito-section-lbl">💡 Lección aprendida</div>
                <p className="hito-text">{det.leccion}</p>
              </div>
            )}
          </>)}
          {seg.s==='prog' && (<>
            <div className="hito-cols">
              <div className="hito-section">
                <div className="hito-section-lbl">✓ Lo que hemos hecho</div>
                <ul className="hito-list hito-list-ok">
                  {(det.hecho||[]).map((l,i)=><li key={i}>{l}</li>)}
                </ul>
              </div>
              <div className="hito-section">
                <div className="hito-section-lbl">◻ Lo que falta</div>
                <ul className="hito-list hito-list-pen">
                  {(det.faltante||[]).map((l,i)=><li key={i}>{l}</li>)}
                </ul>
              </div>
            </div>
            {det.proximo_paso && (
              <div className="hito-section hito-insight">
                <div className="hito-section-lbl">→ Próximo paso crítico</div>
                <p className="hito-text">{det.proximo_paso}</p>
              </div>
            )}
          </>)}
          {seg.s==='late' && (<>
            <div className="hito-section">
              <div className="hito-section-lbl">⚠ ¿Qué ha pasado?</div>
              <ul className="hito-list hito-list-late">
                {(det.problemas||[]).map((l,i)=><li key={i}>{l}</li>)}
              </ul>
            </div>
            {det.mejora && (
              <div className="hito-section hito-insight hito-insight-warn">
                <div className="hito-section-lbl">🔍 ¿Qué podríamos haber hecho mejor?</div>
                <p className="hito-text">{det.mejora}</p>
              </div>
            )}
            <div className="hito-section">
              <div className="hito-section-lbl">→ Plan para ponerlo en verde</div>
              <ul className="hito-list hito-list-plan">
                {(det.plan_recuperacion||[]).map((l,i)=><li key={i}>{l}</li>)}
              </ul>
            </div>
          </>)}
          {seg.s==='' && (
            <div className="hito-cols">
              <div className="hito-section">
                <div className="hito-section-lbl">🔒 Requisitos para arrancar</div>
                <ul className="hito-list hito-list-pen">
                  {(det.requisitos||[]).map((l,i)=><li key={i}>{l}</li>)}
                </ul>
              </div>
              <div className="hito-section">
                <div className="hito-section-lbl">🎯 Pasos para el 100%</div>
                <ul className="hito-list hito-list-plan">
                  {(det.pasos||[]).map((l,i)=><li key={i}>{l}</li>)}
                </ul>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Execution(){
  const apiMilestones = useApiData('milestones');
  const segs = (apiMilestones && apiMilestones.length) ? apiMilestones : SEGS_FALLBACK;
  const doneCount = segs.filter(s=>s.s==='done').length;
  const [selIdx, setSelIdx] = useState(null);
  const selSeg = selIdx !== null ? segs[selIdx] : null;

  return (
    <div className="panel">
      <div className="panel-hd">
        <h3>Ejecución hacia <em>2030</em></h3>
        <span className="hint">{segs.length} SEGMENTOS · {doneCount} COMPLETOS</span>
      </div>
      <div className="exec-grid">
        {segs.map((s,i)=>(
          <div key={i} className={'exec-seg ' + s.s}
               onClick={()=>setSelIdx(i)}>
            <span className="tt">{s.t}</span>
          </div>
        ))}
      </div>
      <div className="exec-legend">
        <span className="l"><span className="sq" style={{background:'var(--falla)'}}/>Completo</span>
        <span className="l"><span className="sq" style={{background:'var(--ink-3)'}}/>En curso</span>
        <span className="l"><span className="sq" style={{background:'var(--warn)'}}/>Retrasado</span>
        <span className="l"><span className="sq" style={{background:'var(--line)'}}/>Pendiente · clic para detalle</span>
      </div>
      <MilestoneModal seg={selSeg} onClose={()=>setSelIdx(null)}/>
    </div>
  );
}

const PINS_FALLBACK = [
  { x:3, y:3, c:'high', t:'Rutas Cafeteras 02 · sobrecosto',
    gentil_analysis:'El sobrecosto de +7% en Rutas Cafeteras 02 posiciona este riesgo en Nr=16 (nivel máximo). El gasto ya está ocurriendo durante el rodaje activo del episodio 2 — el margen de corrección es mínimo. Si el patrón continúa, el proyecto proyecta un déficit de ~12M COP al cierre, impactando directamente la liquidez de Q3. No es una amenaza futura: es un hecho en curso que requiere intervención esta semana.',
    origen:'openclaw_auto', detectado_por:'Gentil · cruce sobrecosto ejecutado vs. presupuesto aprobado', fecha_deteccion:'2026-05-02',
    plan_mitigacion:['Auditoría de gastos con director de proyectos esta semana','Revisar contratos de post-producción — explorar renegociación o reducción de scope','Evaluar si el episodio 2 puede absorber el diferencial reduciendo días de rodaje','Activar reserva estratégica si el déficit supera 15M COP'],
    estado_mitigacion:'en_mitigacion' },
  { x:2, y:2, c:'med', t:'MinCultura · silencio 24d',
    gentil_analysis:'La ausencia de respuesta de MinCultura durante 24 días es un riesgo moderado (Nr=9). La renovación del convenio está programada para junio 15 — si no hay contacto en los próximos 7 días, el proceso administrativo no tendrá tiempo suficiente para firmar antes de esa fecha. El impacto es alto en acceso a convocatorias cerradas y en la credibilidad institucional ante aliados internacionales. La probabilidad es media: el silencio puede ser burocrático, no negativo.',
    origen:'openclaw_auto', detectado_por:'Gentil · monitoreo de SLA de comunicaciones institucionales', fecha_deteccion:'2026-04-28',
    plan_mitigacion:['Llamada directa al enlace de MinCultura esta semana — no email, no formulario','Enviar resumen de logros 2025 como recordatorio de valor de la alianza','Si no hay respuesta en 5 días, escalar al director de área del ministerio'],
    estado_mitigacion:'monitoreado' },
  { x:1, y:3, c:'med', t:'Rotación equipo AV',
    gentil_analysis:'La rotación en el equipo audiovisual es un riesgo de impacto alto pero probabilidad baja (Nr=8). El director audiovisual coordina 3 proyectos simultáneos: Rutas Cafeteras, Piloto Eje y Reel Abril, con un solo colaborador externo de apoyo. Si ocurre una salida inesperada, la cobertura audiovisual de la Cumbre ACMI quedaría sin responsable. El riesgo es estructural, no de persona — la carga es la amenaza.',
    origen:'ceo_manual', detectado_por:'Gerente General · evaluación de carga operativa del área', fecha_deteccion:'2026-04-30',
    plan_mitigacion:['Mapear 1 colaborador audiovisual adicional como respaldo para la Cumbre ACMI','Documentar los flujos de trabajo del área AV para que no dependan de una sola persona','Conversación 1:1 con director audiovisual sobre su carga y nivel de satisfacción'],
    estado_mitigacion:'monitoreado' },
  { x:1, y:1, c:'low', t:'Ajuste cronograma lab.',
    gentil_analysis:'El ajuste en el cronograma del laboratorio es un riesgo bajo como evento aislado (Nr=4), dado que ya hay un plan de recuperación activo. La preocupación real es si este retraso se acumula con el de Memoria 2025 — en ese escenario el impacto sube. Por ahora lo clasifico como bajo porque el equipo tiene pasos concretos y la ventana de corrección es suficiente si se actúa esta semana.',
    origen:'openclaw_auto', detectado_por:'Gentil · detección de tareas vencidas en GP · Laboratorio Risaralda', fecha_deteccion:'2026-05-01',
    plan_mitigacion:['Confirmar agenda de talleres 5 y 6 antes del lunes','Si no hay agenda confirmada en 48h, escalar este riesgo a nivel medio'],
    estado_mitigacion:'monitoreado' },
  { x:3, y:1, c:'low', t:'Memoria 2025 · tiempos',
    gentil_analysis:'El retraso de la Memoria 2025 tiene impacto bajo como riesgo individual (Nr=4), pero actúa como multiplicador: si la Memoria no está lista antes de la Cumbre ACMI, se pierde un material clave de posicionamiento institucional. La probabilidad de impacto es alta porque el retraso ya existe — la coloco en bajo porque Gentil puede generar el primer borrador en minutos desde los 23 documentos activos de GI, reduciendo el riesgo operativo a cero si se actúa hoy.',
    origen:'openclaw_auto', detectado_por:'Gentil · cruce de fecha planificada vs. progreso real en GI', fecha_deteccion:'2026-05-03',
    plan_mitigacion:['Solicitar a Gentil borrador de Memoria desde documentos GI (hoy, sin esperar)','Asignar editor de GI por 5 días exclusivos para el cierre editorial','Publicar versión digital antes del 20 de mayo'],
    estado_mitigacion:'monitoreado' },
];

function RiskModal({ pin, onClose }){
  const [ceoNota, setCeoNota] = useState('');
  const [editando, setEditando] = useState(false);
  const [borrador, setBorrador] = useState('');

  useEffect(()=>{
    if(!pin) return;
    const saved = (() => { try{ return localStorage.getItem('risk_ceo_'+pin.t)||''; }catch{ return ''; } })();
    setCeoNota(saved);
    setEditando(false);
    const h = e=>{ if(e.key==='Escape') onClose(); };
    document.addEventListener('keydown', h);
    return ()=>document.removeEventListener('keydown', h);
  },[pin]);

  if(!pin) return null;

  const NR_LABEL = { high:'⚠ CRÍTICO', med:'◈ MODERADO', low:'● BAJO' };
  const NR_COLOR = { high:'#cc3333', med:'#e89c2b', low:'#00C433' };
  const ORIGEN_LABEL = { openclaw_auto:'Gentil · detección automática', ceo_manual:'Gerente General · ingreso manual', director_area:'Director de Área · reporte' };
  const ESTADO_LABEL = { en_mitigacion:'◈ En mitigación', critico:'⚠ Crítico sin mitigar', monitoreado:'● Monitoreado' };

  const color = NR_COLOR[pin.c]||'#aaa';
  const nr = (pin.x+1)*(pin.y+1);

  const guardar = ()=>{
    try{ localStorage.setItem('risk_ceo_'+pin.t, borrador); }catch{}
    setCeoNota(borrador);
    setEditando(false);
  };

  return (
    <div className="risk-modal-scrim" onClick={onClose}>
      <div className="risk-modal-box" onClick={e=>e.stopPropagation()}>
        <div className="risk-modal-hd">
          <div style={{flex:1}}>
            <div className="risk-modal-badge" style={{color, borderColor:color+'55'}}>
              {NR_LABEL[pin.c]}
              <span className="risk-nr-formula">P{pin.x+1} × I{pin.y+1} = Nr {nr}</span>
            </div>
            <h3 className="risk-modal-title">{pin.t}</h3>
            <div className="risk-modal-origin">
              {ORIGEN_LABEL[pin.origen]||pin.detectado_por||'No especificado'}
              {pin.fecha_deteccion && <span className="risk-origin-date"> · {pin.fecha_deteccion}</span>}
            </div>
          </div>
          <button className="hito-close" onClick={onClose}>×</button>
        </div>

        <div className="risk-modal-body">
          <div className="risk-modal-section risk-gentil-section">
            <div className="risk-section-lbl">
              <span className="risk-gentil-badge">GENTIL</span> Análisis y justificación
            </div>
            <p className="risk-modal-text">{pin.gentil_analysis||'Análisis pendiente — Gentil lo generará en el próximo Heartbeat Matutino.'}</p>
            {(pin.plan_mitigacion||[]).length > 0 && (
              <div className="risk-mitigation">
                <div className="risk-section-sub">Plan de mitigación</div>
                <ul className="hito-list hito-list-plan">
                  {pin.plan_mitigacion.map((p,i)=><li key={i}>{p}</li>)}
                </ul>
              </div>
            )}
          </div>

          <div className="risk-modal-section risk-ceo-section">
            <div className="risk-section-lbl">
              <span className="risk-ceo-badge">GG</span> Tu perspectiva, Clementino
            </div>
            {!editando ? (<>
              {ceoNota
                ? <p className="risk-modal-text risk-ceo-saved">{ceoNota}</p>
                : <p className="risk-placeholder">¿Coincides con Gentil? ¿Ves algo diferente? Tu contexto enriquece el análisis.</p>
              }
              <button className="risk-edit-btn" onClick={()=>{ setBorrador(ceoNota); setEditando(true); }}>
                {ceoNota ? '✎ Editar perspectiva' : '+ Agregar perspectiva'}
              </button>
            </>) : (<>
              <textarea className="risk-ceo-ta" value={borrador}
                onChange={e=>setBorrador(e.target.value)}
                placeholder="Escribe tu análisis, acuerdo o desacuerdo con Gentil..."
                autoFocus rows={4}/>
              <div className="risk-ceo-actions">
                <button className="risk-save-btn" onClick={guardar}>Guardar</button>
                <button className="risk-cancel-btn" onClick={()=>setEditando(false)}>Cancelar</button>
              </div>
            </>)}
          </div>
        </div>

        <div className="risk-modal-ft">
          <span className={'risk-estado risk-estado-'+(pin.estado_mitigacion||'monitoreado')}>
            {ESTADO_LABEL[pin.estado_mitigacion]||'● Monitoreado'}
          </span>
          <span className="risk-ft-hint">Arrastra el punto en el mapa para reposicionar</span>
        </div>
      </div>
    </div>
  );
}

function RiskMap(){
  const apiRisks = useApiData('risks');
  const initPins = (apiRisks && apiRisks.length) ? apiRisks : PINS_FALLBACK;
  const [pins, setPins] = useState(initPins);
  const [selPin, setSelPin] = useState(null);
  const [dragging, setDragging] = useState(null);

  const NR_COLOR = { high:'#cc3333', med:'#e89c2b', low:'#00C433' };

  const handleDragStart = (e, pin) => {
    setDragging(pin);
    e.dataTransfer.effectAllowed = 'move';
  };
  const handleDrop = (e, cx, cy) => {
    e.preventDefault();
    if(!dragging) return;
    setPins(prev => prev.map(p => p.t===dragging.t ? {...p, x:cx, y:cy} : p));
    setDragging(null);
  };

  return (
    <div className="panel">
      <div className="panel-hd">
        <h3>Mapa de <em>riesgos</em></h3>
        <span className="hint">IMPACTO × PROBABILIDAD · Arrastra para mover · Clic para análisis</span>
      </div>
      <div className="risk-map">
        <div className="y-axis">IMPACTO →</div>
        <div className="cells">
          {Array.from({length:16}).map((_,i)=>{
            const cx = i%4, cy = 3-Math.floor(i/4);
            const pin = pins.find(p=>p.x===cx && p.y===cy);
            return (
              <div key={i} className="risk-cell"
                   onDragOver={e=>{e.preventDefault(); e.dataTransfer.dropEffect='move';}}
                   onDrop={e=>handleDrop(e,cx,cy)}>
                {pin && (
                  <span
                    className={'pin '+pin.c}
                    style={{cursor:'grab'}}
                    draggable
                    onDragStart={e=>handleDragStart(e,pin)}
                    onClick={e=>{ e.stopPropagation(); setSelPin(pin); }}
                    title={pin.t}
                  />
                )}
              </div>
            );
          })}
        </div>
        <div className="x-axis">PROBABILIDAD →</div>
      </div>
      <RiskModal pin={selPin} onClose={()=>setSelPin(null)}/>
    </div>
  );
}

/* ============================================================
   BRANCH RAIL (columna derecha — nodos interactivos)
   ============================================================ */
const BRANCHES = [
  { id:'gcf', code:'GCF', t:'Dirección Comercial', sub:'Comercial & Financiera', icon:I.coin,
    kpi:{ label:'Recaudación vs. Meta', value:'68%', target:'Meta Q2 · 620M COP', tone:'up' },
    metrics:[
      ['Recaudación YTD','420M','up'],
      ['Meta Q2','620M',''],
      ['Cobros 30d','42M','up'],
      ['Alianzas activas','8',''],
    ],
    todos:[['ok','Cierre abril','reporte enviado',5],['w','Pitch FDC','presencial jueves',2],['c','Cartera +60d','2 clientes · $18M',0],['','Renovación MinCultura','jun 15',14]],
    services:[
      { name:'Hostinger VPS',    status:'ok',  kind:'paid', note:'plan anual' },
      { name:'Chatwoot',         status:'ok',  kind:'infra' },
      { name:'YCloud (WhatsApp)',status:'ok',  kind:'paid' },
      { name:'Google Workspace', status:'ok',  kind:'ngo' },
      { name:'n8n',              status:'ok',  kind:'infra' },
    ]
  },
  { id:'gp', code:'GP', t:'Dirección de Proyectos', sub:'Ejecución & Entregas', icon:I.clap,
    kpi:{ label:'Índice de Ejecución', value:'78%', target:'On-time ratio · 7 proyectos activos', tone:'' },
    metrics:[
      ['Índice ejecución','78%',''],
      ['Entregables 7d','7/9','up'],
      ['Proyectos activos','7',''],
      ['Sobrecosto medio','+4%','dn'],
    ],
    todos:[['c','Rutas Cafeteras 02','sobrecosto +7%',-3],['ok','Piloto «Eje»','día 3 de 5',4],['w','Laboratorio Risaralda','retraso 6d',-6],['','Cumbre ACMI','guion en revisión',1]],
    services:[
      { name:'Hostinger VPS',        status:'ok',  kind:'paid', note:'plan anual' },
      { name:'EasyPanel',            status:'ok',  kind:'paid' },
      { name:'n8n',                  status:'ok',  kind:'infra' },
      { name:'api-gerencia (FastAPI)',status:'ok',  kind:'infra' },
      { name:'PostgreSQL',           status:'ok',  kind:'infra' },
    ]
  },
  { id:'gi', code:'GI', t:'Dirección de Investigación', sub:'Conocimiento & Territorio', icon:I.map,
    kpi:{ label:'Producción de Contenido', value:'23', target:'Documentos activos · 2 publicados Q2', tone:'up' },
    metrics:[
      ['Documentos activos','23','up'],
      ['Publicaciones Q2','2','up'],
      ['Territorios mapeados','4',''],
      ['Síntesis pendientes','3',''],
    ],
    todos:[['ok','Eje · campo completo','listo para síntesis',7],['','Caribe · exploratorio','contactos abiertos',5],['w','Memoria 2025','atrasada 2 sem',-14],['ok','Drive auditado','Gentil confirma',10]],
    services:[
      { name:'Hostinger VPS',  status:'ok',   kind:'paid', note:'plan anual' },
      { name:'Perplexity API', status:'ok',   kind:'paid' },
      { name:'OpenAI API',     status:'ok',   kind:'paid' },
      { name:'Airtable',       status:'ok',   kind:'paid' },
      { name:'Firecrawl',      status:'down', kind:'paid', note:'pausado · presupuesto' },
      { name:'n8n',            status:'ok',   kind:'infra' },
    ]
  },
  { id:'ga', code:'GA', t:'Dirección Audiovisual', sub:'Producción & Narrativa', icon:I.cam,
    kpi:{ label:'Eficiencia de Producción', value:'6.2%', target:'Engagement · 12 piezas Q2', tone:'up' },
    metrics:[
      ['Eficiencia (eng.)','6.2%','up'],
      ['Piezas Q2','12',''],
      ['Alcance 30d','184K','up'],
      ['Pauta activa','3M',''],
    ],
    todos:[['w','Guion ACMI','pendiente tu visto',0],['ok','Reel abril','publicado',8],['','Rodaje Piloto','día 3 de 5',3],['','Rebrand aliados','bocetos vie.',2]],
    services:[
      { name:'Hostinger VPS',       status:'ok',      kind:'paid', note:'plan anual' },
      { name:'Meta Ads (pauta)',     status:'unknown', kind:'paid' },
      { name:'YouTube Studio',       status:'ok',      kind:'ngo' },
      { name:'Adobe Creative Cloud', status:'unknown', kind:'paid' },
      { name:'Google Workspace',     status:'ok',      kind:'ngo' },
    ]
  },
];

function branchStatus(b){
  const s = b.services || [];
  if(!s.length) return 'unknown';
  if(s.some(x=>x.status==='down'))    return 'down';
  if(s.some(x=>x.status==='warn'))    return 'warn';
  if(s.some(x=>x.status==='unknown')) return 'unknown';
  return 'ok';
}

const SVC_STATUS_LABEL = { ok:'Servicios activos', warn:'Atención requerida', down:'Servicio caído', unknown:'Estado desconocido' };

function BranchRail({ active, onPick }){
  const execFeed = useApiData('executive_feed');
  const focoTitle   = execFeed?.foco_semana || 'Cierre contrato Risaralda Film';
  const focoArea    = execFeed?.hitos_activos?.[0]?.area || 'Comercial';
  const hito        = execFeed?.proximo_hito_critico;
  const hitoTitle   = hito?.titulo || 'Entrega rough cut · Manizales Doc';
  const hitoPct     = hito?.pct_completado ?? 72;
  const hitoArea    = hito?.area || 'Audiovisual';
  const riesgo      = execFeed?.riesgo_abierto;
  const riesgoTitle = riesgo?.titulo || 'Retraso proveedor post-producción';
  const riesgoNivel = riesgo?.nivel  || 'Alto impacto';
  const riesgoEst   = riesgo?.estado || 'En gestión';
  const hitoChip    = hitoArea === 'Audiovisual' ? 'rex-chip-audio' : 'rex-chip-ok';
  const [openSvc, setOpenSvc] = useState(null);

  useEffect(()=>{
    if(!openSvc) return;
    const h = ()=>setOpenSvc(null);
    document.addEventListener('click', h);
    return ()=>document.removeEventListener('click', h);
  },[openSvc]);

  return (
    <aside className="rail">
      <div className="rail-hd">
        Direcciones
        <strong>Cuatro ramas</strong>
      </div>
      {BRANCHES.map(b => {
        const st = branchStatus(b);
        return (
          <div key={b.id} style={{position:'relative'}}>
            <button className={'branch ' + (active===b.id?'on':'')} onClick={()=>{setOpenSvc(null); onPick(b.id);}}>
              <span className="icon">{b.icon}</span>
              <span className="lbl">
                <span className="code">{b.code}</span>
                <span className="t">{b.t}</span>
                <span className="sub">{b.sub}</span>
              </span>
              <span
                className={'branch-svc-dot d-'+st}
                title={SVC_STATUS_LABEL[st]}
                onClick={(e)=>{ e.stopPropagation(); setOpenSvc(openSvc===b.id?null:b.id); }}
              />
              <span className="chev">›</span>
            </button>
            {openSvc===b.id && (
              <div className="branch-svc-popup" onClick={e=>e.stopPropagation()}>
                <div className="branch-svc-hd">SERVICIOS · {b.code}</div>
                {(b.services||[]).map((s,i)=>(
                  <div key={i} className="branch-svc-row">
                    <span className={'branch-svc-dot d-'+s.status}/>
                    <span className="branch-svc-name">{s.name}</span>
                    {s.note && <span className="branch-svc-note">{s.note}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}

      {/* Tablero ejecutivo — información de valor que ancla el rail */}
      <div className="rail-exec">
        <div className="rex-eye"><span className="gentil-brand-name">Gentil</span> · lectura ejecutiva</div>

        <div className="rex-block rex-focus">
          <div className="rex-lbl">Foco · Esta semana</div>
          <div className="rex-title">{focoTitle}</div>
          <div className="rex-meta">
            <span className="rex-chip rex-chip-ok">{focoArea}</span>
            <span className="rex-pr">Prioridad <strong>01 / 03</strong></span>
          </div>
        </div>

        <div className="rex-block rex-milestone">
          <div className="rex-lbl">Próximo hito · crítico</div>
          <div className="rex-title">{hitoTitle}</div>
          <div className="rex-bar">
            <div className="rex-bar-fill" style={{width: Math.round(hitoPct) + '%'}}/>
          </div>
          <div className="rex-meta">
            <span className={'rex-chip ' + hitoChip}>{hitoArea}</span>
            <span className="rex-pr"><strong>{Math.round(hitoPct)}%</strong> ejecutado</span>
          </div>
        </div>

        <div className="rex-block rex-risk">
          <div className="rex-lbl"><span className="rex-pulse"/> Riesgo abierto · 1</div>
          <div className="rex-title">{riesgoTitle}</div>
          <div className="rex-meta">
            <span className="rex-chip rex-chip-risk">{riesgoNivel}</span>
            <span className="rex-pr">{riesgoEst}</span>
          </div>
        </div>

        <button className="rex-foot" onClick={()=>window.__openProjects && window.__openProjects()}>
          <span>Dashboard de Proyectos</span>
          <span className="rex-arr">→</span>
        </button>
      </div>
    </aside>
  );
}

/* ============================================================
   DEPLOY (overlay en el central cuando se elige un área)
   ============================================================ */
function Deploy({ branchId, onClose }){
  const b = BRANCHES.find(x => x.id===branchId);
  if(!b) return null;
  const areaData = useAreaData(branchId);

  /* Pendientes: API si hay datos, fallback a constante BRANCHES */
  const SLA_DOT = { green:'ok', yellow:'w', red:'c', skull:'c' };
  const todos = areaData?.pendientes?.length
    ? areaData.pendientes.map(p => [SLA_DOT[p.sla_color]||'', p.titulo, p.responsable||p.estado||'', p.dias??99])
    : b.todos;

  /* KPI: API si disponible, fallback a constante */
  const kpiLabel  = areaData?.kpi_principal?.label  || b.kpi.label;
  const kpiTarget = areaData?.kpi_principal?.period
    ? `${areaData.kpi_principal.period}${areaData.kpi_principal.target ? ' · Meta: ' + Number(areaData.kpi_principal.target).toLocaleString('es-CO') : ''}`
    : b.kpi.target;

  return (
    <div className="deploy">
      <div className="deploy-head">
        <div>
          <div className="eye">ÁREA · {b.code}</div>
          <h2>{b.t} <em>· {b.sub}</em></h2>
        </div>
        <button className="deploy-close" onClick={onClose}>{I.x}</button>
      </div>

      <div className="branch-hero">
        <div className="bh-eye">KPI OPERATIVO CLAVE · PLACEHOLDER · EDITABLE POR GERENTE GENERAL</div>
        <div className="bh-row">
          <div className="bh-val num-mono">{b.kpi.value}</div>
          <div className="bh-lbl">
            <strong>{kpiLabel}</strong>
            <span>{kpiTarget}</span>
          </div>
        </div>
      </div>

      <div className="deploy-grid">
        <div className="deploy-block">
          <h4>Indicadores <span className="tiny">ÚLTIMOS 30 DÍAS</span></h4>
          {b.metrics.map((m,i)=>(
            <div key={i} className="metric-row">
              <span className="k">{m[0]}</span>
              <span className={'v ' + (m[2]||'')}>{m[1]}</span>
            </div>
          ))}
        </div>
        <div className="deploy-block">
          <h4>Pendientes <span className="tiny">EN CURSO</span></h4>
          <ul className="todo-list">
            {todos.map((t,i)=>{
              const days = t[3] ?? 99;
              let urgClass = 'urg-green';
              let urgIcon = '●';
              let urgLabel = days+'d';
              if(days < 0){ urgClass='urg-skull'; urgIcon='💀'; urgLabel=Math.abs(days)+'d vencido'; }
              else if(days === 0){ urgClass='urg-red'; urgIcon='🔴'; urgLabel='HOY'; }
              else if(days <= 3){ urgClass='urg-yellow'; urgIcon='🟡'; urgLabel=days+'d'; }
              else { urgIcon='🟢'; urgLabel=days+'d'; }
              return (
                <li key={i}>
                  <span className={'dot ' + (t[0]||'')}/>
                  <div className="body">
                    <strong>{t[1]}</strong>
                    <span>{t[2]}</span>
                  </div>
                  <span className={'urg-badge '+urgClass} title={urgLabel}>
                    <span className="urg-ico">{urgIcon}</span>
                    <span className="urg-lbl">{urgLabel}</span>
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   GENTIL — GRÁFICA INTERACTIVA (Recharts)
   ============================================================ */
function GentilChart({ spec }) {
  const R = window.Recharts;
  if (!R) return <div className="gentil-chart-err">Recharts no cargado</div>;

  const {
    BarChart, Bar, LineChart, Line, AreaChart, Area, PieChart, Pie, Cell,
    RadarChart, Radar, PolarGrid, PolarAngleAxis,
    XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
  } = R;

  const color   = spec.color || '#00ff41';
  const data    = spec.data  || [];
  const xKey    = spec.x_key;
  const yKey    = spec.y_key;

  const tooltipStyle = {
    background:'#111', border:'1px solid #2a2a2a',
    color:'#ccc', fontSize:11, borderRadius:6
  };
  const axisProps = { tick:{ fill:'#555', fontSize:10 }, axisLine:{ stroke:'#2a2a2a' } };

  const wrap = (chart) => (
    <div className="gentil-chart">
      <div className="gentil-chart-title">{spec.title}</div>
      {spec.subtitle && <div className="gentil-chart-sub">{spec.subtitle}</div>}
      <ResponsiveContainer width="100%" height={220}>{chart}</ResponsiveContainer>
    </div>
  );

  if (spec.chart_type === 'bar') return wrap(
    <BarChart data={data} margin={{top:8,right:12,bottom:4,left:-16}}>
      <CartesianGrid strokeDasharray="3 3" stroke="#1e1e1e"/>
      <XAxis dataKey={xKey} {...axisProps}/>
      <YAxis {...axisProps}/>
      <Tooltip contentStyle={tooltipStyle}/>
      <Bar dataKey={yKey} fill={color} radius={[3,3,0,0]}/>
    </BarChart>
  );

  if (spec.chart_type === 'line') return wrap(
    <LineChart data={data} margin={{top:8,right:12,bottom:4,left:-16}}>
      <CartesianGrid strokeDasharray="3 3" stroke="#1e1e1e"/>
      <XAxis dataKey={xKey} {...axisProps}/>
      <YAxis {...axisProps}/>
      <Tooltip contentStyle={tooltipStyle}/>
      <Line type="monotone" dataKey={yKey} stroke={color} strokeWidth={2} dot={{fill:color, r:3}}/>
    </LineChart>
  );

  if (spec.chart_type === 'area') return wrap(
    <AreaChart data={data} margin={{top:8,right:12,bottom:4,left:-16}}>
      <defs>
        <linearGradient id="gc" x1="0" y1="0" x2="0" y2="1">
          <stop offset="5%"  stopColor={color} stopOpacity={0.25}/>
          <stop offset="95%" stopColor={color} stopOpacity={0}/>
        </linearGradient>
      </defs>
      <CartesianGrid strokeDasharray="3 3" stroke="#1e1e1e"/>
      <XAxis dataKey={xKey} {...axisProps}/>
      <YAxis {...axisProps}/>
      <Tooltip contentStyle={tooltipStyle}/>
      <Area type="monotone" dataKey={yKey} stroke={color} fill="url(#gc)" strokeWidth={2}/>
    </AreaChart>
  );

  if (spec.chart_type === 'pie') return wrap(
    <PieChart>
      <Pie data={data} dataKey={yKey} nameKey={xKey} cx="50%" cy="50%"
           outerRadius={80} label={({name,percent})=>`${name} ${(percent*100).toFixed(0)}%`}
           labelLine={false}>
        {data.map((_,i)=>{
          const COLORS = ['#00ff41','#00d4aa','#ffd666','#ff6b6b','#89b4fa','#cba6f7'];
          return <Cell key={i} fill={COLORS[i % COLORS.length]}/>;
        })}
      </Pie>
      <Tooltip contentStyle={tooltipStyle}/>
    </PieChart>
  );

  if (spec.chart_type === 'radar') return wrap(
    <RadarChart data={data} cx="50%" cy="50%" outerRadius={80}>
      <PolarGrid stroke="#2a2a2a"/>
      <PolarAngleAxis dataKey={xKey} tick={{fill:'#555', fontSize:10}}/>
      <Radar name={yKey} dataKey={yKey} stroke={color} fill={color} fillOpacity={0.25}/>
      <Tooltip contentStyle={tooltipStyle}/>
    </RadarChart>
  );

  return <div className="gentil-chart-err">Tipo de gráfica desconocido: {spec.chart_type}</div>;
}

/* ============================================================
   GENTIL — TARJETA DE PROPUESTA DE AUTOMATIZACIÓN
   ============================================================ */
function AutomationProposal({ spec, onApprove }) {
  const [decision, setDecision] = React.useState(null);

  const approve = () => {
    setDecision('yes');
    if (onApprove) onApprove(`Gentil, procede con la automatización: "${spec.title}". Crea el workflow en n8n ahora.`);
  };
  const reject = () => setDecision('no');

  const areaColor = {GCF:'#ffd666', GP:'#00ff41', GI:'#89b4fa', GA:'#cba6f7', Transversal:'#00d4aa'};
  const ac = areaColor[spec.area] || '#00ff41';

  return (
    <div className="auto-proposal">
      <div className="auto-proposal-head">
        <span className="auto-proposal-eye" style={{color: ac}}>
          PROPUESTA · {spec.area}
        </span>
        <span className="auto-proposal-title">{spec.title}</span>
      </div>
      <div className="auto-proposal-body">
        <div className="auto-proposal-section">
          <span className="auto-proposal-label">PROBLEMA</span>
          <p>{spec.problema}</p>
        </div>
        <div className="auto-proposal-section">
          <span className="auto-proposal-label">SOLUCIÓN</span>
          <p>{spec.solucion}</p>
        </div>
        <div className="auto-proposal-metrics">
          <div className="auto-proposal-metric">
            <span className="auto-proposal-metric-val">{spec.tiempo_ahorro_hrs_mes}h</span>
            <span className="auto-proposal-metric-lbl">ahorradas/mes</span>
          </div>
          {spec.costo_impl_hrs && (
            <div className="auto-proposal-metric">
              <span className="auto-proposal-metric-val">{spec.costo_impl_hrs}h</span>
              <span className="auto-proposal-metric-lbl">de desarrollo</span>
            </div>
          )}
          <div className="auto-proposal-metric accent" style={{'--ac': ac}}>
            <span className="auto-proposal-metric-val">{spec.roi_semanas}sem</span>
            <span className="auto-proposal-metric-lbl">ROI</span>
          </div>
        </div>
      </div>
      {!decision && (
        <div className="auto-proposal-actions">
          <button className="auto-proposal-btn-yes" onClick={approve}>
            ✓ Proceder · Crear en n8n
          </button>
          <button className="auto-proposal-btn-no" onClick={reject}>
            × Rechazar por ahora
          </button>
        </div>
      )}
      {decision === 'yes' && (
        <div className="auto-proposal-confirmed">
          ✓ Aprobado — Gentil está creando el workflow en n8n…
        </div>
      )}
      {decision === 'no' && (
        <div className="auto-proposal-rejected">
          Descartado · Puedes retomarlo con /n8n_proponer cuando quieras
        </div>
      )}
    </div>
  );
}

/* ============================================================
   GENTIL DRAWER
   ============================================================ */
const MODELS = [
  { id:'haiku', name:'Llama 3.3 70B · GROQ',
    desc:'Consultas operativas, triaje, preguntas rápidas del día a día' },
  { id:'opus',  name:'DeepSeek V4 Pro · Estratégico',
    desc:'Análisis profundo, contratos, proyecciones financieras, decisiones 2030' },
];

const SLASH_COMMANDS = [
  // ─── Internet ───
  { cmd:'/busca',      desc:'Investigar algo en internet en tiempo real',                fill:'/busca — Investiga en internet: ' },
  // ─── La Falla — Gobernanza ───
  { cmd:'/analiza',    desc:'Análisis ejecutivo completo del Centro de Mando',           fill:'/analiza — Dame un análisis ejecutivo completo del estado actual del Centro de Mando.' },
  { cmd:'/salud',      desc:'Salud operativa del colectivo (heatmap)',                   fill:'/salud — ¿Cómo está la salud operativa del colectivo esta semana? Dame el heatmap.' },
  { cmd:'/riesgos',    desc:'Riesgos activos, criticidad I×P y prioridades',            fill:'/riesgos — ¿Cuáles son los riesgos más críticos? Incluye criticidad I×P.' },
  { cmd:'/caja',       desc:'Liquidez, runway y flujos próximos',                       fill:'/caja — Dame el estado de la liquidez: caja total, meses de runway y flujos próximos.' },
  { cmd:'/hitos',      desc:'Progreso hacia la Visión 2030',                            fill:'/hitos — ¿Cómo vamos con los hitos estratégicos hacia 2030? ¿Qué está bloqueado?' },
  { cmd:'/inbox',      desc:'Bandeja de entrada y pendientes de atención',              fill:'/inbox — ¿Qué hay en la bandeja que necesite mi atención hoy?' },
  { cmd:'/area GCF',   desc:'Dirección Comercial y Financiera',                         fill:'/area GCF — Analiza el estado de la Dirección Comercial y Financiera.' },
  { cmd:'/area GP',    desc:'Dirección de Proyectos',                                   fill:'/area GP — Analiza el estado de la Dirección de Proyectos.' },
  { cmd:'/area GI',    desc:'Dirección de Investigación',                               fill:'/area GI — Analiza el estado de la Dirección de Investigación.' },
  { cmd:'/area GA',    desc:'Dirección Audiovisual',                                    fill:'/area GA — Analiza el estado de la Dirección Audiovisual.' },
  { cmd:'/sinergias',  desc:'Cruces y oportunidades entre áreas',                       fill:'/sinergias — ¿Qué sinergias o cruces entre áreas debería aprovechar esta semana?' },
  { cmd:'/status',     desc:'Estado de los servicios del dashboard',                    fill:'/status — ¿Cómo están los servicios del Centro de Mando?' },
  // ─── Frameworks de Pensamiento ───
  { cmd:'/thinking_first_principles', desc:'Análisis desde primeros principios',        fill:'/thinking_first_principles — Analiza este problema desde primeros principios: ' },
  { cmd:'/thinking_pre_mortem',       desc:'¿Qué podría salir mal? (pre-mortem)',       fill:'/thinking_pre_mortem — Aplica un pre-mortem a esta decisión o plan: ' },
  { cmd:'/thinking_red_team',         desc:'Refuta mi idea (red team)',                 fill:'/thinking_red_team — Actúa como red team y refuta esta propuesta: ' },
  { cmd:'/thinking_ooda',             desc:'Bucle Observar→Orientar→Decidir→Actuar',    fill:'/thinking_ooda — Aplica el bucle OODA a esta situación: ' },
  { cmd:'/thinking_systems',          desc:'Análisis sistémico',                        fill:'/thinking_systems — Analiza esto con pensamiento sistémico: ' },
  { cmd:'/thinking_feedback_loops',   desc:'Identifica bucles de retroalimentación',    fill:'/thinking_feedback_loops — Identifica los bucles de retroalimentación en: ' },
  { cmd:'/thinking_constraints',      desc:'Teoría de restricciones (TOC)',             fill:'/thinking_constraints — Aplica la teoría de restricciones a: ' },
  // ─── Gestión de Proyectos ───
  { cmd:'/edt_management',    desc:'Gestionar EDT del proyecto activo',                 fill:'/edt_management — Ayúdame a gestionar el EDT del proyecto: ' },
  { cmd:'/taskflow',          desc:'Flujo de tareas y priorización',                    fill:'/taskflow — Organiza el flujo de tareas de esta semana.' },
  { cmd:'/taskflow_inbox_triage', desc:'Triaje de bandeja de entrada',                  fill:'/taskflow_inbox_triage — Haz triaje de la bandeja de entrada y prioriza.' },
  { cmd:'/ccpm',              desc:'Critical Chain Project Management',                 fill:'/ccpm — Aplica CCPM al proyecto: ' },
  { cmd:'/gerencia_analytics', desc:'Analítica gerencial avanzada',                     fill:'/gerencia_analytics — Dame analítica gerencial del estado actual.' },
  { cmd:'/google_appscript',  desc:'Automatizar con Google Apps Script',                fill:'/google_appscript — Ayúdame a crear un script de Google Apps Script para: ' },
  { cmd:'/healthcheck',       desc:'Verificar estado de los sistemas',                  fill:'/healthcheck — Ejecuta un healthcheck de todos los sistemas.' },
  // ─── N8N — Automatizaciones reales ───
  { cmd:'/n8n_listar',        desc:'Ver todas las automatizaciones en n8n',             fill:'/n8n_listar — Lista todas las automatizaciones de n8n con su estado.' },
  { cmd:'/n8n_fallos',        desc:'Detectar automatizaciones rotas (self-healing)',    fill:'/n8n_fallos — Revisa las ejecuciones fallidas de n8n y propón cómo arreglarlas.' },
  { cmd:'/n8n_crear',         desc:'Crear una nueva automatización en n8n',             fill:'/n8n_crear — Quiero crear una automatización en n8n para: ' },
  { cmd:'/n8n_proponer',      desc:'Proponer automatización con ROI para el CEO',       fill:'/n8n_proponer — Analiza el flujo de trabajo de esta semana y propón la automatización de mayor impacto.' },
  { cmd:'/email',             desc:'Enviar correo electrónico',                         fill:'/email — Envía un correo a ' },
  { cmd:'/grafica',           desc:'Generar gráfica interactiva con datos',             fill:'/grafica — Genera una gráfica de barras con los datos de ' },
  { cmd:'/node_connect',      desc:'Conectar nodo o servicio externo',                  fill:'/node_connect — Ayúdame a conectar este servicio: ' },
  { cmd:'/skill_creator',     desc:'Crear nueva habilidad para el sistema',             fill:'/skill_creator — Crea una nueva habilidad para: ' },
  { cmd:'/find_skills',       desc:'Buscar habilidades disponibles',                    fill:'/find_skills — ¿Qué habilidades tienes disponibles para gestión empresarial?' },
  // ─── Agentes y Herramientas ───
  { cmd:'/tools',      desc:'Herramientas y MCPs disponibles',                          fill:'/tools — ¿Qué herramientas y MCPs tienes disponibles?' },
  { cmd:'/skill',      desc:'Ejecutar una habilidad específica',                        fill:'/skill — Ejecuta la habilidad: ' },
  { cmd:'/subagents',  desc:'Ver sub-agentes activos',                                  fill:'/subagents — ¿Qué sub-agentes tienes activos?' },
  { cmd:'/agents',     desc:'Lista de agentes disponibles',                             fill:'/agents — ¿Qué agentes están disponibles?' },
  { cmd:'/steer',      desc:'Redirigir un agente en curso',                             fill:'/steer — ' },
  { cmd:'/tasks',      desc:'Ver tareas del agente actual',                             fill:'/tasks — ¿Qué tareas tienes en curso?' },
  { cmd:'/context',    desc:'Ver contexto de la sesión',                                fill:'/context — ¿Qué contexto tienes de nuestra conversación?' },
  // ─── Modelo y Configuración ───
  { cmd:'/think',      desc:'Razonamiento extendido paso a paso',                       fill:'/think — Usa razonamiento extendido para analizar: ' },
  { cmd:'/reasoning',  desc:'Ver razonamiento del último análisis',                     fill:'/reasoning — Muéstrame el razonamiento detrás de tu última respuesta.' },
  { cmd:'/verbose',    desc:'Modo detallado (más contexto)',                            fill:'/verbose — Responde en modo detallado: ' },
  { cmd:'/fast',       desc:'Modo rápido (respuesta concisa)',                          fill:'/fast — Responde de forma concisa y directa: ' },
  { cmd:'/usage',      desc:'Uso de tokens y costo de la sesión',                      fill:'/usage — ¿Cuántos tokens hemos usado en esta sesión y cuánto ha costado?' },
  { cmd:'/btw',        desc:'Agregar contexto de fondo',                               fill:'/btw — Nota de contexto: ' },
  // ─── Sesión ───
  { cmd:'/nuevo',      desc:'Nueva conversación (reiniciar)',                           fill:null },
  { cmd:'/reset',      desc:'Reiniciar contexto',                                       fill:null },
  { cmd:'/clear',      desc:'Limpiar mensajes de la sesión',                            fill:null },
  { cmd:'/compactar',  desc:'Resumir conversación actual',                              fill:'/compactar — Resume los puntos clave de esta conversación en un párrafo ejecutivo.' },
  { cmd:'/compact',    desc:'Compactar contexto de conversación',                       fill:'/compact — Resume y compacta el contexto de esta sesión.' },
  { cmd:'/export-session', desc:'Exportar transcripción de la sesión',                 fill:'/export-session — Genera un resumen exportable de esta conversación.' },
];

function routeModel(text) {
  const t = text.toLowerCase();
  const opusKw = ['contrato','presupuest','proyección','estrategia','2030','visión','decisión crítica','fusión','riesgo crítico','síntesis final','analiza','/analiza','/riesgos','/hitos','/sinergias','/thinking_','/ccpm','/edt_','/gerencia_analytics','first_principles','pre_mortem','red_team'];
  if (opusKw.some(w => t.includes(w))) return 'opus';
  return 'haiku';
}

const INIT_MSG = { who:'bot', text:'Hola, Clementino. Soy Gentil — segundo cerebro estratégico del colectivo.\n\nAhora puedo ACTUAR, no solo hablar:\n• /n8n_listar — ver y crear automatizaciones reales en n8n\n• /n8n_fallos — detectar y reparar workflows caídos\n• /busca [tema] — investigar en internet en tiempo real\n• /email — enviar correos reales\n• /grafica — generar gráficas interactivas con tus datos\n• /n8n_proponer — te propongo automatizaciones con ROI calculado\n• Adjuntar PDF/DOCX — leo el contenido completo del archivo\n\nEscribe / para ver todos los comandos disponibles.' };

function ClawDrawer({ open, onClose }){
  const [model, setModel] = useState('haiku');
  const [autoRoute, setAutoRoute] = useState(true);
  const [ddOpen, setDdOpen] = useState(false);
  const [input, setInput] = useState('');
  const [msgs, setMsgs] = useState([INIT_MSG]);
  const [slashOpen, setSlashOpen] = useState(false);
  const [slashIdx, setSlashIdx] = useState(0);
  const [slashFilter, setSlashFilter] = useState('');
  const [drawerWidth, setDrawerWidth] = useState(480);
  const [attachment, setAttachment] = useState(null);
  const [recording, setRecording] = useState(false);
  const mediaRecRef = useRef(null);
  const bodyRef = useRef(null);
  const inputRef = useRef(null);
  const fileRef = useRef(null);

  // Exponer función send globalmente para que proposals puedan disparar mensajes
  const sendDirectRef = useRef(null);

  useEffect(()=>{ if(bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight; },[msgs,open]);
  useEffect(()=>{ const h = (e)=> e.key==='Escape' && !slashOpen && onClose(); window.addEventListener('keydown',h); return ()=>window.removeEventListener('keydown',h); },[onClose,slashOpen]);

  // Auto-grow textarea
  useEffect(()=>{
    const el = inputRef.current;
    if(!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  }, [input]);

  // Drag-resize from left edge
  const startResize = (e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = drawerWidth;
    const onMove = (me) => {
      const newW = Math.min(Math.max(startW + (startX - me.clientX), 360), Math.floor(window.innerWidth * 0.9));
      setDrawerWidth(newW);
    };
    const onUp = () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  // ── Adjuntar archivo ──────────────────────────────────────────
  const handleFile = (file) => {
    const isImage = file.type.startsWith('image/');
    const isText  = file.type.startsWith('text/') || /\.(js|jsx|ts|tsx|py|json|md|csv|sql|txt|html|css)$/i.test(file.name);
    if (isImage) {
      const reader = new FileReader();
      reader.onload = (ev) => {
        const dataUrl = ev.target.result;
        const b64 = dataUrl.split(',')[1];
        setAttachment({ name: file.name, type: 'image', preview: dataUrl, image_b64: b64, image_type: file.type });
      };
      reader.readAsDataURL(file);
    } else if (isText) {
      const reader = new FileReader();
      reader.onload = (ev) => setAttachment({ name: file.name, type: 'text', file_text: ev.target.result });
      reader.readAsText(file);
    } else {
      // PDF / DOCX / Excel: extraer texto en el backend para que Gentil pueda leerlo
      setAttachment({ name: file.name, type: 'document', file_text: '', loading: true });
      const form = new FormData();
      form.append('file', file);
      const k = window.__API_KEY__ || '';
      const b = (window.__API_BASE__ || '').replace(/\/$/,'');
      fetch(`${b}/chat/extract-file`, {
        method: 'POST',
        headers: k ? {'X-API-Key': k} : {},
        body: form,
      })
        .then(r => r.ok ? r.json() : null)
        .then(data => {
          if (data && data.text) {
            const pagesNote = data.pages ? ` (${data.pages} págs.)` : '';
            setAttachment({ name: file.name, type: 'document', file_text: data.text, subtitle: `Texto extraído${pagesNote}` });
          } else {
            const warning = data?.warning || 'Sin extracción automática disponible';
            setAttachment({ name: file.name, type: 'document', file_text: `[Archivo: ${file.name}] ${warning}` });
          }
        })
        .catch(() => {
          setAttachment({ name: file.name, type: 'document', file_text: `[Archivo: ${file.name} — error al extraer contenido]` });
        });
    }
  };

  // ── Grabación de voz ──────────────────────────────────────────
  const toggleRecord = async () => {
    if (recording) {
      if (mediaRecRef.current) mediaRecRef.current.stop();
      setRecording(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
      const rec = new MediaRecorder(stream, { mimeType });
      const chunks = [];
      rec.ondataavailable = (ev) => { if (ev.data.size > 0) chunks.push(ev.data); };
      rec.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(chunks, { type: mimeType });
        const formData = new FormData();
        formData.append('audio', blob, 'recording.webm');
        const k = window.__API_KEY__ || '';
        const b = (window.__API_BASE__ || '').replace(/\/$/,'');
        try {
          setInput(prev => prev + (prev ? ' ' : '') + '…transcribiendo…');
          const r = await fetch(`${b}/chat/transcribe`, {
            method: 'POST', body: formData,
            headers: k ? {'X-API-Key': k} : {},
          });
          if (r.ok) {
            const data = await r.json();
            setInput(prev => prev.replace('…transcribiendo…', data.text));
          } else {
            setInput(prev => prev.replace('…transcribiendo…', ''));
          }
        } catch { setInput(prev => prev.replace('…transcribiendo…', '')); }
      };
      rec.start();
      mediaRecRef.current = rec;
      setRecording(true);
    } catch (err) {
      alert('No se pudo acceder al micrófono: ' + err.message);
    }
  };

  const filteredCmds = slashFilter
    ? SLASH_COMMANDS.filter(c => c.cmd.includes(slashFilter) || c.desc.toLowerCase().includes(slashFilter.toLowerCase()))
    : SLASH_COMMANDS;

  const handleInputChange = (e) => {
    const v = e.target.value;
    setInput(v);
    if (v === '/' || (v.startsWith('/') && !v.includes(' '))) {
      setSlashOpen(true);
      setSlashFilter(v.slice(1));
      setSlashIdx(0);
    } else {
      setSlashOpen(false);
    }
  };

  const selectSlash = (cmd) => {
    setSlashOpen(false);
    if (['/nuevo','/reset','/clear','/new'].includes(cmd.cmd)) { resetConversation(); return; }
    setInput(cmd.fill || cmd.cmd + ' ');
    setTimeout(()=> inputRef.current && inputRef.current.focus(), 0);
  };

  const resetConversation = () => {
    setMsgs([INIT_MSG]);
    setInput('');
    setAttachment(null);
    setSlashOpen(false);
  };

  const buildHistory = (currentMsgs) => {
    return currentMsgs
      .filter(m => m.who !== 'bot' || !m.text.startsWith('Hola.'))
      .slice(-16)
      .map(m => ({ role: m.who === 'me' ? 'user' : 'assistant', content: m.text }));
  };

  const modelObj = MODELS.find(m=>m.id===model);

  const sendText = async (forcedTxt) => {
    const txt = (forcedTxt ?? input).trim();
    if ((!txt && !attachment) || txt === '/') return;
    const chosenModel = autoRoute ? routeModel(txt) : model;
    if (autoRoute) setModel(chosenModel);
    const history = buildHistory(msgs);
    const att = forcedTxt ? null : attachment;
    const displayText = txt || (att ? `[${att.name}]` : '');
    setMsgs(m => [...m, { who:'me', text: displayText, attachment: att }]);
    if (!forcedTxt) {
      setInput('');
      setAttachment(null);
    }
    setSlashOpen(false);
    setMsgs(m => [...m, {who:'bot', text:'Analizando…', loading:true}]);
    try {
      const k = window.__API_KEY__ || '';
      const b = (window.__API_BASE__ || '').replace(/\/$/,'');
      const body = {
        message: txt,
        model: chosenModel,
        history,
        file_text: att?.file_text || '',
        file_name: att?.name || '',
        image_b64: att?.image_b64 || '',
        image_type: att?.image_type || 'image/jpeg',
      };
      const res = await fetch(`${b}/chat`, {
        method: 'POST',
        headers: {'Content-Type':'application/json', ...(k ? {'X-API-Key':k} : {})},
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(()=>({detail:'Error desconocido'}));
        throw new Error(err.detail || res.statusText);
      }
      const data = await res.json();
      setMsgs(m => [...m.slice(0,-1), {
        who:'bot',
        text: data.response,
        usedModel: data.model_used,
        tool_artifacts: data.tool_artifacts || [],
      }]);
    } catch(e) {
      setMsgs(m => [...m.slice(0,-1), {who:'bot', text:`⚠ ${e.message}`}]);
    }
  };

  const send = () => sendText();

  // Exponer para que AutomationProposal pueda disparar mensajes
  sendDirectRef.current = sendText;

  const onKey = (e) => {
    if (slashOpen) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setSlashIdx(i => Math.min(i+1, filteredCmds.length-1)); return; }
      if (e.key === 'ArrowUp')   { e.preventDefault(); setSlashIdx(i => Math.max(i-1, 0)); return; }
      if (e.key === 'Enter')     { e.preventDefault(); if(filteredCmds[slashIdx]) selectSlash(filteredCmds[slashIdx]); return; }
      if (e.key === 'Escape')    { setSlashOpen(false); return; }
    }
    if (e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); send(); }
  };

  return (
    <>
      <div className={'claw-scrim ' + (open?'on':'')} onClick={onClose}/>
      <aside className={'claw ' + (open?'on':'')} style={{width: drawerWidth+'px'}}>
        <div className="claw-resize-handle" onMouseDown={startResize}/>
        <div className="claw-hd">
          <div className="avatar gentil-avatar">G</div>
          <div className="meta">
            <div className="name gentil-brand-name">Gentil</div>
            <div className="model">
              <div className="model-dd">
                <button className="trig" onClick={()=>setDdOpen(v=>!v)}>
                  {autoRoute ? <span style={{color:'var(--falla)',fontSize:9,fontFamily:'var(--f-sub)',letterSpacing:'.08em',fontWeight:700}}>AUTO · </span> : null}
                  {modelObj.name} <span style={{fontSize:8}}>▼</span>
                </button>
                {ddOpen && (
                  <div className="menu" onMouseLeave={()=>setDdOpen(false)}>
                    <div className="item auto-toggle" onClick={()=>{setAutoRoute(v=>!v); setDdOpen(false);}}>
                      <div>
                        <div className="m-name" style={{color: autoRoute ? 'var(--falla)' : 'var(--ink-3)'}}>
                          {autoRoute ? '✓ Auto-routing activado' : '○ Auto-routing desactivado'}
                        </div>
                        <div className="m-desc">Gentil elige el modelo según tu pregunta</div>
                      </div>
                    </div>
                    <div style={{borderTop:'1px solid var(--line)', margin:'4px 0'}}/>
                    {MODELS.map(m=>(
                      <div key={m.id} className={'item ' + (m.id===model && !autoRoute?'sel':'')}
                           onClick={()=>{setModel(m.id); setAutoRoute(false); setDdOpen(false);}}>
                        <div>
                          <div className="m-name">{m.name}</div>
                          <div className="m-desc">{m.desc}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
          <button className="claw-reset-btn" onClick={resetConversation} title="Nueva conversación">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
          </button>
          <button className="close" onClick={onClose}>{I.x}</button>
        </div>

        <div className="claw-body" ref={bodyRef}>
          {msgs.map((m,i)=>(
            <div key={i} className={'msg '+m.who}>
              <div className="who">
                {m.who==='bot'?<span className="gentil-brand-name">Gentil</span>:'Tú'}
                {m.usedModel && <span className="msg-model-badge">{m.usedModel}</span>}
              </div>
              {m.loading && !m.text.includes('⚠') && m.text === 'Analizando…'
                ? <div className="msg-text msg-loading"><span className="loading-dots">···</span></div>
                : m.text && (m.who === 'bot'
                    ? <div className="msg-text md-body" dangerouslySetInnerHTML={{ __html: window.marked ? window.marked.parse(m.text) : m.text.replace(/\n/g,'<br/>') }}></div>
                    : <div className="msg-text" style={{whiteSpace:'pre-wrap'}}>{m.text}</div>
                  )
              }
              {/* Adjuntos de imagen */}
              {m.attachment?.preview && (
                <img src={m.attachment.preview} alt={m.attachment.name}
                     style={{maxWidth:'100%', borderRadius:'8px', marginTop:'6px', display:'block', border:'1px solid #2a2a2a'}}/>
              )}
              {m.attachment && !m.attachment.preview && m.attachment.name && (
                <div style={{marginTop:'4px', fontSize:10, opacity:.6, fontFamily:'var(--f-num)', display:'flex', alignItems:'center', gap:'4px'}}>
                  <span>📄</span>{m.attachment.name}
                </div>
              )}
              {/* Tool artifacts: gráficas y propuestas */}
              {(m.tool_artifacts || []).map((artifact, ai) => {
                if (artifact.__chart__)    return <GentilChart key={ai} spec={artifact}/>;
                if (artifact.__proposal__) return <AutomationProposal key={ai} spec={artifact}
                  onApprove={(txt) => sendDirectRef.current && sendDirectRef.current(txt)}/>;
                return null;
              })}
            </div>
          ))}
          {/* Burbuja de preview — muestra lo que el usuario está escribiendo */}
          {(input.trim() || attachment) && !slashOpen && (
            <div className="msg me typing-preview">
              <div className="who">Tú <span className="typing-label">escribiendo…</span></div>
              {attachment && (
                <div className="typing-att">
                  {attachment.type === 'image' && attachment.preview
                    ? <img src={attachment.preview} alt={attachment.name} style={{maxWidth:'80px', height:'48px', objectFit:'cover', borderRadius:'6px', border:'1px solid #333'}}/>
                    : <span>📄 {attachment.name}</span>
                  }
                </div>
              )}
              {input.trim() && <div className="msg-text" style={{whiteSpace:'pre-wrap', opacity:.55}}>{input}</div>}
            </div>
          )}
        </div>

        <div className="claw-foot">
          {slashOpen && filteredCmds.length > 0 && (
            <div className="slash-menu">
              <div className="slash-menu-hd">Comandos · <kbd>/</kbd></div>
              {filteredCmds.map((c,i)=>(
                <div key={c.cmd}
                     className={'slash-item' + (i===slashIdx?' sel':'')}
                     onMouseEnter={()=>setSlashIdx(i)}
                     onClick={()=>selectSlash(c)}>
                  <span className="slash-cmd">{c.cmd}</span>
                  <span className="slash-desc">{c.desc}</span>
                </div>
              ))}
            </div>
          )}
          {attachment && (
            <div className="attachment-pill">
              {attachment.type === 'image' && attachment.preview
                ? <img src={attachment.preview} className="att-thumb" alt=""/>
                : <span className="att-icon">{attachment.loading ? '⏳' : '📄'}</span>
              }
              <span className="att-name">
                {attachment.name}
                {attachment.loading && <span style={{opacity:.6, fontSize:10, marginLeft:4}}>extrayendo…</span>}
                {attachment.subtitle && <span style={{opacity:.5, fontSize:10, marginLeft:4}}>{attachment.subtitle}</span>}
              </span>
              <button className="att-remove" onClick={()=>setAttachment(null)}>×</button>
            </div>
          )}
          <div className="claw-input">
            <button className="claw-attach-btn" onClick={()=>fileRef.current?.click()}
                    title="Adjuntar imagen, texto o código">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
              </svg>
            </button>
            <input type="file" ref={fileRef} style={{display:'none'}}
                   accept="image/*,.pdf,.xlsx,.csv,.txt,.js,.jsx,.ts,.tsx,.py,.json,.md,.sql,.html,.css"
                   onChange={e=>{ if(e.target.files[0]){ handleFile(e.target.files[0]); e.target.value=''; } }}/>
            <textarea ref={inputRef} value={input} onChange={handleInputChange} onKeyDown={onKey}
              placeholder={recording ? '🔴 Grabando… habla en español' : 'Pregunta, escribe / para comandos o adjunta archivo…'} rows={1}/>
            <button className={'claw-mic-btn' + (recording ? ' rec' : '')}
                    onClick={toggleRecord}
                    title={recording ? 'Detener y transcribir' : 'Grabar nota de voz'}>
              {recording
                ? <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="3"/></svg>
                : <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 2a3 3 0 0 1 3 3v7a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>
              }
            </button>
            <button className="send" onClick={send} disabled={(!input.trim() && !attachment) || input === '/' || attachment?.loading}>{I.send}</button>
          </div>
          <div className="claw-hint">/ comandos · Enter envía · Shift+Enter línea · 📎 adjunta · 🎤 voz</div>
        </div>
      </aside>
    </>
  );
}

/* ============================================================
   MODAL GENÉRICO
   ============================================================ */
function Modal({ open, onClose, eye, title, children, wide }){
  useEffect(()=>{ const h = (e)=> open && e.key==='Escape' && onClose(); window.addEventListener('keydown',h); return ()=>window.removeEventListener('keydown',h); },[open,onClose]);
  return (
    <div className={'modal-scrim ' + (open?'on':'')} onClick={onClose}>
      <div className={'modal ' + (wide?'modal-wide':'')} onClick={e=>e.stopPropagation()}>
        <div className="modal-hd">
          <div>
            <div className="eye">{eye}</div>
            <h2>{title}</h2>
          </div>
          <button className="deploy-close" onClick={onClose}>{I.x}</button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

/* Hoja de Ruta 2026 */
function RoadmapContent(){
  const rows = [
    ['Q1','Consolidar alianza MinCultura','firma + plan de trabajo','80%'],
    ['Q2','Lanzar Cumbre ACMI','piloto audiovisual + narrativa','60%'],
    ['Q3','Abrir Laboratorio Risaralda','infraestructura + curaduría','15%'],
    ['Q4','Memoria 2026 + Visión 2027','cierre editorial','0%'],
  ];
  return (
    <div className="roadmap">
      {rows.map((r,i)=>(
        <div key={i} className="rm-row">
          <span className="q">{r[0]} 2026</span>
          <div className="body"><strong>{r[1]}</strong><span>{r[2]}</span></div>
          <span className="prog tabular">{r[3]}</span>
        </div>
      ))}
    </div>
  );
}

/* Visión 2030 */
function VisionContent(){
  return (
    <>
      <div className="vision-block">
        <div className="quote">«Que La Falla sea, en 2030, el referente audiovisual independiente del Eje Cafetero — con red nacional, laboratorio permanente y autonomía financiera.»</div>
        <div className="cite">MANIFIESTO · COLECTIVO LA FALLA D.F.</div>
      </div>
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
        {[
          ['01','Red nacional','8 ciudades · 4 aliados estratégicos'],
          ['02','Laboratorio','infraestructura propia en Risaralda'],
          ['03','Autonomía','60% ingresos recurrentes no-público'],
          ['04','Archivo vivo','500+ piezas catalogadas y accesibles'],
        ].map((p,i)=>(
          <div key={i} className="rm-row" style={{gridTemplateColumns:'40px 1fr'}}>
            <span className="q">{p[0]}</span>
            <div className="body"><strong>{p[1]}</strong><span>{p[2]}</span></div>
          </div>
        ))}
      </div>
    </>
  );
}

/* Dimensión Estratégica — carga con modal de intención */
const INTENTS = [
  { id:'plan', title:'Modificar Plan Estratégico',
    desc:'Re-calcula todo el roadmap 2026–2030 con el nuevo documento como fuente.',
    badge:'ALTO IMPACTO', tone:'crit' },
  { id:'obs', title:'Generar Observaciones e Ideas',
    desc:'Gentil lee y sugiere, no modifica el plan. Aparece en Lectura del Día.',
    badge:'RECOMENDADO', tone:'ok' },
  { id:'pend', title:'Lista de Pendientes',
    desc:'Guarda el documento para revisión posterior. No se procesa ahora.',
    badge:'DIFERIDO', tone:'mute' },
];

function DimensionContent({ onIntent }){
  const [files, setFiles] = useState([]);
  const [hot, setHot] = useState(false);
  const [pending, setPending] = useState(null);
  const [pendingFile, setPendingFile] = useState(null); // File object for upload
  const [linkMode, setLinkMode] = useState(false);
  const [linkUrl, setLinkUrl] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const inputRef = useRef(null);

  const queueFile = (f) => {
    const newFile = {
      name:f.name,
      size:(f.size/1024 > 1024 ? (f.size/1024/1024).toFixed(1)+' MB' : Math.round(f.size/1024)+' KB'),
      status:'pending', type:'file',
    };
    setPendingFile(f);
    setPending(newFile);
  };
  const addFiles = (fs) => { if(fs?.length) queueFile(fs[0]); };

  const queueLink = () => {
    if(!linkUrl.trim()) return;
    const url = linkUrl.trim();
    const name = url.length > 50 ? url.slice(0,47)+'...' : url;
    const isGDrive = /drive\.google|docs\.google/.test(url);
    setPendingFile(null);
    setPending({ name, size: isGDrive ? 'Google Drive' : 'Enlace', status:'pending', type:'link', url });
    setLinkUrl('');
    setLinkMode(false);
  };

  const confirmIntent = async (intentId) => {
    if(!pending) return;
    const entry = { ...pending, status:'proc', intent:intentId };
    setFiles(prev => [entry, ...prev]);
    setPending(null);
    setUploading(true);
    setUploadResult(null);

    try {
      const k = window.__API_KEY__ || '';
      const b = (window.__API_BASE__ || '/api').replace(/\/$/,'');
      const fd = new FormData();
      fd.append('intent', intentId);

      if(pendingFile) {
        fd.append('file', pendingFile, pendingFile.name);
      } else if(pending.url) {
        fd.append('url', pending.url);
        fd.append('filename_hint', pending.name);
      }

      const res = await fetch(`${b}/strategy/ingest-resource`, {
        method:'POST',
        headers: k ? {'X-API-Key':k} : {},
        body: fd,
      });
      const data = await res.json().catch(()=>({ok:false, message:'Error de comunicación'}));

      setFiles(prev => prev.map(f =>
        f.name===entry.name ? {...f, status: res.ok ? 'ok' : 'err'} : f
      ));
      setUploadResult(res.ok ? { ok:true, text: data.analysis || data.message } : { ok:false, text: data.detail || data.message || 'Error al procesar' });
    } catch(e) {
      setFiles(prev => prev.map(f => f.name===entry.name ? {...f, status:'err'} : f));
      setUploadResult({ ok:false, text:'Error de conexión con el servidor.' });
    } finally {
      setUploading(false);
      setPendingFile(null);
    }
  };

  const ext = (f) => f.type==='link' ? '🔗' : f.name.split('.').pop().slice(0,4).toUpperCase();
  const intentLabel = (id) => INTENTS.find(i=>i.id===id)?.title || '—';

  return (
    <>
      {!linkMode ? (
        <div className={'dropzone ' + (hot?'hot':'')}
             onClick={()=>inputRef.current?.click()}
             onDragOver={e=>{e.preventDefault(); setHot(true);}}
             onDragLeave={()=>setHot(false)}
             onDrop={e=>{e.preventDefault(); setHot(false); addFiles(e.dataTransfer.files);}}>
          <span className="ico">⇪</span>
          <div className="t">Sube un documento o enlace</div>
          <div className="s">PDF · DOCX · TXT · Links — al soltarlo, Gentil te preguntará qué hacer con él</div>
          <input type="file" ref={inputRef} onChange={e=>addFiles(e.target.files)}/>
        </div>
      ) : (
        <div className="link-input-box">
          <div className="link-ico">🔗</div>
          <div className="link-body">
            <div className="link-label">Pega un enlace · Google Drive, Notion, URL directa</div>
            <div className="link-row">
              <input
                type="url"
                className="link-field"
                placeholder="https://drive.google.com/..."
                value={linkUrl}
                onChange={e=>setLinkUrl(e.target.value)}
                onKeyDown={e=>{ if(e.key==='Enter') queueLink(); }}
                autoFocus
              />
              <button className="link-go" onClick={queueLink} disabled={!linkUrl.trim()}>Añadir</button>
            </div>
          </div>
        </div>
      )}

      <div className="upload-toggle-row">
        <button className={'upload-tab ' + (!linkMode?'on':'')} onClick={()=>setLinkMode(false)}>
          <span>📄</span> Documento
        </button>
        <button className={'upload-tab ' + (linkMode?'on':'')} onClick={()=>setLinkMode(true)}>
          <span>🔗</span> Enlace / Link
        </button>
      </div>

      {uploading && (
        <div className="upload-progress">
          <span className="upload-spinner"/>
          Gentil está analizando el documento…
        </div>
      )}

      {uploadResult && (
        <div className={'upload-result ' + (uploadResult.ok ? 'ok' : 'err')}>
          <div className="ur-badge">{uploadResult.ok ? '✓ ANÁLISIS LISTO' : '✗ ERROR'}</div>
          <div className="ur-text">{uploadResult.text}</div>
          {uploadResult.ok && <div className="ur-note">Guardado en Lectura del Día · recarga para ver la sugerencia.</div>}
          <button className="ur-close" onClick={()=>setUploadResult(null)}>Cerrar</button>
        </div>
      )}

      <div className="file-list">
        {files.map((f,i)=>(
          <div key={i} className="file-item">
            <span className="t-icon">{ext(f)}</span>
            <div>
              <div className="name">{f.name}</div>
              <div className="meta">{f.size} · {intentLabel(f.intent)}</div>
            </div>
            <span className={'status '+f.status}>{f.status==='proc'?'PROCESANDO':f.status==='err'?'ERROR':'LISTO'}</span>
          </div>
        ))}
      </div>

      {/* Intent modal — aparece sobre el modal principal */}
      {pending && (
        <div className="intent-scrim" onClick={()=>setPending(null)}>
          <div className="intent-box" onClick={e=>e.stopPropagation()}>
            <div className="intent-hd">
              <div className="eye">NUEVO RECURSO · {pending.name.slice(0,40)}</div>
              <h3>¿Cuál es el <em>objetivo</em> de este documento?</h3>
              <span className="intent-sub">Elige una acción · Gentil no procesa nada sin tu instrucción.</span>
            </div>
            <div className="intent-opts">
              {INTENTS.map(opt => (
                <button key={opt.id} className={'intent-opt t-'+opt.tone} onClick={()=>confirmIntent(opt.id)}>
                  <div className="i-head">
                    <span className={'i-badge '+opt.tone}>{opt.badge}</span>
                    <strong>{opt.title}</strong>
                  </div>
                  <span className="i-desc">{opt.desc}</span>
                  <span className="i-arrow">→</span>
                </button>
              ))}
            </div>
            <button className="intent-cancel" onClick={()=>setPending(null)}>Cancelar · volver</button>
          </div>
        </div>
      )}

      {/* Zona de peligro — oculta al final */}
      <ResetStrategyZone/>
    </>
  );
}

/* ============================================================
   RESET STRATEGY — zona oculta + modal de confirmación
   ============================================================ */
function ResetStrategyZone(){
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(1);
  const [checked, setChecked] = useState(false);
  const [pwd, setPwd] = useState('');
  const [status, setStatus] = useState(null); // null | 'loading' | 'ok' | 'err'
  const [errMsg, setErrMsg] = useState('');

  const close = () => { setOpen(false); setStep(1); setChecked(false); setPwd(''); setStatus(null); setErrMsg(''); };

  const confirm = async () => {
    setStatus('loading');
    try {
      const k = window.__API_KEY__ || '';
      const b = (window.__API_BASE__ || '').replace(/\/$/,'');
      const res = await fetch(`${b}/strategy/reset`, {
        method: 'DELETE',
        headers: { 'Content-Type':'application/json', ...(k ? {'X-API-Key':k} : {}) },
        body: JSON.stringify({ password: pwd }),
      });
      const data = await res.json().catch(()=>({detail:'Error desconocido'}));
      if (!res.ok) { setStatus('err'); setErrMsg(data.detail || 'Error al reiniciar.'); return; }
      setStatus('ok');
    } catch(e) { setStatus('err'); setErrMsg('Error de conexión.'); }
  };

  return (
    <>
      <div className="reset-zone">
        <button className="reset-zone-trigger" onClick={()=>setOpen(true)}>
          ⚠ Zona de reinicio estratégico
        </button>
      </div>

      {open && (
        <div className="reset-scrim" onClick={close}>
          <div className="reset-box" onClick={e=>e.stopPropagation()}>
            {status === 'ok' ? (
              <>
                <div className="reset-ok-icon">✓</div>
                <div className="reset-ok-title">Estrategia reiniciada</div>
                <p className="reset-ok-sub">Todos los datos estratégicos han sido eliminados. El dashboard volverá a su estado inicial.</p>
                <button className="reset-close-btn" onClick={()=>{ close(); window.location.reload(); }}>Cerrar y recargar</button>
              </>
            ) : (
              <>
                <div className="reset-warn-icon">⚠</div>
                <div className="reset-title">Reiniciar Estrategia</div>
                <p className="reset-sub">Esta acción elimina <strong>todos los datos estratégicos</strong> del Centro de Mando: hitos, riesgos, proyectos, finanzas, sugerencias y bandeja de entrada. <em>No hay vuelta atrás.</em></p>

                {step === 1 && (
                  <>
                    <label className="reset-check-row">
                      <input type="checkbox" checked={checked} onChange={e=>setChecked(e.target.checked)}/>
                      <span>Entiendo que esta acción es <strong>irreversible</strong> y borrará toda la estrategia cargada en el sistema.</span>
                    </label>
                    <div className="reset-actions">
                      <button className="reset-cancel" onClick={close}>Cancelar</button>
                      <button className="reset-next" disabled={!checked} onClick={()=>setStep(2)}>Continuar →</button>
                    </div>
                  </>
                )}

                {step === 2 && (
                  <>
                    <div className="reset-pwd-label">Ingresa la contraseña de autorización para confirmar:</div>
                    <input
                      type="password"
                      className="reset-pwd-input"
                      placeholder="Contraseña de reinicio"
                      value={pwd}
                      onChange={e=>{ setPwd(e.target.value); setErrMsg(''); }}
                      onKeyDown={e=>{ if(e.key==='Enter' && pwd && status !== 'loading') confirm(); }}
                      autoFocus
                    />
                    {errMsg && <div className="reset-err">{errMsg}</div>}
                    <div className="reset-actions">
                      <button className="reset-cancel" onClick={()=>setStep(1)} disabled={status==='loading'}>Atrás</button>
                      <button className="reset-confirm" disabled={!pwd || status==='loading'} onClick={confirm}>
                        {status==='loading' ? 'Eliminando…' : 'Eliminar toda la estrategia'}
                      </button>
                    </div>
                  </>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}

/* ============================================================
   KPI DETAIL MODALS — contenido
   ============================================================ */
function PulsoDetail(){
  const [drillOpen, setDrillOpen] = React.useState(false);
  const pulsoData = useApiData('pulso');

  const AREAS_META = [
    { code:'GCF', name:'Dirección Comercial',    trend:'+3',
      triggers:['feedback: 4.2/5','horas extra: 34h','disponibilidad: alta'],
      note:'Equipo estable. Alta carga por cierre fiscal Q2.' },
    { code:'GP',  name:'Dirección de Proyectos', trend:'-2',
      triggers:['feedback: 3.6/5','horas extra: 54h ⚠','días libres: 8% ⚠'],
      note:'Rutas Cafeteras 02 presiona. Considerar refuerzo.' },
    { code:'GI',  name:'Dirección de Investigación', trend:'+5',
      triggers:['feedback: 4.6/5','horas extra: 22h','disponibilidad: alta'],
      note:'Campo productivo. Publicaciones al día.' },
    { code:'GA',  name:'Dirección Audiovisual',  trend:'-1',
      triggers:['feedback: 3.8/5','horas extra: 48h','rodaje día 3/5'],
      note:'Piloto en rodaje día 3/5. Intensidad alta.' },
  ];
  const SCORES_FALLBACK = [78, 64, 82, 66];
  const apiScores = pulsoData?.rows?.map(r => r.score);
  const areas = AREAS_META.map((m, i) => {
    const score = apiScores?.[i] ?? SCORES_FALLBACK[i];
    return { ...m, score, flag: score >= 75 ? 'ok' : 'warn' };
  });

  const saludScore = pulsoData ? Math.round(pulsoData.salud_global) : Math.round(areas.reduce((s,a)=>s+a.score,0)/4);
  const deltaVal   = pulsoData ? (pulsoData.delta ?? 0) : 4;
  const deltaStr   = (deltaVal >= 0 ? '+' : '') + deltaVal + ' vs. semana pasada';
  const prevScore  = saludScore - deltaVal;

  const LEVEL_COLORS = [
    null,
    { label:'Crítico',  desc:'>50h extra · <10% días libres', color:'#ef4444' },
    { label:'Fricción', desc:'Sobrecosto · caída de puntos',   color:'#f97316' },
    { label:'Estable',  desc:'Operación normal · ≤40h extra',  color:'#86efac' },
    { label:'Óptimo',   desc:'Feedback >4.5 · 0h extra',       color:'#00FF41' },
  ];

  return (
    <div className="kd">
      {/* Hero — clickable para ir al drill-down */}
      <button className="kd-hero kd-hero-btn" onClick={()=>setDrillOpen(true)}>
        <PulsoViz rows={pulsoData?.rows}/>
        <div className="kd-hero-side">
          <div className="kd-big"><span className="n num-mono">{saludScore}</span><span className="u">/100</span></div>
          <div className={'kd-delta ' + (deltaVal >= 0 ? 'up' : 'dn')}>▲ {deltaStr}</div>
          <p className="kd-lede">La organización está <strong>en forma</strong>. 3 de 4 áreas en verde. El cuidado está en Proyectos y Audiovisual, donde la intensidad de rodaje eleva la carga.</p>
          <span className="kd-hero-hint">Clic para ver fórmula y análisis completo →</span>
        </div>
      </button>

      <div className="kd-sec-head">ÁREAS · DESGLOSE</div>
      <div className="kd-areas">
        {areas.map(a=>(
          <div key={a.code} className={'kd-area f-'+a.flag}>
            <span className="kd-code num-mono">{a.code}</span>
            <div className="kd-a-body">
              <strong>{a.name}</strong>
              <span>{a.note}</span>
            </div>
            <div className="kd-a-score">
              <span className="n num-mono">{a.score}</span>
              <span className={'t ' + (a.trend.startsWith('+')?'up':'down')}>{a.trend}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="kd-action">
        <strong>Recomendación <span className="gentil-brand-name">Gentil</span></strong>
        <p>Agendar conversación 1:1 con líder de Proyectos esta semana. La caída de 2 puntos + carga de Rutas Cafeteras 02 justifica una intervención cultural temprana, antes de que afecte la entrega del piloto.</p>
      </div>

      {/* Drill-down: fórmula + heatmap completo + leyenda */}
      {drillOpen && (
        <div className="pulso-drill-scrim" onClick={()=>setDrillOpen(false)}>
          <div className="pulso-drill-box" onClick={e=>e.stopPropagation()}>
            <div className="pulso-drill-hd">
              <div>
                <div className="pf-eye">ANÁLISIS PROFUNDO · PULSO DEL COLECTIVO</div>
                <h2 className="pulso-drill-title">Fórmula Global · <em>Trazabilidad</em></h2>
              </div>
              <button className="pulso-drill-close" onClick={()=>setDrillOpen(false)}>×</button>
            </div>

            {/* Fórmula */}
            <div className="pulso-formula">
              <div className="pf-eye">SALUD = Σ(S_GCF + S_GP + S_GI + S_GA) / 4</div>
              <div className="pf-row">
                {areas.map(a=>(
                  <div key={a.code} className="pf-term">
                    <span className={'pf-val num-mono f-'+a.flag}>{a.score}</span>
                    <span className="pf-code">{a.code}</span>
                  </div>
                ))}
                <div className="pf-eq">÷ 4</div>
                <div className="pf-result">
                  <span className="pf-r num-mono">{saludScore}</span>
                  <span className={'pf-delta ' + (deltaVal >= 0 ? 'up' : 'dn')}>▲ {(deltaVal >= 0 ? '+' : '') + deltaVal} vs. {prevScore}</span>
                </div>
              </div>
            </div>

            {/* Heatmap completo */}
            <div className="kd-sec-head">MAPA DE CALOR · SEMANA ACTUAL</div>
            <div className="pulso-full-heat">
              <div className="pfh-days">
                <span className="pfh-axis"></span>
                {['LUN','MAR','MIÉ','JUE','VIE','SÁB','DOM'].map(d=>(
                  <span key={d} className="pfh-day">{d}</span>
                ))}
                <span className="pfh-score-h">S</span>
              </div>
              {PULSO_ROWS.map(r=>(
                <div key={r.area} className="pfh-row">
                  <span className="pfh-label">{r.area}</span>
                  {r.values.map((v,i)=>(
                    <div key={i} className={'pfh-cell v'+v} title={LEVEL_COLORS[v]?.label||''}/>
                  ))}
                  <div className="pfh-score">
                    <span className={'pfh-s num-mono f-'+(r.score>=75?'ok':'warn')}>{r.score}</span>
                  </div>
                </div>
              ))}
            </div>

            {/* Leyenda */}
            <div className="pulso-legend">
              {LEVEL_COLORS.slice(1).reverse().map(l=>(
                <div key={l.label} className="pl-item">
                  <span className="pl-dot" style={{background:l.color}}/>
                  <span className="pl-lbl">{l.label}</span>
                  <span className="pl-desc">{l.desc}</span>
                </div>
              ))}
            </div>

            {/* Variables de entrada */}
            <div className="kd-sec-head">VARIABLES DE ENTRADA · MANUALES DE FUNCIONES</div>
            <div className="kd-areas">
              {areas.map(a=>(
                <div key={a.code} className={'kd-area f-'+a.flag}>
                  <span className="kd-code num-mono">{a.code}</span>
                  <div className="kd-a-body">
                    <strong>{a.name}</strong>
                    <span>{a.note}</span>
                    <div className="kd-triggers">
                      {a.triggers.map((t,i)=><span key={i} className="kd-trigger">{t}</span>)}
                    </div>
                  </div>
                  <div className="kd-a-score">
                    <span className="n num-mono">{a.score}</span>
                    <span className={'t '+(a.trend.startsWith('+')?'up':'down')}>{a.trend}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function VisionDetail(){
  const [drillOpen, setDrillOpen] = React.useState(false);
  const apiArcs = useApiData('arcs');

  const getArcVal = (label, fallback) => {
    if (!apiArcs) return fallback;
    const a = apiArcs.find(x => x.label === label);
    return a != null ? Math.round(a.value) : fallback;
  };

  const pillars = [
    { code:'EJE ESTRAT.', value: getArcVal('EJE ESTRAT.', 58), color:'#0E0E0E', note:'Consolidar Eje Cafetero como destino fílmico.', sub:'6 hitos de 12 · 2 en riesgo · 4 completos', hitos:[{t:'Identidad de marca',done:true},{t:'Red aliados Q1',done:true},{t:'Piloto «Eje»',done:true},{t:'Lab Risaralda',done:false},{t:'Cumbre ACMI',done:false},{t:'Escala nacional',done:false}] },
    { code:'CAPTACIÓN',   value: getArcVal('CAPTACIÓN', 65),   color:'#00FF41', note:'Diversificar fuentes de financiación.', sub:'Adelantados 7% vs. plan · FDC 2026 pendiente', hitos:[{t:'FDC Q1',done:true},{t:'MinCultura Q1',done:true},{t:'Privados',done:false},{t:'FDC Q2',done:false}] },
    { code:'ENTREGAS',    value: getArcVal('ENTREGAS', 78),    color:'#0E0E0E', note:'Ratio proyectos on-time sobre comprometido.', sub:'7 de 9 on-time · 2 reprogramados a Q3', hitos:[{t:'Rutas 01',done:true},{t:'Piloto OK',done:true},{t:'Lab Risaralda',done:false}] },
    { code:'RIESGO',      value: getArcVal('RIESGO', 22),      color:'#E8A02C', note:'Índice exposición: meta mantener < 30%.', sub:'Zona sana · en control', hitos:[{t:'MinCultura',done:true},{t:'Diversif. finanzas',done:false}] },
  ];
  const v2030 = getArcVal('EJE ESTRAT.', 58);

  return (
    <div className="kd">
      <button className="kd-hero kd-hero-btn" onClick={()=>setDrillOpen(true)}>
        <RadialViz size={210} arcs={apiArcs}/>
        <div className="kd-hero-side">
          <div className="kd-big"><span className="n num-mono">{v2030}</span><span className="u">%</span></div>
          <div className="kd-delta up">▲ +6 vs. Q1</div>
          <p className="kd-lede">Vamos <strong>algo más que a medio camino</strong> hacia la visión 2030. Captación adelantada, ejecución al ritmo esperado.</p>
          <span className="kd-hero-hint">Clic para ver pilares y hitos →</span>
        </div>
      </button>
      <div className="kd-sec-head">PILARES · 4 DIMENSIONES</div>
      <div className="kd-pillars">
        {pillars.map(p=>(
          <div key={p.code} className="kd-pillar">
            <div className="kd-p-head">
              <span className="kd-p-code num-mono">{p.code}</span>
              <span className="kd-p-val num-mono">{p.value}%</span>
            </div>
            <div className="kd-p-track"><div className="kd-p-fill" style={{width:p.value+'%'}}/></div>
            <strong>{p.note}</strong>
            <span>{p.sub}</span>
          </div>
        ))}
      </div>
      <div className="kd-action">
        <strong>Lectura para el CEO</strong>
        <p>El foco ahora es <strong>consolidar el Eje Cafetero</strong>: 2 hitos del pilar estratégico en riesgo. Gentil sugiere revisar con Proyectos antes de fin de mes.</p>
      </div>

      {drillOpen && (
        <div className="pulso-drill-scrim" onClick={()=>setDrillOpen(false)}>
          <div className="pulso-drill-box" onClick={e=>e.stopPropagation()}>
            <div className="pulso-drill-hd">
              <div>
                <div className="pf-eye">ANÁLISIS PROFUNDO · EJECUCIÓN ESTRATÉGICA 2030</div>
                <h2 className="pulso-drill-title">Pilares · <em>Hitos y avance</em></h2>
              </div>
              <button className="pulso-drill-close" onClick={()=>setDrillOpen(false)}>×</button>
            </div>
            <div style={{padding:'24px 28px', display:'grid', gridTemplateColumns:'1fr 1fr', gap:16}}>
              {pillars.map(p=>(
                <div key={p.code} style={{padding:18, background:'var(--bg)', border:'1px solid var(--line)', borderRadius:'var(--r-md)', borderLeft:`4px solid ${p.color}`}}>
                  <div style={{display:'flex', justifyContent:'space-between', marginBottom:8}}>
                    <span style={{fontFamily:'var(--f-title)', fontSize:11, fontWeight:700, textTransform:'uppercase', letterSpacing:'.04em', color:'var(--ink)'}}>{p.code}</span>
                    <span style={{fontFamily:'var(--f-num)', fontSize:18, fontWeight:700, color:'var(--ink)'}}>{p.value}%</span>
                  </div>
                  <div style={{height:4, background:'var(--line)', borderRadius:2, marginBottom:10}}>
                    <div style={{height:'100%', width:p.value+'%', background:p.color, borderRadius:2}}/>
                  </div>
                  <p style={{fontFamily:'var(--f-body)', fontSize:12, color:'var(--mute)', margin:'0 0 10px', lineHeight:1.4}}>{p.note}</p>
                  <ul style={{listStyle:'none', padding:0, margin:0, display:'flex', flexDirection:'column', gap:5}}>
                    {p.hitos.map((h,i)=>(
                      <li key={i} style={{display:'flex', alignItems:'center', gap:8, fontFamily:'var(--f-body)', fontSize:12, color:h.done?'var(--mute)':'var(--ink)', textDecoration:h.done?'line-through':'none'}}>
                        <span style={{width:16, height:16, borderRadius:4, background:h.done?'#00FF41':'var(--line)', display:'grid', placeItems:'center', fontSize:10, fontWeight:700, color:'#001', flexShrink:0}}>{h.done?'✓':'○'}</span>
                        {h.t}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CajaDetail(){
  const [drillOpen, setDrillOpen] = React.useState(false);
  const [selMonth, setSelMonth] = React.useState(null);
  const cajaData = useApiData('caja');

  const latest = cajaData?.latest;
  const sources = latest ? [
    ['Caja operativa',         latest.caja    + 'M', 'ok'],
    ['Reservas estratégicas',  latest.reservas + 'M', 'ok'],
    ['Línea de crédito disp.', latest.credito  + 'M', 'ok'],
  ] : [
    ['Caja operativa',        '6.2M', 'ok'],
    ['Reservas estratégicas', '2.1M', 'ok'],
    ['Línea de crédito disp.','0.9M', 'ok'],
  ];

  const flows = cajaData?.flows || [];
  const risks = flows.length ? flows.map(f => [
    f.descripcion,
    (f.monto >= 0 ? '+' : '') + (f.monto/1000000).toFixed(1) + 'M',
    f.frecuencia || (f.horizonte_dias ? f.horizonte_dias + 'd' : ''),
    f.monto >= 0 ? 'ok' : 'warn',
  ]) : [
    ['Cobro pendiente FDC',    '42M',   '60d',    'ok'],
    ['Pago nómina + impuestos','-3.1M', 'mensual','warn'],
    ['Rodaje Piloto (fase 3)', '-1.8M', '60d',    'warn'],
  ];

  const MONTHS_FALLBACK = [
    {m:'May-25',v:6.4},{m:'Jun',v:6.1},{m:'Jul',v:5.8},{m:'Ago',v:6.2},{m:'Sep',v:6.9},{m:'Oct',v:7.4},
    {m:'Nov',v:7.8},{m:'Dic',v:8.1},{m:'Ene-26',v:8.4},{m:'Feb',v:8.7},{m:'Mar',v:9.0},{m:'Abr',v:9.2},
  ];
  const months = cajaData?.months?.length >= 2
    ? cajaData.months.map(([m, v]) => ({ m, v }))
    : MONTHS_FALLBACK;

  const cajaTotal = latest?.total ?? 9.2;
  const cajaMeses = latest?.meses ?? 9;
  const maxV = Math.max(...months.map(m=>m.v));
  return (
    <div className="kd">
      <button className="kd-hero kd-hero-btn" onClick={()=>setDrillOpen(true)}>
        <div className="kd-caja-chart">
          <CajaViz months={cajaData?.months}/>
          <div className="kd-caja-scale">
            <span>12M</span><span>9M</span><span>6M</span><span>3M</span><span>0</span>
          </div>
        </div>
        <div className="kd-hero-side">
          <div className="kd-big"><span className="n num-mono">{cajaTotal}</span><span className="u">M COP</span></div>
          <div className="kd-delta up">▲ +0.8M vs. mes pasado</div>
          <p className="kd-lede">Tenemos <strong>{cajaMeses} meses de respiración</strong> al ritmo actual. Tendencia al alza desde julio.</p>
          <span className="kd-hero-hint">Clic para ver flujos y proyección →</span>
        </div>
      </button>
      <div className="kd-sec-head">FUENTES DE LIQUIDEZ</div>
      <div className="kd-sources">
        {sources.map(([l,v,f],i)=>(
          <div key={i} className={'kd-src f-'+f}>
            <span className="l">{l}</span>
            <span className="v num-mono">{v}</span>
          </div>
        ))}
      </div>
      <div className="kd-sec-head">FLUJOS PRÓXIMOS 90 DÍAS</div>
      <div className="kd-risks">
        {risks.map(([l,v,t,f],i)=>(
          <div key={i} className={'kd-risk f-'+f}>
            <span className="l">{l}</span>
            <span className="t">{t}</span>
            <span className="v num-mono">{v}</span>
          </div>
        ))}
      </div>
      <div className="kd-action">
        <strong>Ventana de decisión</strong>
        <p>El colchón habilita inversión controlada en tecnología o acelerar contratación. Si el cobro FDC se retrasa +60d, revisar antes de comprometer.</p>
      </div>

      {drillOpen && (
        <div className="pulso-drill-scrim" onClick={()=>setDrillOpen(false)}>
          <div className="pulso-drill-box" onClick={e=>e.stopPropagation()}>
            <div className="pulso-drill-hd">
              <div>
                <div className="pf-eye">ANÁLISIS PROFUNDO · LIQUIDEZ OPERATIVA</div>
                <h2 className="pulso-drill-title">Proyección 12 meses · <em>Combustible</em></h2>
              </div>
              <button className="pulso-drill-close" onClick={()=>setDrillOpen(false)}>×</button>
            </div>
            <div style={{padding:'24px 28px', display:'flex', flexDirection:'column', gap:22}}>
              {/* Bar chart ampliado */}
              <div>
                <div style={{fontFamily:'var(--f-sub)', fontSize:10, fontWeight:600, letterSpacing:'.14em', textTransform:'uppercase', color:'var(--mute)', paddingBottom:8, borderBottom:'1px solid var(--line)', marginBottom:14}}>TENDENCIA · 12 MESES (M COP)</div>
                <div style={{display:'flex', alignItems:'flex-end', gap:6, height:140, position:'relative'}}>
                  {months.map((m,i)=>{
                    const isLast = i===months.length-1;
                    const isSel = selMonth===i;
                    const h = (m.v/maxV*100)+'%';
                    const MONTH_DETAIL = [
                      {ingresos:'FDC cuota 1',i:'3.2M',egresos:'Nómina',e:'2.1M',balance:'+0.1'},
                      {ingresos:'Alianzas',i:'2.8M',egresos:'Rodaje',e:'2.9M',balance:'-0.3'},
                      {ingresos:'MinCultura',i:'2.6M',egresos:'Post-prod',e:'2.6M',balance:'-0.2'},
                      {ingresos:'Privados',i:'3.0M',egresos:'Nómina',e:'2.2M',balance:'+0.4'},
                      {ingresos:'FDC cuota 2',i:'3.8M',egresos:'Operaciones',e:'2.4M',balance:'+0.7'},
                      {ingresos:'ACMI',i:'4.1M',egresos:'Nómina',e:'2.3M',balance:'+0.5'},
                      {ingresos:'Alianzas',i:'4.2M',egresos:'Lab Risaralda',e:'2.6M',balance:'+0.4'},
                      {ingresos:'FDC cuota 3',i:'4.0M',egresos:'Nómina',e:'2.1M',balance:'+0.3'},
                      {ingresos:'Privados+FDC',i:'4.4M',egresos:'Tecnología',e:'2.2M',balance:'+0.3'},
                      {ingresos:'MinCultura 2',i:'4.6M',egresos:'Nómina',e:'2.3M',balance:'+0.3'},
                      {ingresos:'Alianzas',i:'4.8M',egresos:'Operaciones',e:'2.4M',balance:'+0.3'},
                      {ingresos:'FDC+Privados',i:'5.2M',egresos:'Nómina+pauta',e:'2.6M',balance:'+0.2'},
                    ][i] || {};
                    return (
                      <div key={i} style={{flex:1, display:'flex', flexDirection:'column', alignItems:'center', gap:4, height:'100%', justifyContent:'flex-end', position:'relative', cursor:'pointer'}}
                           onClick={()=>setSelMonth(isSel?null:i)}>
                        {isSel && (
                          <div style={{
                            position:'absolute', bottom:'calc(100% + 8px)', left:'50%', transform:'translateX(-50%)',
                            background:'#1a1a1a', color:'#fff', borderRadius:8, padding:'10px 13px', zIndex:100,
                            width:160, boxShadow:'0 4px 20px rgba(0,0,0,.5)', border:'1px solid rgba(255,255,255,.1)',
                            fontFamily:'IBM Plex Mono,monospace', fontSize:10, lineHeight:1.6,
                          }} onClick={e=>e.stopPropagation()}>
                            <div style={{color:'#00FF41', marginBottom:4, fontSize:9, letterSpacing:'.08em'}}>{m.m} — ${m.v}M COP</div>
                            <div style={{color:'#aaa', fontSize:9}}>Ingresos: <span style={{color:'#00FF41'}}>{MONTH_DETAIL.i}</span></div>
                            <div style={{color:'#aaa', fontSize:9, marginBottom:2}}>  {MONTH_DETAIL.ingresos}</div>
                            <div style={{color:'#aaa', fontSize:9}}>Egresos: <span style={{color:'#e89c2b'}}>{MONTH_DETAIL.e}</span></div>
                            <div style={{color:'#aaa', fontSize:9, marginBottom:4}}>  {MONTH_DETAIL.egresos}</div>
                            <div style={{fontSize:10, fontWeight:700, color: MONTH_DETAIL.balance?.startsWith('+')?'#00FF41':'#cc3333'}}>Balance: {MONTH_DETAIL.balance}M</div>
                          </div>
                        )}
                        <span style={{fontFamily:'var(--f-num)', fontSize:9, color:isLast||isSel?'var(--falla-ink)':'var(--mute)'}}>{m.v}</span>
                        <div style={{width:'100%', height:h, background:isSel?'#89b4fa':isLast?'#00FF41':'#0E0E0E', borderRadius:'3px 3px 0 0', boxShadow:isSel?'0 0 8px rgba(137,180,250,.5)':isLast?'0 0 10px rgba(0,255,65,.4)':'', transition:'background .2s'}}/>
                        <span style={{fontFamily:'var(--f-sub)', fontSize:9, color:isLast||isSel?'var(--ink)':'var(--mute)', letterSpacing:'.04em', textAlign:'center'}}>{m.m}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
              {/* Fuentes */}
              <div>
                <div style={{fontFamily:'var(--f-sub)', fontSize:10, fontWeight:600, letterSpacing:'.14em', textTransform:'uppercase', color:'var(--mute)', paddingBottom:8, borderBottom:'1px solid var(--line)', marginBottom:12}}>COMPOSICIÓN DE CAJA</div>
                <div style={{display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10}}>
                  {sources.map(([l,v],i)=>(
                    <div key={i} style={{padding:'14px 16px', background:'var(--bg)', border:'1px solid var(--line)', borderRadius:'var(--r-md)'}}>
                      <div style={{fontFamily:'var(--f-sub)', fontSize:9, color:'var(--mute)', letterSpacing:'.1em', textTransform:'uppercase', marginBottom:6}}>{l}</div>
                      <div style={{fontFamily:'var(--f-num)', fontSize:22, fontWeight:700, color:'var(--ink)'}}>{v}</div>
                    </div>
                  ))}
                </div>
              </div>
              {/* Flujos con barras */}
              <div>
                <div style={{fontFamily:'var(--f-sub)', fontSize:10, fontWeight:600, letterSpacing:'.14em', textTransform:'uppercase', color:'var(--mute)', paddingBottom:8, borderBottom:'1px solid var(--line)', marginBottom:12}}>FLUJOS PRÓXIMOS 90 DÍAS</div>
                <div style={{display:'flex', flexDirection:'column', gap:8}}>
                  {risks.map(([l,v,t,f],i)=>(
                    <div key={i} style={{display:'grid', gridTemplateColumns:'1fr auto auto', gap:12, padding:'12px 14px', background:'var(--bg)', border:`1px solid ${f==='warn'?'#E8A02C':'var(--line)'}`, borderRadius:'var(--r-md)'}}>
                      <span style={{fontFamily:'var(--f-body)', fontSize:13, color:'var(--ink)', fontWeight:500}}>{l}</span>
                      <span style={{fontFamily:'var(--f-sub)', fontSize:10, color:'var(--mute)', letterSpacing:'.06em', textTransform:'uppercase', alignSelf:'center'}}>{t}</span>
                      <span style={{fontFamily:'var(--f-num)', fontSize:15, fontWeight:700, color:f==='warn'?'#f97316':'var(--falla-ink)', alignSelf:'center'}}>{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ============================================================
   APP
   ============================================================ */
function App(){
  const [theme, setTheme] = useState(()=> localStorage.getItem('cm11-theme') || 'light');
  const [period, setPeriod] = useState('Hoy');
  const [branch, setBranch] = useState(null);
  const [claw, setClaw] = useState(false);
  const [modal, setModal] = useState(null);
  const [sidebar, setSidebar] = useState(false);
  const [captura, setCaptura] = useState(false);
  const [stkModal, setStkModal] = useState(false);
  const [stkEdit, setStkEdit] = useState(null); // null or contact object for editing
  const [projects, setProjects] = useState(false);
  const [inbox, setInbox] = useState([]);
  const [contacts, setContacts] = useState([]);

  // Expose project opener for rail button
  useEffect(()=>{ window.__openProjects = ()=>setProjects(true); return ()=>{ delete window.__openProjects; }; },[]);

  useEffect(()=>{
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('cm11-theme', theme);
  },[theme]);

  // Carga bandeja de entrada desde la BD al montar
  useEffect(()=>{
    const k = window.__API_KEY__ || '';
    const b = (window.__API_BASE__ || '').replace(/\/$/,'');
    fetch(`${b}/inbox?procesado=false`, k ? {headers:{'X-API-Key':k}} : {})
      .then(r => r.ok ? r.json() : [])
      .then(list => setInbox(list.map(item=>({
        id: item.id, type: item.tipo, text: item.texto,
        date: new Date(item.created_at).toLocaleDateString('es-CO',{day:'numeric',month:'short'}),
        from: item.origen,
      }))))
      .catch(()=>{});
  },[]);

  // Carga stakeholders desde la BD al montar
  useEffect(()=>{
    const k = window.__API_KEY__ || '';
    const b = (window.__API_BASE__ || '').replace(/\/$/,'');
    fetch(`${b}/stakeholders?limit=100`, k ? {headers:{'X-API-Key':k}} : {})
      .then(r => r.ok ? r.json() : [])
      .then(list => setContacts(list.map(_adaptStk)))
      .catch(()=>{});
  },[]);

  const addCaptura = async (text) => {
    const tempId = Date.now();
    setInbox(prev => [{ id:tempId, type:'note', text, date:'Hoy', from:'Captura rápida' }, ...prev]);
    const k = window.__API_KEY__ || '';
    const b = (window.__API_BASE__ || '').replace(/\/$/,'');
    try {
      const r = await fetch(`${b}/inbox`,{
        method:'POST',
        headers:{'Content-Type':'application/json',...(k?{'X-API-Key':k}:{})},
        body:JSON.stringify({tipo:'note',texto:text,origen:'Captura rápida'}),
      });
      if(r.ok){ const s=await r.json(); setInbox(prev=>prev.map(i=>i.id===tempId?{...i,id:s.id}:i)); }
    } catch(e){}
  };
  const _adaptStk = s => ({
    id: s.id,
    name: s.nombre,
    phone: s.telefono || '',
    email: s.correo || s.email || '',
    type: s.clasificacion_negocio || s.tipo || 'Prospecto por Identificar',
    linkedin: s.linkedin_url || s.linkedin || '',
    ubicacion: s.ubicacion || '',
    rol: s.rol || '',
    observaciones: s.observaciones || '',
    activo: s.activo !== false,
  });
  const addStakeholder = async (s) => {
    const k = window.__API_KEY__ || '';
    const b = (window.__API_BASE__ || '').replace(/\/$/,'');
    const h = {'Content-Type':'application/json',...(k?{'X-API-Key':k}:{})};
    const payload = {
      nombre: s.name,
      telefono: s.phone || null,
      correo: s.email || null,
      clasificacion_negocio: s.type || 'Prospecto por Identificar',
      linkedin_url: s.linkedin || null,
      observaciones: s.observaciones || null,
      rol: s.rol || null,
      ubicacion: s.ubicacion || null,
    };
    try {
      if(stkEdit && stkEdit.id){
        const r = await fetch(`${b}/stakeholders/${stkEdit.id}`,{method:'PATCH',headers:h,body:JSON.stringify(payload)});
        if(r.ok){ const u=await r.json(); setContacts(p=>p.map(c=>c.id===stkEdit.id?_adaptStk(u):c)); }
      } else {
        const r = await fetch(`${b}/stakeholders`,{method:'POST',headers:h,body:JSON.stringify(payload)});
        if(r.ok){ const c=await r.json(); setContacts(p=>[_adaptStk(c),...p]); }
      }
    } catch(e) { console.error('Error guardando stakeholder:', e); }
  };
  const editStakeholder = (c) => { setStkEdit(c); setStkModal(true); };

  return (
    <>
      <Header theme={theme} onTheme={()=>setTheme(t=>t==='dark'?'light':'dark')} onOpenClaw={()=>setClaw(true)} onUpload={()=>setModal('dim')} onMenu={()=>setSidebar(true)}/>
      <SubHeader period={period} setPeriod={setPeriod}
        onRoadmap={()=>setModal('roadmap')} onVision={()=>setModal('vision')}/>
      <main className="wall">
        <section className="stage" data-screen-label="01 Panel General">
          <div className="stage-title">
            <div className="stage-title-row">
              <h1>Panel <em>General</em></h1>
            </div>
            <span className="stage-meta tabular">PERIODO · {period.toUpperCase()}</span>
          </div>
          <KPIs onOpen={(k)=>setModal('kpi-'+k)}/>
          <Lectura/>
          <div className="grid-2">
            <Execution/>
            <RiskMap/>
          </div>
          {branch && <Deploy branchId={branch} onClose={()=>setBranch(null)}/>}
        </section>
        <BranchRail active={branch} onPick={(id)=>setBranch(b=>b===id?null:id)}/>
      </main>

      <ClawDrawer open={claw} onClose={()=>setClaw(false)}/>

      <Modal open={modal==='roadmap'} onClose={()=>setModal(null)}
             eye="HOJA DE RUTA" title={<>Lo que viene en <em>2026</em></>}>
        <RoadmapContent/>
      </Modal>
      <Modal open={modal==='vision'} onClose={()=>setModal(null)}
             eye="VISIÓN" title={<>Hacia <em>2030</em></>}>
        <VisionContent/>
      </Modal>
      <Modal open={modal==='dim'} onClose={()=>setModal(null)}
             eye="DIMENSIÓN ESTRATÉGICA" title={<>Alimenta el <em>colectivo</em></>}>
        <DimensionContent/>
      </Modal>

      {/* KPI DETAIL MODALS */}
      <Modal open={modal==='kpi-pulso'} onClose={()=>setModal(null)} wide
             eye="PULSO DEL COLECTIVO · SALUD OPERATIVA"
             title={<>La <em>energía</em> humana del colectivo</>}>
        <PulsoDetail/>
      </Modal>
      <Modal open={modal==='kpi-vision'} onClose={()=>setModal(null)} wide
             eye="HACIA 2030 · EJECUCIÓN ESTRATÉGICA"
             title={<>Avance hacia la <em>visión</em></>}>
        <VisionDetail/>
      </Modal>
      <Modal open={modal==='kpi-caja'} onClose={()=>setModal(null)} wide
             eye="AIRE EN LA CAJA · LIQUIDEZ OPERATIVA"
             title={<>El <em>combustible</em> disponible</>}>
        <CajaDetail/>
      </Modal>

      {/* NEW v1.4 components */}
      {!claw && <window.FAB onCaptura={()=>setCaptura(true)} onStakeholder={()=>{setStkEdit(null); setStkModal(true);}}/>}
      <window.CapturaModal open={captura} onClose={()=>setCaptura(false)} onSave={addCaptura}/>
      <window.StakeholderModal open={stkModal} onClose={()=>{setStkModal(false); setStkEdit(null);}} onSave={addStakeholder} editData={stkEdit}/>
      <window.Sidebar open={sidebar} onClose={()=>setSidebar(false)} inbox={inbox} setInbox={setInbox} contacts={contacts} setContacts={setContacts} onEditStakeholder={editStakeholder}/>
      <window.ProjectsDashboard open={projects} onClose={()=>setProjects(false)}/>
    </>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
