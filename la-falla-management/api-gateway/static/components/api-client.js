/* api-client.js — Centro de Mando v1.4 · carga datos reales del backend */
(function () {
  'use strict';

  var BASE = window.__API_BASE__ || '/api';

  var MONTH_ABBR = ['E','F','M','A','M','J','J','A','S','O','N','D'];

  var STATUS_MAP = { done:'done', in_progress:'prog', delayed:'late', pendiente:'' };

  var AREA_LABEL = {
    Comercial:    'GCF · Comercial',
    Proyectos:    'GP  · Proyectos',
    Investigacion:'GI  · Investig.',
    Audiovisual:  'GA  · Audiovisual',
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
        x: toCell(r.probabilidad),
        y: toCell(r.impacto),
        c: nr >= 16 ? 'high' : nr >= 6 ? 'med' : 'low',
        t: r.descripcion,
      };
    });
  }

  function transformMilestones(raw) {
    var list = Array.isArray(raw) ? raw : (raw && raw.milestones) ? raw.milestones : [];
    return list
      .slice()
      .sort(function(a, b){ return (a.orden||0) - (b.orden||0); })
      .map(function(m){ return { s: STATUS_MAP[m.estado] != null ? STATUS_MAP[m.estado] : '', t: m.titulo }; });
  }

  function transformHeatmap(raw) {
    if (!raw || !raw.areas) return null;
    return {
      rows: raw.areas.map(function(a) {
        return {
          area: AREA_LABEL[a.name] || a.name,
          values: (a.days || []).slice(0, 7),
          score: a.score || 0,
        };
      }),
      salud_global: raw.salud_global || 0,
      delta: raw.delta || 0,
    };
  }

  function transformFinancial(raw) {
    if (!raw) return null;
    var snaps = (raw.snapshots || []).slice(-12);
    var months = snaps.map(function(s) {
      var d = new Date((s.fecha || '').replace(' ', 'T') + (s.fecha && s.fecha.length === 10 ? 'T00:00:00' : ''));
      var abbr = isNaN(d.getTime()) ? '?' : MONTH_ABBR[d.getMonth()];
      return [abbr, +((s.liquidez_total || 0) / 1000000).toFixed(1)];
    });
    var latest = raw.latest || snaps[snaps.length - 1] || {};
    return {
      months: months,
      latest: {
        total:    +((latest.liquidez_total      || 0) / 1000000).toFixed(1),
        meses:    latest.meses_respiracion || 0,
        caja:     +((latest.caja_operativa          || 0) / 1000000).toFixed(1),
        reservas: +((latest.reservas_estrategicas   || 0) / 1000000).toFixed(1),
        credito:  +((latest.credito_disponible      || 0) / 1000000).toFixed(1),
      },
      flows: raw.flows || [],
    };
  }

  function transformSuggestions(raw) {
    var list = Array.isArray(raw) ? raw : (raw && raw.suggestions) ? raw.suggestions : [];
    return list
      .filter(function(s){ return s.estado === 'pendiente'; })
      .map(function(s){ return { id: String(s.id), tag: s.tag, title: s.titulo, body: s.cuerpo }; });
  }

  function transformArcs(raw) {
    if (!raw || !raw.arcs) return null;
    return raw.arcs;
  }

  async function loadAll() {
    var apiKey = '';
    try {
      var cfg = await fetch('/config').then(function(r){ return r.json(); });
      apiKey = cfg.apiKey || '';
      window.__API_KEY__ = apiKey;
      window.__API_BASE__ = cfg.apiBase || '/api';
    } catch(e) {
      console.warn('[CM] /config no disponible — modo demo activo');
      return;
    }

    if (!apiKey) {
      console.warn('[CM] Sin API key — modo demo activo');
      return;
    }

    var H = { 'X-API-Key': apiKey };

    var endpoints = {
      heatmap:     BASE + '/dashboard/health-heatmap',
      roadmap2030: BASE + '/dashboard/roadmap-2030',
      financial:   BASE + '/dashboard/financial-snapshots',
      suggestions: BASE + '/dashboard/suggestions',
      milestones:  BASE + '/roadmap/milestones',
      risks:          BASE + '/risks',
      health:         BASE + '/dashboard/health/services',
      executive_feed: BASE + '/dashboard/openclaw-executive-feed',
    };

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
      risks:       raw.risks       != null ? transformRisks(raw.risks)            : null,
      health:         raw.health         != null ? raw.health         : null,
      executive_feed: raw.executive_feed != null ? raw.executive_feed : null,
    };

    notify();
  }

  window.__CM_REFRESH__ = loadAll;
  loadAll();
})();
