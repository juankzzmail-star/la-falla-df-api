/* api-client.js — Centro de Mando v1.4 · carga datos reales del backend */
(function () {
  'use strict';

  var BASE = window.__API_BASE__ || '/api';

  // fix-403-race: v14-app hace fetches con X-API-Key leyendo window.__API_KEY__; esos useEffect pueden
  // correr ANTES de que loadAll() resuelva /config y setee la key -> 403 (directorio/bandeja vacíos).
  // Exponemos una promesa que resuelve cuando la key está lista (o '' en modo demo): los fetches la
  // esperan en lugar de disparar sin key. api-client.js corre antes que los <script type=text/babel>,
  // así que __CM_KEY_READY__ existe siempre antes de que v14-app monte.
  var _keyReadyResolve;
  window.__CM_KEY_READY__ = new Promise(function (res) { _keyReadyResolve = res; });

  var MONTH_ABBR = ['E','F','M','A','M','J','J','A','S','O','N','D'];
  // 3-letter + full month names: la inicial sola (A=¿Abril/Agosto?, M=¿Marzo/Mayo?) es ambigua
  var MONTH_3 = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
  var MONTH_FULL = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];

  var STATUS_MAP = { done:'done', in_progress:'prog', delayed:'late', pendiente:'' };

  // Códigos de Dirección (NO Gerencia): DC=Comercial, DP=Proyectos, DI=Investigación, DA=Audiovisual.
  var AREA_LABEL = {
    Comercial:    'DC · Comercial',
    Proyectos:    'DP · Proyectos',
    Investigacion:'DI · Investig.',
    Audiovisual:  'DA · Audiovisual',
  };

  function notify() {
    (window.__CM_LISTENERS__ || []).forEach(function(fn){ try { fn(); } catch(e){} });
  }

  function toCell(v) {
    if (v <= 1) return 0;
    if (v <= 2) return 1;
    if (v <= 3) return 2;
    return 3;
  }

  function transformRisks(raw) {
    var list = Array.isArray(raw) ? raw : (raw && raw.risks) ? raw.risks : [];
    return list.map(function(r) {
      var nr = r.nivel_riesgo != null ? r.nivel_riesgo : (r.impacto * r.probabilidad);
      return {
        id: r.id,
        x: toCell(r.probabilidad),
        y: toCell(r.impacto),
        c: nr >= 16 ? 'high' : nr >= 6 ? 'med' : 'low',
        t: r.descripcion,
        // Gentil's deep-brain analysis (ddl_v14) — feeds the existing RiskModal slots, no layout change.
        gentil_analysis: r.analisis_gentil || null,
        plan_mitigacion: Array.isArray(r.plan_mitigacion) ? r.plan_mitigacion : [],
      };
    });
  }

  function transformMilestones(raw) {
    var list = Array.isArray(raw) ? raw : (raw && raw.milestones) ? raw.milestones : [];
    return list
      .slice()
      .sort(function(a, b){ return (a.orden||0) - (b.orden||0); })
      .map(function(m){ return {
        id: m.id,
        s: STATUS_MAP[m.estado] != null ? STATUS_MAP[m.estado] : '',
        t: m.titulo,
        estado: m.estado,
        // change connect-execution-strategy: ONE coherent avance (done=100, pendiente=0, en progreso=
        // roll-up real) so el modal deja de pelearse con el radial. Fallback a pct_completado para
        // payloads viejos; null -> "sin datos" (nunca un 0 inventado).
        pct: m.avance != null ? Number(m.avance)
             : (m.pct_completado != null ? Number(m.pct_completado) : null),
        sinRespaldo: !!m.sin_respaldo,   // 'terminado' sin evidencia suficiente -> "verificar respaldo"
        // change connect-execution-strategy: tareas reales que avanzan el hito (vinculadas) y cuántas hechas
        tareasTotal: m.tareas_total != null ? Number(m.tareas_total) : 0,
        tareasDone: m.tareas_done != null ? Number(m.tareas_done) : 0,
        peso: m.peso != null ? Number(m.peso) : 1,   // change rigorous-progress-math: tier estratégico del hito
        anio: m.anio != null ? m.anio : null,
      }; });
  }

  function transformHeatmap(raw) {
    if (!raw || !raw.areas) return null;
    return {
      rows: raw.areas.map(function(a) {
        return {
          area: AREA_LABEL[a.name] || a.name,
          code: a.code,
          values: (a.days || []).slice(0, 7),
          score: a.score != null ? a.score : null,   // change rigorous-progress-math: continuo 0–100 (no banda)
          nivel: a.nivel || 0,
          total: a.total || 0,
          pendiente: a.pendiente || 0,
          overdue: a.overdue || 0,
          // change rigorous-progress-math: desglose del índice compuesto para el cajón de detalle
          onTimePct: a.on_time_pct != null ? a.on_time_pct : null,   // puntualidad histórica
          backlogSev: a.backlog_sev != null ? a.backlog_sev : null,  // severidad del backlog vencido (0–100)
          wTotal: a.w_total != null ? a.w_total : 0,                 // carga ponderada (size-weighting)
          // change period-aware-pulso: per-horizon score/load (hoy/semana/mensual) for the toggle
          periodo: a.periodo || null,
        };
      }),
      salud_global: raw.salud_global || 0,
      salud_global_simple: raw.salud_global_simple != null ? raw.salud_global_simple : null,  // baseline equal
      salud_global_periodo: raw.salud_global_periodo || null,
    };
  }

  function transformFinancial(raw) {
    if (!raw) return null;
    var snaps = (raw.snapshots || []).slice(-12);
    // change real-financial-source: las barras grafican la CAJA real del banco (saldo BCS de cierre de
    // mes), NO liquidez_total — el respaldo de crédito del fundador fluye por la misma cuenta, así que
    // sumarlo duplicaría el dinero. El crédito vive aparte (composición + runway "con crédito").
    var months = snaps.map(function(s) {
      var d = new Date((s.fecha || '').replace(' ', 'T') + (s.fecha && s.fecha.length === 10 ? 'T00:00:00' : ''));
      var abbr = isNaN(d.getTime()) ? '?' : MONTH_3[d.getMonth()];
      return [abbr, +((s.caja_operativa || 0) / 1000000).toFixed(1)];
    });
    // When fewer than 2 real snapshots exist, generate a 12-month forward runway projection so
    // CajaViz has enough points to render. The projection burns caja_operativa at gasto_mensual_promedio
    // per month — it shows the CEO visually when cash hits zero at the current burn rate.
    if (months.length < 2 && raw.latest && (raw.latest.gasto_mensual_promedio || 0) > 0) {
      var _cajaM  = +((raw.latest.caja_operativa || 0) / 1000000).toFixed(1);
      var _gastoM = +((raw.latest.gasto_mensual_promedio || 0) / 1000000).toFixed(1);
      var _baseSnap = snaps.length > 0 ? snaps[snaps.length - 1] : null;
      var _baseDate = _baseSnap && _baseSnap.fecha
        ? new Date(_baseSnap.fecha.length === 10 ? _baseSnap.fecha + 'T00:00:00' : _baseSnap.fecha)
        : new Date();
      months = [];
      for (var _i = 0; _i < 12; _i++) {
        var _d2 = new Date(_baseDate.getFullYear(), _baseDate.getMonth() + _i, 1);
        var _v = Math.max(0, +(_cajaM - _gastoM * _i).toFixed(1));
        months.push([MONTH_3[_d2.getMonth()], _v]);
        if (_v === 0) break;
      }
    }
    // detalle real por mes para el tooltip (composición + Δ caja mes a mes). NO se re-inventan
    // ingresos/egresos (se borraron a propósito por ser ficción); solo datos derivados reales.
    var monthsDetail = snaps.map(function(s, i) {
      var d = new Date((s.fecha || '').replace(' ', 'T') + (s.fecha && s.fecha.length === 10 ? 'T00:00:00' : ''));
      var mi = isNaN(d.getTime()) ? -1 : d.getMonth();
      var cajaM = +((s.caja_operativa || 0) / 1000000).toFixed(1);
      var prev = i > 0 ? +((snaps[i - 1].caja_operativa || 0) / 1000000).toFixed(1) : null;
      return {
        m: mi >= 0 ? MONTH_3[mi] : '?',
        full: mi >= 0 ? (MONTH_FULL[mi] + (isNaN(d.getFullYear()) ? '' : ' ' + d.getFullYear())) : '?',
        v: cajaM,
        caja:     cajaM,
        reservas: +((s.reservas_estrategicas || 0) / 1000000).toFixed(1),
        credito:  +((s.credito_disponible || 0) / 1000000).toFixed(1),
        meses:    s.meses_respiracion != null ? s.meses_respiracion : null,
        delta:    prev != null ? +(cajaM - prev).toFixed(1) : null,   // Δ caja vs mes previo (real)
      };
    });
    var latest = raw.latest || snaps[snaps.length - 1] || {};
    // change caja-freshness-honesty (AUD-039): expose the data's as-of date + staleness so the card can be
    // honest that the book's latest month may lag the sync. as-of = the latest snapshot's date (not the sync time).
    var lastSnap = snaps[snaps.length - 1] || {};
    var fechaStr = lastSnap.fecha || null;
    var asOf = null, stale = false;
    if (fechaStr) {
      var _d = new Date(fechaStr.length === 10 ? fechaStr + 'T00:00:00' : fechaStr);
      if (!isNaN(_d.getTime())) {
        var _M = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
        asOf = _d.getDate() + ' ' + _M[_d.getMonth()] + ' ' + _d.getFullYear();
        stale = (Date.now() - _d.getTime()) > 45 * 24 * 3600 * 1000;
      }
    }
    return {
      months: months,
      monthsDetail: monthsDetail,
      mesesCount: months.length,
      latest: {
        total:    +((latest.caja_operativa      || 0) / 1000000).toFixed(1),
        meses:    latest.meses_respiracion || 0,
        fecha:    fechaStr,
        asOf:     asOf,
        stale:    stale,
        caja:     +((latest.caja_operativa          || 0) / 1000000).toFixed(1),
        reservas: +((latest.reservas_estrategicas   || 0) / 1000000).toFixed(1),
        credito:  +((latest.credito_disponible      || 0) / 1000000).toFixed(1),
        // change rigorous-progress-math: cash runway (caja+reservas, lo que de verdad tienes) vs funded
        // runway (+crédito, colchón contingente). Cada uno con su semáforo (rojo/ambar/ok/verde).
        cashRunway:   latest.cash_runway_meses != null ? latest.cash_runway_meses : null,
        fundedRunway: latest.funded_runway_meses != null ? latest.funded_runway_meses : null,
        cashRag:      latest.cash_runway_rag || null,
        fundedRag:    latest.funded_runway_rag || null,
      },
      flows: raw.flows || [],
      // change real-financial-source: doc real (MOVIMIENTOS 2026, Dir. Comercial y Financiero) para el
      // botón Ver / Descargar (.xlsx). Sin spreadsheet_id -> los botones no se pintan.
      source: raw.source || null,
    };
  }

  function transformSuggestions(raw) {
    var list = Array.isArray(raw) ? raw : (raw && raw.suggestions) ? raw.suggestions : [];
    var items = list
      .filter(function(s){ return s.estado === 'pendiente'; })
      .map(function(s){ return { id: String(s.id), tag: s.tag, title: s.titulo, body: s.cuerpo }; });
    // generatedToday = filas totales de HOY (cualquier estado). Distingue "todo resuelto" (>0 y 0 pendientes)
    // de "el motor no corrió hoy" (0 filas) — para que el empty-state no mienta.
    return { items: items, generatedToday: list.length };
  }

  function transformArcs(raw) {
    if (!raw || !raw.arcs) return null;
    var arr = raw.arcs;
    // change relabel-avance-2030 (AUD-024): surface the real counts ON the arcs array (it stays an array,
    // so existing arcs.find(...) / RadialViz consumers are unaffected) for an honest KPI subtitle.
    arr.done = raw.done != null ? raw.done : null;
    arr.total = raw.total_milestones != null ? raw.total_milestones : null;
    arr.sinRespaldo = raw.sin_respaldo != null ? raw.sin_respaldo : 0;
    return arr;
  }

  // change plan-quarterly-milestones: per-quarter roadmap sourced from the PLANS' quarterly goals
  // (the quarter lives on the plan, not the hito). Pass-through of
  // {anio, total, quarters:[{trimestre, items:[{plan_id, area, meta, objetivo_medible, pct}]}]}.
  function transformQuarters(raw) {
    if (!raw || !raw.quarters) return null;
    return raw;
  }

  function transformOportunidades(raw) {
    var list = Array.isArray(raw) ? raw : [];
    return list.map(function(o) {
      return {
        id: o.id,
        rec: o.airtable_record_id || '',
        nombre: o.nombre,
        entidad: o.entidad || o.programa || '',
        adn: o.adn_score,
        prioridad: o.prioridad || '',
        cierre: o.fecha_cierre || '',
        url: o.url_convocatoria || '',
        estado: o.estado_seguimiento || 'nueva',
      };
    });
  }

  async function loadAll() {
    var apiKey = '';
    try {
      var cfg = await fetch('/config').then(function(r){ return r.json(); });
      apiKey = cfg.apiKey || '';
      window.__API_KEY__ = apiKey;
      window.__API_BASE__ = cfg.apiBase || '/api';
      _keyReadyResolve(apiKey);            // key lista -> los fetches de v14-app pueden disparar
    } catch(e) {
      console.warn('[CM] /config no disponible — modo demo activo');
      _keyReadyResolve('');                // modo demo: resuelve vacío para no colgar a los que esperan
      return;
    }

    if (!apiKey) {
      console.warn('[CM] Sin API key — modo demo activo');
      return;
    }

    var H = { 'X-API-Key': apiKey };

    // change plan-quarterly-milestones: anchor the roadmap year to the ACTIVE cycle, not the browser
    // clock (kills the latent 2027 empty-dashboard bug). No active cycle -> no year guess (honest empty).
    var cycle = await fetch(BASE + '/roadmap/active-cycle', { headers: H })
      .then(function(r){ return r.ok ? r.json() : null; })
      .catch(function(){ return null; });
    var roadmapAnio = (cycle && cycle.anio) || null;
    window.__CM_ROADMAP_ANIO__ = roadmapAnio;

    var endpoints = {
      heatmap:     BASE + '/dashboard/health-heatmap',
      roadmap2030: BASE + '/dashboard/roadmap-2030',
      financial:   BASE + '/dashboard/financial-snapshots',
      suggestions: BASE + '/dashboard/suggestions',
      milestones:  BASE + '/roadmap/milestones',
      risks:          BASE + '/risks',
      health:         BASE + '/dashboard/health/services',
      executive_feed: BASE + '/dashboard/openclaw-executive-feed',
      oportunidades:  BASE + '/oportunidades?limit=50',
      // change rebuild-onboarding-hub: the completeness interview drives the OnboardingHub cards +
      // the InterviewBanner. This key was never fetched, so useApiData('interview') was always null
      // and the whole interview UI was dead code in the browser.
      interview:      BASE + '/interview',
    };
    // Only fetch the per-quarter roadmap when there is an active cycle year to anchor to.
    if (roadmapAnio) {
      endpoints.quarters = BASE + '/roadmap/quarters?anio=' + roadmapAnio;
    }

    var fetches = Object.entries(endpoints).map(function([k, url]) {
      return fetch(url, { headers: H })
        .then(function(r) {
          if (!r.ok) throw new Error(r.status);
          return r.json();
        })
        .then(function(d) { return [k, d]; })
        .catch(function(e) {
          console.warn('[CM]', k, 'falló:', e.message);
          return [k, null];
        });
    });

    var results = await Promise.all(fetches);
    var raw = {};
    results.forEach(function([k, d]) { if (d !== null) raw[k] = d; });

    window.__CM_DATA__ = {
      pulso:       transformHeatmap(raw.heatmap),
      arcs:        transformArcs(raw.roadmap2030),
      caja:        transformFinancial(raw.financial),
      suggestions: raw.suggestions != null ? transformSuggestions(raw.suggestions) : null,
      milestones:  raw.milestones  != null ? transformMilestones(raw.milestones)  : null,
      quarters:    raw.quarters    != null ? transformQuarters(raw.quarters)      : null,
      roadmapAnio: roadmapAnio,
      risks:       raw.risks       != null ? transformRisks(raw.risks)            : null,
      health:         raw.health         != null ? raw.health         : null,
      executive_feed: raw.executive_feed != null ? raw.executive_feed : null,
      oportunidades:  raw.oportunidades  != null ? transformOportunidades(raw.oportunidades) : null,
      interview:      raw.interview      != null ? raw.interview      : null,
    };

    notify();
  }

  window.__CM_REFRESH__ = loadAll;
  loadAll();
})();
