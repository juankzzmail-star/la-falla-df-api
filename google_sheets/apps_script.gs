/**
 * ============================================================================
 *  Stakeholders La Falla DF — Apps Script (v2: headers dinámicos + extras)
 * ============================================================================
 *  Sincroniza la hoja "Stakeholders" con la API FastAPI (api-stakeholders)
 *  que corre en EasyPanel, la cual a su vez escribe en Postgres.
 *
 *  Flujo:
 *    Edición manual en el Sheet  →  onEdit()  →  PATCH/POST a FastAPI
 *    Cron cada 5 min             →  refreshFromPostgres()  →  pull completo
 *    Menú "La Falla DF"          →  hard delete / activar / desactivar
 *
 *  COLUMNAS DINÁMICAS:
 *    La fila 1 del Sheet es la fuente de verdad para los nombres de columna.
 *    · Cabeceras que coincidan con columnas reales de Postgres (BASE_COLS)
 *      se mapean a sus campos directos.
 *    · Cualquier cabecera desconocida se guarda en el campo JSONB `extras`
 *      sin tocar el esquema. Así cualquiera puede agregar una columna
 *      nueva en el Sheet y su valor queda persistido en Postgres.
 *
 *  SETUP (una sola vez):
 *    1) Tab llamado "Stakeholders". Fila 1 con nombres de columna.
 *       Base mínima recomendada:
 *         id | nombre | rol | correo | telefono | ubicacion | direccion |
 *         clasificacion_negocio | observaciones | observaciones_post_contacto |
 *         servicios | linkedin_url | activo | fecha_actualizacion
 *       Puedes agregar columnas libres (ej. "prioridad", "nota_interna").
 *    2) Extensiones → Apps Script → pegar este archivo completo.
 *    3) Proyecto → Configuración → Propiedades del script:
 *         API_BASE_URL = https://<tu-api-stakeholders>.easypanel.host
 *         API_KEY      = <misma FASTAPI_API_KEY del servidor>
 *    4) Correr setupTriggers() una vez (autoriza permisos).
 *    5) Correr refreshFromPostgres() para poblar.
 * ============================================================================
 */

const SHEET_NAME = 'Stakeholders';

// Columnas que existen como columna real en Postgres `stakeholders_master`.
// Todo lo que NO esté aquí se rutea al JSONB `extras` automáticamente.
const BASE_COLS = [
  'id', 'nombre', 'rol', 'correo', 'telefono', 'ubicacion', 'direccion',
  'nit', 'observaciones', 'observaciones_post_contacto', 'servicios',
  'redes', 'quien_contacta', 'clasificacion', 'clasificacion_negocio',
  'linkedin_url', 'fuente_archivo', 'fuente_hoja', 'activo',
  'fecha_carga', 'fecha_actualizacion'
];
const BASE_SET = new Set(BASE_COLS);

// Columnas calculadas o manejadas por el servidor — no se envían en edits.
const SERVER_MANAGED = new Set([
  'id', 'fecha_carga', 'fecha_actualizacion', 'clasificacion'
]);

function _props() { return PropertiesService.getScriptProperties(); }
function _sheet() { return SpreadsheetApp.getActive().getSheetByName(SHEET_NAME); }

function _headers(sheet) {
  const lastCol = sheet.getLastColumn();
  if (lastCol < 1) return [];
  return sheet.getRange(1, 1, 1, lastCol).getValues()[0].map((h) => String(h || '').trim());
}

function _indexOf(headers, name) {
  for (let i = 0; i < headers.length; i++) if (headers[i] === name) return i;
  return -1;
}

function _apiCall(method, path, payload) {
  const base = _props().getProperty('API_BASE_URL');
  const key  = _props().getProperty('API_KEY');
  if (!base || !key) throw new Error('Faltan Script Properties API_BASE_URL / API_KEY');

  const options = {
    method: method,
    headers: { 'X-API-Key': key, 'Content-Type': 'application/json' },
    muteHttpExceptions: true,
  };
  if (payload) options.payload = JSON.stringify(payload);

  const resp = UrlFetchApp.fetch(base + path, options);
  const code = resp.getResponseCode();
  if (code >= 400) throw new Error(`API ${method} ${path} → ${code}: ${resp.getContentText()}`);
  return JSON.parse(resp.getContentText() || '{}');
}

function _normalize(h, v) {
  // Normaliza tipos para que Postgres reciba lo esperado
  if (v === '' || v === null || v === undefined) return null;
  if (h === 'activo') {
    if (typeof v === 'boolean') return v;
    const s = String(v).trim().toUpperCase();
    return s === 'TRUE' || s === 'VERDADERO' || s === '1' || s === 'SI' || s === 'SÍ';
  }
  if (h === 'telefono') return String(v);
  return v;
}

function _buildPayload(headers, rowValues) {
  const payload = {};
  const extras = {};
  for (let i = 0; i < headers.length; i++) {
    const h = headers[i];
    if (!h || SERVER_MANAGED.has(h)) continue;
    const v = _normalize(h, rowValues[i]);
    if (BASE_SET.has(h)) {
      payload[h] = v;
    } else {
      extras[h] = v;
    }
  }
  payload.extras = extras;
  return payload;
}

function _rowFromApi(headers, obj) {
  const extras = obj.extras || {};
  return headers.map((h) => {
    if (!h) return '';
    if (BASE_SET.has(h)) return (obj[h] !== undefined && obj[h] !== null) ? obj[h] : '';
    return (extras[h] !== undefined && extras[h] !== null) ? extras[h] : '';
  });
}

// ----------------------------------------------------------------------------
//  Menú
// ----------------------------------------------------------------------------
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('La Falla DF')
    .addItem('Refrescar desde Postgres', 'refreshFromPostgres')
    .addSeparator()
    .addItem('Eliminar fila seleccionada (hard delete)', 'deleteSelectedRow')
    .addItem('Desactivar fila seleccionada', 'deactivateSelectedRow')
    .addItem('Activar fila seleccionada', 'activateSelectedRow')
    .addSeparator()
    .addItem('(Setup) Crear triggers', 'setupTriggers')
    .addToUi();
}

// ----------------------------------------------------------------------------
//  Trigger installable: cualquier edición de usuario
// ----------------------------------------------------------------------------
function onEditInstallable(e) {
  if (_props().getProperty('SYNC_IN_PROGRESS') === 'true') return;

  const sheet = e.range.getSheet();
  if (sheet.getName() !== SHEET_NAME) return;

  const row = e.range.getRow();
  if (row === 1) return;

  const headers = _headers(sheet);
  if (!headers.length) return;

  const editedCol = e.range.getColumn();
  const editedHeader = headers[editedCol - 1];
  // Ignorar ediciones en columnas server-managed (evita loops)
  if (SERVER_MANAGED.has(editedHeader)) return;

  const rowValues = sheet.getRange(row, 1, 1, headers.length).getValues()[0];
  const idIdx = _indexOf(headers, 'id');
  const nombreIdx = _indexOf(headers, 'nombre');
  const id = idIdx >= 0 ? rowValues[idIdx] : '';
  const nombre = nombreIdx >= 0 ? String(rowValues[nombreIdx] || '').trim() : '';

  try {
    let updated;
    if (!id) {
      if (!nombre) return;
      const payload = _buildPayload(headers, rowValues);
      if (!payload.fuente_archivo) payload.fuente_archivo = 'Google Sheets';
      updated = _apiCall('POST', '/stakeholders', payload);
    } else {
      const payload = _buildPayload(headers, rowValues);
      updated = _apiCall('PATCH', '/stakeholders/' + id, payload);
    }
    _writeRow(sheet, row, headers, updated);
  } catch (err) {
    const fechaIdx = _indexOf(headers, 'fecha_actualizacion');
    const noteCol = (fechaIdx >= 0 ? fechaIdx : 0) + 1;
    sheet.getRange(row, noteCol).setNote('Error sync: ' + err.message);
  }
}

function _writeRow(sheet, row, headers, obj) {
  _props().setProperty('SYNC_IN_PROGRESS', 'true');
  try {
    const values = _rowFromApi(headers, obj);
    sheet.getRange(row, 1, 1, headers.length).setValues([values]);
    const fechaIdx = _indexOf(headers, 'fecha_actualizacion');
    if (fechaIdx >= 0) sheet.getRange(row, fechaIdx + 1).clearNote();
  } finally {
    _props().deleteProperty('SYNC_IN_PROGRESS');
  }
}

// ----------------------------------------------------------------------------
//  Trigger onChange: protege contra borrado manual de filas
//  (click-derecho → Eliminar fila NO dispara onEdit; usamos onChange)
// ----------------------------------------------------------------------------
function onChangeInstallable(e) {
  if (_props().getProperty('SYNC_IN_PROGRESS') === 'true') return;
  if (!e || e.changeType !== 'REMOVE_ROW') return;

  refreshFromPostgres();
  try {
    SpreadsheetApp.getUi().alert(
      'Protección de datos',
      'Detecté eliminación manual de fila(s). Restauré desde Postgres.\n\n' +
      'Para eliminar de verdad: menú "La Falla DF → Eliminar fila seleccionada".\n' +
      'Para dejar de contactar: menú "La Falla DF → Desactivar fila seleccionada".',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
  } catch (_) { /* sin UI en ejecuciones de cron */ }
}

// ----------------------------------------------------------------------------
//  Pull completo desde Postgres (cron + manual)
// ----------------------------------------------------------------------------
function refreshFromPostgres() {
  _props().setProperty('SYNC_IN_PROGRESS', 'true');
  try {
    const rows = _apiCall('GET', '/stakeholders?incluir_inactivos=true&limit=10000');
    const sheet = _sheet();
    const headers = _headers(sheet);
    if (!headers.length) return;

    const lastRow = sheet.getLastRow();

    // Preservar filas pendientes: sin id pero con nombre (POST en curso o falló)
    const pending = [];
    if (lastRow > 1) {
      const existing = sheet.getRange(2, 1, lastRow - 1, headers.length).getValues();
      const idIdx = _indexOf(headers, 'id');
      const nombreIdx = _indexOf(headers, 'nombre');
      existing.forEach((r) => {
        const hasId = idIdx >= 0 && r[idIdx] !== '' && r[idIdx] !== null && r[idIdx] !== undefined;
        const hasNombre = nombreIdx >= 0 && String(r[nombreIdx] || '').trim() !== '';
        if (!hasId && hasNombre) pending.push(r);
      });
      sheet.getRange(2, 1, lastRow - 1, headers.length).clearContent();
    }

    const fromDb = rows.map((r) => _rowFromApi(headers, r));
    const all = fromDb.concat(pending);
    if (!all.length) return;

    sheet.getRange(2, 1, all.length, headers.length).setValues(all);
  } finally {
    _props().deleteProperty('SYNC_IN_PROGRESS');
  }
}

// ----------------------------------------------------------------------------
//  Acciones de menú
// ----------------------------------------------------------------------------
function deleteSelectedRow() {
  const sheet = _sheet();
  const row = sheet.getActiveRange().getRow();
  if (row === 1) { SpreadsheetApp.getUi().alert('Selecciona una fila de datos.'); return; }

  const headers = _headers(sheet);
  const idIdx = _indexOf(headers, 'id');
  const nombreIdx = _indexOf(headers, 'nombre');
  if (idIdx < 0) { SpreadsheetApp.getUi().alert('No encuentro la columna "id".'); return; }

  const id = sheet.getRange(row, idIdx + 1).getValue();
  const nombre = nombreIdx >= 0 ? sheet.getRange(row, nombreIdx + 1).getValue() : '';
  if (!id) { sheet.deleteRow(row); return; }

  const ui = SpreadsheetApp.getUi();
  const resp = ui.alert(
    'Eliminación permanente',
    `¿Eliminar DEFINITIVAMENTE a "${nombre}" (id=${id}) de Postgres?\n\n` +
    `Esta acción NO se puede deshacer. Si solo quieres dejar de contactarlo, ` +
    `usa "Desactivar" en su lugar.`,
    ui.ButtonSet.YES_NO
  );
  if (resp !== ui.Button.YES) return;

  _apiCall('DELETE', '/stakeholders/' + id);
  sheet.deleteRow(row);
}

function deactivateSelectedRow() {
  const sheet = _sheet();
  const row = sheet.getActiveRange().getRow();
  if (row === 1) return;
  const headers = _headers(sheet);
  const idIdx = _indexOf(headers, 'id');
  if (idIdx < 0) return;
  const id = sheet.getRange(row, idIdx + 1).getValue();
  if (!id) return;
  const updated = _apiCall('POST', '/stakeholders/' + id + '/deactivate');
  _writeRow(sheet, row, headers, updated);
}

function activateSelectedRow() {
  const sheet = _sheet();
  const row = sheet.getActiveRange().getRow();
  if (row === 1) return;
  const headers = _headers(sheet);
  const idIdx = _indexOf(headers, 'id');
  if (idIdx < 0) return;
  const id = sheet.getRange(row, idIdx + 1).getValue();
  if (!id) return;
  const updated = _apiCall('POST', '/stakeholders/' + id + '/activate');
  _writeRow(sheet, row, headers, updated);
}

// ----------------------------------------------------------------------------
//  Setup: corre una sola vez para crear triggers
// ----------------------------------------------------------------------------
function setupTriggers() {
  const triggers = ScriptApp.getProjectTriggers();
  triggers.forEach((t) => {
    const fn = t.getHandlerFunction();
    if (fn === 'onEditInstallable' || fn === 'onChangeInstallable' || fn === 'refreshFromPostgres') {
      ScriptApp.deleteTrigger(t);
    }
  });

  ScriptApp.newTrigger('onEditInstallable')
    .forSpreadsheet(SpreadsheetApp.getActive())
    .onEdit()
    .create();

  ScriptApp.newTrigger('onChangeInstallable')
    .forSpreadsheet(SpreadsheetApp.getActive())
    .onChange()
    .create();

  ScriptApp.newTrigger('refreshFromPostgres')
    .timeBased()
    .everyMinutes(5)
    .create();

  SpreadsheetApp.getUi().alert('Triggers creados: onEdit + onChange (protección) + refresh cada 5 min.');
}
