/**
 * ============================================================================
 *  Stakeholders La Falla DF — Apps Script
 * ============================================================================
 *  Sincroniza la hoja "Stakeholders" con la API FastAPI (api-stakeholders)
 *  que corre en EasyPanel, la cual a su vez escribe en Postgres.
 *
 *  Flujo:
 *    Edición manual en el Sheet  →  onEdit()  →  PATCH/POST a FastAPI
 *    Cron cada 5 min             →  refreshFromPostgres()  →  pull completo
 *    Menú "La Falla DF"          →  hard delete / activar / desactivar
 *
 *  SETUP (una sola vez):
 *    1) En la hoja, tab llamado "Stakeholders" con esta fila 1 (encabezados):
 *         id | nombre | rol | correo | telefono | ubicacion | direccion |
 *         clasificacion_negocio | observaciones | servicios | linkedin_url |
 *         activo | fecha_actualizacion
 *    2) Extensiones → Apps Script → pegar este archivo completo.
 *    3) Proyecto → Configuración → Propiedades del script → agregar:
 *         API_BASE_URL = https://<tu-api-stakeholders>.easypanel.host
 *         API_KEY      = <misma FASTAPI_API_KEY que pusiste en EasyPanel>
 *    4) Correr una vez setupTriggers() desde el editor (autoriza permisos).
 *       Eso crea:
 *         - onEditInstallable  → dispara en cada edit
 *         - refreshFromPostgres → cada 5 min
 *    5) Correr refreshFromPostgres() manualmente la primera vez para poblar.
 * ============================================================================
 */

const SHEET_NAME = 'Stakeholders';
const COLUMNS = [
  'id', 'nombre', 'rol', 'correo', 'telefono', 'ubicacion',
  'direccion', 'clasificacion_negocio', 'observaciones', 'servicios',
  'linkedin_url', 'activo', 'fecha_actualizacion'
];
const ID_COL = 1;
const ACTIVO_COL = 12;
const FECHA_ACT_COL = 13;

function _props() { return PropertiesService.getScriptProperties(); }
function _sheet() { return SpreadsheetApp.getActive().getSheetByName(SHEET_NAME); }

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

  const col = e.range.getColumn();
  if (col < 2 || col > ACTIVO_COL) return;

  const rowValues = sheet.getRange(row, 1, 1, COLUMNS.length).getValues()[0];
  const rowObj = {};
  COLUMNS.forEach((k, i) => { rowObj[k] = rowValues[i]; });
  const id = rowObj.id;

  try {
    if (!id) {
      if (!rowObj.nombre) return;
      const created = _apiCall('POST', '/stakeholders', {
        nombre: rowObj.nombre, rol: rowObj.rol, correo: rowObj.correo,
        telefono: String(rowObj.telefono || ''), ubicacion: rowObj.ubicacion,
        direccion: rowObj.direccion, observaciones: rowObj.observaciones,
        servicios: rowObj.servicios, linkedin_url: rowObj.linkedin_url,
        fuente_archivo: 'Google Sheets',
      });
      _writeRow(sheet, row, created);
    } else {
      const updates = {
        nombre: rowObj.nombre || null,
        rol: rowObj.rol || null,
        correo: rowObj.correo || null,
        telefono: rowObj.telefono ? String(rowObj.telefono) : null,
        ubicacion: rowObj.ubicacion || null,
        direccion: rowObj.direccion || null,
        clasificacion_negocio: rowObj.clasificacion_negocio || null,
        observaciones: rowObj.observaciones || null,
        servicios: rowObj.servicios || null,
        linkedin_url: rowObj.linkedin_url || null,
        activo: rowObj.activo === true || String(rowObj.activo).toUpperCase() === 'TRUE',
      };
      const updated = _apiCall('PATCH', '/stakeholders/' + id, updates);
      _writeRow(sheet, row, updated);
    }
  } catch (err) {
    sheet.getRange(row, FECHA_ACT_COL).setNote('Error sync: ' + err.message);
  }
}

function _writeRow(sheet, row, obj) {
  _props().setProperty('SYNC_IN_PROGRESS', 'true');
  try {
    const values = COLUMNS.map((k) => (obj[k] !== undefined && obj[k] !== null) ? obj[k] : '');
    sheet.getRange(row, 1, 1, COLUMNS.length).setValues([values]);
    sheet.getRange(row, FECHA_ACT_COL).clearNote();
  } finally {
    _props().deleteProperty('SYNC_IN_PROGRESS');
  }
}

// ----------------------------------------------------------------------------
//  Pull completo desde Postgres (cron + manual)
// ----------------------------------------------------------------------------
function refreshFromPostgres() {
  _props().setProperty('SYNC_IN_PROGRESS', 'true');
  try {
    const rows = _apiCall('GET', '/stakeholders?incluir_inactivos=true&limit=500');
    const sheet = _sheet();
    const lastRow = sheet.getLastRow();
    if (lastRow > 1) sheet.getRange(2, 1, lastRow - 1, COLUMNS.length).clearContent();
    if (!rows.length) return;

    const data = rows.map((r) => COLUMNS.map((k) => (r[k] !== undefined && r[k] !== null) ? r[k] : ''));
    sheet.getRange(2, 1, data.length, COLUMNS.length).setValues(data);
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

  const id = sheet.getRange(row, ID_COL).getValue();
  const nombre = sheet.getRange(row, 2).getValue();
  if (!id) { sheet.deleteRow(row); return; }

  const ui = SpreadsheetApp.getUi();
  const resp = ui.alert(
    'Eliminación permanente',
    `¿Eliminar DEFINITIVAMENTE a "${nombre}" (id=${id}) de Postgres?\n\nEsta acción NO se puede deshacer. Si solo quieres dejar de contactarlo, usa "Desactivar" en su lugar.`,
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
  const id = sheet.getRange(row, ID_COL).getValue();
  if (!id) return;
  const updated = _apiCall('POST', '/stakeholders/' + id + '/deactivate');
  _writeRow(sheet, row, updated);
}

function activateSelectedRow() {
  const sheet = _sheet();
  const row = sheet.getActiveRange().getRow();
  if (row === 1) return;
  const id = sheet.getRange(row, ID_COL).getValue();
  if (!id) return;
  const updated = _apiCall('POST', '/stakeholders/' + id + '/activate');
  _writeRow(sheet, row, updated);
}

// ----------------------------------------------------------------------------
//  Setup: corre una sola vez para crear triggers
// ----------------------------------------------------------------------------
function setupTriggers() {
  const triggers = ScriptApp.getProjectTriggers();
  triggers.forEach((t) => {
    const fn = t.getHandlerFunction();
    if (fn === 'onEditInstallable' || fn === 'refreshFromPostgres') {
      ScriptApp.deleteTrigger(t);
    }
  });

  ScriptApp.newTrigger('onEditInstallable')
    .forSpreadsheet(SpreadsheetApp.getActive())
    .onEdit()
    .create();

  ScriptApp.newTrigger('refreshFromPostgres')
    .timeBased()
    .everyMinutes(5)
    .create();

  SpreadsheetApp.getUi().alert('Triggers creados: onEditInstallable + refreshFromPostgres cada 5 min.');
}
