/* global React, ReactDOM */
const { useState: useSt, useEffect: useEff, useRef: useRf } = React;

/* ============================================================
   SAMPLE DATA
   ============================================================ */
const INBOX_ITEMS = [
  { id:1, type:'note', text:'Revisar propuesta audiovisual de Medellín antes del viernes', date:'23 abr', from:'Captura rápida' },
  { id:2, type:'doc', text:'Convocatoria FDC 2026.pdf', date:'22 abr', from:'Lista de pendientes', size:'1.2 MB' },
  { id:3, type:'note', text:'Llamar a Claudia del ICBF por alianza Risaralda', date:'21 abr', from:'Captura rápida' },
  { id:4, type:'doc', text:'Presupuesto rodaje Piloto.docx', date:'20 abr', from:'Lista de pendientes', size:'340 KB' },
  { id:5, type:'note', text:'Explorar formato documental para caficultores', date:'19 abr', from:'Captura rápida' },
];

const CONTACTS_DATA = [
  { id:1, name:'Claudia Ramírez', phone:'+57 310 456 7890', email:'claudia@icbf.gov.co', type:'Institucional', linkedin:'' },
  { id:2, name:'Andrés Montoya', phone:'+57 315 234 5678', email:'andres@risaraldafilm.co', type:'Aliado Comercial', linkedin:'linkedin.com/in/andresmontoya' },
  { id:3, name:'María Camila Rojas', phone:'', email:'mcrojas@mincultura.gov.co', type:'Gobierno', linkedin:'' },
  { id:4, name:'Carlos Arbeláez', phone:'+57 301 987 6543', email:'', type:'Talento Audiovisual', linkedin:'linkedin.com/in/carlosarbelaez' },
  { id:5, name:'Laura Betancur', phone:'', email:'laura@ejecafetero.org', type:'ONG / Fundación', linkedin:'' },
  { id:6, name:'Felipe Osorio', phone:'+57 318 111 2233', email:'felipe@osorio.co', type:'Proveedor', linkedin:'linkedin.com/in/felipeosorio' },
  { id:7, name:'Diana Velásquez', phone:'', email:'', type:'Gobierno', linkedin:'linkedin.com/in/dianav' },
  { id:8, name:'Santiago Gómez', phone:'+57 312 555 4444', email:'sgomez@cafetv.co', type:'Medio de Comunicación', linkedin:'' },
  { id:9, name:'Natalia Herrera', phone:'', email:'nherrera@udea.edu.co', type:'Academia', linkedin:'' },
  { id:10, name:'Julián Ríos', phone:'+57 300 888 7766', email:'julian@fdc.gov.co', type:'Institucional', linkedin:'linkedin.com/in/julianrios' },
  { id:11, name:'Camilo Duque', phone:'+57 316 999 0011', email:'cduque@manizaleslab.co', type:'Aliado Comercial', linkedin:'' },
  { id:12, name:'Valentina Mejía', phone:'', email:'vale@narrativa.co', type:'Talento Audiovisual', linkedin:'linkedin.com/in/valemejia' },
];

const PROJECTS_DATA = [
  { id:'rc02', name:'Rutas Cafeteras 02', area:'Dirección de Proyectos', budget:'120M COP', spent:'86M (72%)',
    entregables:[
      {t:'Rough cut episodio 1', done:true},
      {t:'Guion episodio 2', done:true},
      {t:'Rodaje episodio 2 (día 3/5)', done:false},
      {t:'Post-producción ep. 1', done:false},
      {t:'Entrega final ep. 1', done:false},
    ],
    docs:['Brief creativo v3.pdf','Contrato FDC.pdf','Investigación Eje Cafetero.docx'] },
  { id:'pileje', name:'Piloto «Eje»', area:'Dirección Audiovisual', budget:'45M COP', spent:'28M (62%)',
    entregables:[
      {t:'Casting confirmado', done:true},
      {t:'Locaciones scout', done:true},
      {t:'Rodaje (día 3/5)', done:false},
      {t:'Edición piloto', done:false},
    ],
    docs:['Guion Piloto v2.pdf','Presupuesto desglose.xlsx'] },
  { id:'labris', name:'Laboratorio Risaralda', area:'Dirección de Investigación', budget:'30M COP', spent:'18M (60%)',
    entregables:[
      {t:'Mapeo territorial', done:true},
      {t:'Talleres comunitarios (4/6)', done:false},
      {t:'Documento síntesis', done:false},
    ],
    docs:['Metodología Lab.pdf','Informe campo semana 1-3.docx'] },
  { id:'acmi', name:'Cumbre ACMI 2026', area:'Dirección Comercial & Financiera', budget:'65M COP', spent:'22M (34%)',
    entregables:[
      {t:'Programa confirmado', done:true},
      {t:'Invitados nacionales', done:true},
      {t:'Invitados internacionales', done:false},
      {t:'Producción evento', done:false},
      {t:'Cobertura audiovisual', done:false},
    ],
    docs:['Propuesta ACMI v4.pdf','Presupuesto evento.xlsx','Lista invitados.csv'] },
];

const STAKEHOLDER_TYPES = ['Clientes','Aliados','Institucional / Gobierno','Proveedores (Locaciones)','Prospecto por Identificar','REVISIÓN_MANUAL'];

/* ============================================================
   FAB — botón flotante "+"
   ============================================================ */
function FAB({ onCaptura, onStakeholder }){
  const [open, setOpen] = useSt(false);
  return (
    <div className="fab-wrap">
      {open && <div className="fab-scrim" onClick={()=>setOpen(false)}/>}
      {open && (
        <div className="fab-menu">
          <button className="fab-opt" onClick={()=>{setOpen(false); onCaptura();}}>
            <span className="fab-opt-ico">⚡</span>
            <div><strong>Captura rápida</strong><span>Nota para la bandeja de Gentil</span></div>
          </button>
          <button className="fab-opt" onClick={()=>{setOpen(false); onStakeholder();}}>
            <span className="fab-opt-ico">👤</span>
            <div><strong>Agregar stakeholder</strong><span>Nuevo contacto al directorio</span></div>
          </button>
        </div>
      )}
      <button className={'fab-btn ' + (open?'on':'')} onClick={()=>setOpen(!open)}>
        <span className="fab-plus">{open ? '×' : '+'}</span>
      </button>
    </div>
  );
}

/* ============================================================
   CAPTURA RÁPIDA — modal pequeño
   ============================================================ */
function CapturaModal({ open, onClose, onSave }){
  const [text, setText] = useSt('');
  if(!open) return null;
  const save = () => {
    if(!text.trim()) return;
    onSave(text.trim());
    setText('');
    onClose();
  };
  return (
    <div className="cap-scrim" onClick={onClose}>
      <div className="cap-box" onClick={e=>e.stopPropagation()}>
        <div className="cap-hd">
          <span className="cap-eye">⚡ CAPTURA RÁPIDA</span>
          <button className="cap-close" onClick={onClose}>×</button>
        </div>
        <textarea className="cap-input" placeholder="Escribe una nota, idea o pendiente..." value={text} onChange={e=>setText(e.target.value)} autoFocus rows={3}/>
        <div className="cap-foot">
          <span className="cap-hint">Gentil procesará esto al final del día</span>
          <button className="cap-save" onClick={save} disabled={!text.trim()}>Guardar en bandeja</button>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   AGREGAR STAKEHOLDER — formulario modal
   ============================================================ */
function StakeholderModal({ open, onClose, onSave, editData }){
  const [form, setForm] = useSt({ name:'', phone:'', email:'', type:'Prospecto por Identificar', linkedin:'', observaciones:'', ubicacion:'', rol:'' });
  const [alert, setAlert] = useSt(null);

  useEff(()=>{
    if(open && editData){
      setForm({
        name: editData.name||'', phone: editData.phone||'', email: editData.email||'',
        type: editData.type||'Prospecto por Identificar', linkedin: editData.linkedin||'',
        observaciones: editData.observaciones||'', ubicacion: editData.ubicacion||'', rol: editData.rol||'',
      });
    } else if(open){
      setForm({ name:'', phone:'', email:'', type:'Prospecto por Identificar', linkedin:'', observaciones:'', ubicacion:'', rol:'' });
    }
    setAlert(null);
  },[open, editData]);

  if(!open) return null;

  const update = (k,v) => setForm(f=>({...f,[k]:v}));
  const isEdit = !!editData;

  const save = () => {
    if(!form.name.trim()){ setAlert('El nombre es obligatorio.'); return; }
    const hasPhone = form.phone.trim();
    const hasEmail = form.email.trim();
    const hasLinkedin = form.linkedin.trim();

    if(!hasPhone && !hasEmail && !hasLinkedin){
      setAlert('No hay manera de contactar a esta persona. Agrega al menos un teléfono, correo o LinkedIn.');
      return;
    }
    if(!hasPhone && !hasEmail && hasLinkedin){
      if(!window.confirm('La única forma de contactar a esta persona es por LinkedIn. ¿Estás de acuerdo?')) return;
    }
    onSave({...form, id: editData ? editData.id : Date.now()});
    setAlert(null);
    onClose();
  };

  return (
    <div className="cap-scrim" onClick={onClose}>
      <div className="stk-box" onClick={e=>e.stopPropagation()}>
        <div className="cap-hd">
          <span className="cap-eye">👤 {isEdit ? 'EDITAR' : 'AGREGAR'} STAKEHOLDER</span>
          <button className="cap-close" onClick={onClose}>×</button>
        </div>
        {alert && <div className="stk-alert">{alert}</div>}
        <div className="stk-form">
          <div className="stk-field">
            <label>Nombre <span className="req">*</span></label>
            <input type="text" value={form.name} onChange={e=>update('name',e.target.value)} placeholder="Nombre completo" autoFocus/>
          </div>
          <div className="stk-row2">
            <div className="stk-field">
              <label>Teléfono</label>
              <input type="tel" value={form.phone} onChange={e=>update('phone',e.target.value)} placeholder="+57 3XX XXX XXXX"/>
            </div>
            <div className="stk-field">
              <label>Correo electrónico</label>
              <input type="email" value={form.email} onChange={e=>update('email',e.target.value)} placeholder="correo@ejemplo.com"/>
            </div>
          </div>
          <div className="stk-row2">
            <div className="stk-field">
              <label>Tipo de stakeholder</label>
              <select value={form.type} onChange={e=>update('type',e.target.value)}>
                {STAKEHOLDER_TYPES.map(t=><option key={t}>{t}</option>)}
              </select>
            </div>
            <div className="stk-field">
              <label>LinkedIn</label>
              <input type="url" value={form.linkedin} onChange={e=>update('linkedin',e.target.value)} placeholder="linkedin.com/in/..."/>
            </div>
          </div>
          <div className="stk-row2">
            <div className="stk-field">
              <label>Rol / Cargo</label>
              <input type="text" value={form.rol} onChange={e=>update('rol',e.target.value)} placeholder="Director, Gestor Cultural…"/>
            </div>
            <div className="stk-field">
              <label>Ciudad / Ubicación</label>
              <input type="text" value={form.ubicacion} onChange={e=>update('ubicacion',e.target.value)} placeholder="Pereira, Bogotá…"/>
            </div>
          </div>
          <div className="stk-field">
            <label>Observaciones <span style={{opacity:.5, fontSize:10, fontWeight:400}}>— Gentil las procesa al final del día para enriquecer el perfil</span></label>
            <textarea
              value={form.observaciones}
              onChange={e=>update('observaciones',e.target.value)}
              placeholder="Notas libres: contexto de la relación, proyectos en común, intereses, cómo se conocieron, próximo paso sugerido…"
              rows={3}
              style={{width:'100%', resize:'vertical', fontFamily:'inherit', fontSize:12, padding:'8px', background:'var(--bg2)', border:'1px solid var(--bdr)', borderRadius:6, color:'inherit'}}
            />
          </div>
        </div>
        <div className="stk-foot">
          <button className="stk-cancel" onClick={onClose}>Cancelar</button>
          <button className="stk-save" onClick={save}>{isEdit ? 'Guardar cambios' : 'Guardar stakeholder'}</button>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   SIDEBAR IZQUIERDO — Bandeja + Directorio
   ============================================================ */
function Sidebar({ open, onClose, inbox, setInbox, contacts, setContacts, onEditStakeholder }){
  const [tab, setTab] = useSt('bandeja');
  const [page, setPage] = useSt(0);
  const [editNote, setEditNote] = useSt(null);
  const [editText, setEditText] = useSt('');
  const PER_PAGE = 10;

  if(!open) return null;

  const pageContacts = contacts.slice(page*PER_PAGE, (page+1)*PER_PAGE);
  const totalPages = Math.ceil(contacts.length / PER_PAGE);

  const deleteInbox = async (id) => {
    setInbox(prev => prev.filter(x => x.id !== id));
    const k = window.__API_KEY__ || '';
    const b = (window.__API_BASE__ || '').replace(/\/$/,'');
    try { await fetch(`${b}/inbox/${id}`,{method:'DELETE',headers:k?{'X-API-Key':k}:{}}); } catch(e){}
  };
  const startEditNote = (item) => { setEditNote(item.id); setEditText(item.text); };
  const saveEditNote = async () => {
    setInbox(prev => prev.map(x => x.id === editNote ? {...x, text: editText} : x));
    setEditNote(null);
    const k = window.__API_KEY__ || '';
    const b = (window.__API_BASE__ || '').replace(/\/$/,'');
    try {
      await fetch(`${b}/inbox/${editNote}`,{method:'PATCH',
        headers:{'Content-Type':'application/json',...(k?{'X-API-Key':k}:{})},
        body:JSON.stringify({texto:editText})});
    } catch(e){}
  };
  const deleteContact = async (id) => {
    const k = window.__API_KEY__ || '';
    const b = (window.__API_BASE__ || '').replace(/\/$/,'');
    try {
      await fetch(`${b}/stakeholders/${id}`, {method:'DELETE', headers: k ? {'X-API-Key':k} : {}});
    } catch(e) {}
    setContacts(prev => prev.filter(x => x.id !== id));
  };

  return (
    <>
      <div className="sb-scrim" onClick={onClose}/>
      <nav className="sb-drawer">
        <div className="sb-hd">
          <span className="sb-sub">CENTRO DE MANDO · LA FALLA D.F.</span>
          <button className="sb-close" onClick={onClose}>×</button>
        </div>

        <div className="sb-tabs">
          <button className={'sb-tab '+(tab==='bandeja'?'on':'')} onClick={()=>{setTab('bandeja'); setPage(0);}}>
            <span>📥</span> Bandeja de Entrada
            {inbox.length > 0 && <span className="sb-badge">{inbox.length}</span>}
          </button>
          <button className={'sb-tab '+(tab==='directorio'?'on':'')} onClick={()=>{setTab('directorio'); setPage(0);}}>
            <span>📇</span> Directorio de Contactos
            <span className="sb-badge">{contacts.length}</span>
          </button>
        </div>

        <div className="sb-body">
          {tab === 'bandeja' && (
            <div className="sb-list">
              {inbox.length === 0 && <div className="sb-empty">Bandeja vacía · las capturas rápidas y documentos diferidos aparecerán aquí</div>}
              {inbox.map((item,i) => (
                <div key={item.id||i} className="sb-item">
                  <span className="sb-item-ico">{item.type==='note' ? '⚡' : '📄'}</span>
                  <div className="sb-item-body">
                    {editNote === item.id ? (
                      <>
                        <textarea className="sb-edit-input" value={editText} onChange={e=>setEditText(e.target.value)} autoFocus rows={2}/>
                        <div className="sb-edit-acts">
                          <button className="sb-edit-save" onClick={saveEditNote}>Guardar</button>
                          <button className="sb-edit-cancel" onClick={()=>setEditNote(null)}>Cancelar</button>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="sb-item-text">{item.text}</div>
                        <div className="sb-item-meta">{item.from} · {item.date}</div>
                      </>
                    )}
                  </div>
                  {editNote !== item.id && (
                    <div className="sb-item-acts">
                      <button className="sb-act-btn" onClick={()=>startEditNote(item)} title="Editar">✎</button>
                      <button className="sb-act-btn sb-act-del" onClick={()=>deleteInbox(item.id)} title="Eliminar">×</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {tab === 'directorio' && (
            <div className="sb-contacts">
              {pageContacts.map(c => (
                <div key={c.id} className="sb-contact">
                  <div className="sb-c-avatar">{c.name.split(' ').map(w=>w[0]).join('').slice(0,2)}</div>
                  <div className="sb-c-info">
                    <div className="sb-c-name">{c.name}</div>
                    <div className="sb-c-type">{c.type}</div>
                    <div className="sb-c-details">
                      {c.phone && <a href={`tel:${c.phone.replace(/\s/g,'')}`} className="sb-c-link">📞 {c.phone}</a>}
                      {c.email && <a href={`mailto:${c.email}`} className="sb-c-link">✉ {c.email}</a>}
                      {c.linkedin && <a href={c.linkedin.startsWith('http')?c.linkedin:`https://${c.linkedin}`} target="_blank" rel="noopener noreferrer" className="sb-c-link">🔗 LinkedIn</a>}
                      {!c.phone && !c.email && !c.linkedin && <span className="sb-c-nocontact">Sin datos de contacto</span>}
                    </div>
                  </div>
                  <div className="sb-item-acts">
                    <button className="sb-act-btn" onClick={()=>{ onClose(); onEditStakeholder(c); }} title="Editar">✎</button>
                    <button className="sb-act-btn sb-act-del" onClick={()=>deleteContact(c.id)} title="Eliminar">×</button>
                  </div>
                </div>
              ))}
              {totalPages > 1 && (
                <div className="sb-pager">
                  <button disabled={page===0} onClick={()=>setPage(p=>p-1)}>← Anterior</button>
                  <span>{page+1} / {totalPages}</span>
                  <button disabled={page>=totalPages-1} onClick={()=>setPage(p=>p+1)}>Siguiente →</button>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="sb-foot">
          <span>VPS KVM8 · 32GB · EasyPanel</span>
          <span>Postgres · n8n · FastAPI · Ollama</span>
        </div>
      </nav>
    </>
  );
}

/* ============================================================
   NUEVO PROYECTO — formulario modal especializado
   ============================================================ */
const AREAS_PROJ = ['Proyectos','Audiovisual','Investigacion','Comercial'];

function NewProjectModal({ open, onClose, onSave }){
  const [form, setForm] = useSt({ nombre:'', codigo:'', area:'Dirección de Proyectos', presupuesto:'', entregables:[''] });
  const [saving, setSaving] = useSt(false);

  useEff(()=>{
    if(open) setForm({ nombre:'', codigo:'', area:'Dirección de Proyectos', presupuesto:'', entregables:[''] });
  },[open]);

  if(!open) return null;
  const upd = (k,v) => setForm(f=>({...f,[k]:v}));
  const addEnt = () => setForm(f=>({...f, entregables:[...f.entregables,'']}));
  const updEnt = (i,v) => setForm(f=>({...f, entregables:f.entregables.map((e,j)=>j===i?v:e)}));
  const delEnt = (i) => setForm(f=>({...f, entregables:f.entregables.filter((_,j)=>j!==i)}));

  const save = async () => {
    if(!form.nombre.trim()) return;
    setSaving(true);
    const k = window.__API_KEY__ || '';
    const b = (window.__API_BASE__ || '').replace(/\/$/,'');
    const h = {'Content-Type':'application/json',...(k?{'X-API-Key':k}:{})};
    const codigo = form.codigo.trim() || form.nombre.toLowerCase().replace(/\s+/g,'-').slice(0,20)+'-'+Date.now().toString().slice(-4);
    const presupuesto = parseFloat(String(form.presupuesto).replace(/[^0-9.]/g,''))||0;
    try {
      const r = await fetch(`${b}/projects`,{method:'POST',headers:h,body:JSON.stringify({
        codigo, nombre:form.nombre.trim(), area:form.area, presupuesto, ejecutado:0, estado:'activo'
      })});
      if(r.ok){
        const proj = await r.json();
        const ents = form.entregables.filter(e=>e.trim());
        for(let i=0;i<ents.length;i++){
          await fetch(`${b}/projects/${proj.id}/deliverables`,{method:'POST',headers:h,body:JSON.stringify({titulo:ents[i],completado:false,orden:i})});
        }
        const r2 = await fetch(`${b}/projects/${proj.id}`,{headers:k?{'X-API-Key':k}:{}});
        onSave(r2.ok ? await r2.json() : {...proj, entregables:[], docs:[]});
      }
    } catch(e){ console.error('Error creando proyecto:',e); }
    setSaving(false);
    onClose();
  };

  return (
    <div className="cap-scrim" onClick={onClose}>
      <div className="proj-new-box" onClick={e=>e.stopPropagation()}>
        <div className="cap-hd">
          <span className="cap-eye">📁 NUEVO PROYECTO</span>
          <button className="cap-close" onClick={onClose}>×</button>
        </div>
        <div className="stk-form">
          <div className="stk-field">
            <label>Nombre del proyecto <span className="req">*</span></label>
            <input type="text" value={form.nombre} onChange={e=>upd('nombre',e.target.value)} placeholder="Ej. Rutas Cafeteras 03" autoFocus/>
          </div>
          <div className="stk-row2">
            <div className="stk-field">
              <label>Código</label>
              <input type="text" value={form.codigo} onChange={e=>upd('codigo',e.target.value)} placeholder="Auto-generado"/>
            </div>
            <div className="stk-field">
              <label>Área responsable</label>
              <select value={form.area} onChange={e=>upd('area',e.target.value)}>
                {AREAS_PROJ.map(a=><option key={a}>{a}</option>)}
              </select>
            </div>
          </div>
          <div className="stk-field">
            <label>Presupuesto total (COP)</label>
            <input type="text" value={form.presupuesto} onChange={e=>upd('presupuesto',e.target.value)} placeholder="Ej. 120000000"/>
          </div>
          <div className="stk-field">
            <label>Entregables iniciales</label>
            {form.entregables.map((e,i)=>(
              <div key={i} className="proj-ent-row">
                <input type="text" value={e} onChange={ev=>updEnt(i,ev.target.value)} placeholder={`Entregable ${i+1}`}/>
                {form.entregables.length > 1 && <button className="cap-close" onClick={()=>delEnt(i)}>×</button>}
              </div>
            ))}
            <button className="stk-cancel proj-add-ent" onClick={addEnt}>+ Entregable</button>
          </div>
          <div className="proj-new-hint">💡 Adjunta documentos del proyecto desde <strong>Subir Recurso</strong> en el panel principal</div>
        </div>
        <div className="stk-foot">
          <button className="stk-cancel" onClick={onClose} disabled={saving}>Cancelar</button>
          <button className="stk-save" onClick={save} disabled={saving||!form.nombre.trim()}>{saving?'Guardando…':'Crear proyecto'}</button>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   EDT — DATOS Y HELPERS PARA 9 MODOS
   ============================================================ */

const EDT_FALLBACK = {
  id: 'rc02',
  nombre: 'Rutas Cafeteras 02',
  fechaInicio: '2025-01-15',
  nodos: [
    { id:'1.0', codigo:'1.0', nivel:1, nombre:'Pre-producción', costo:32000000, duracion_dias:20, porcentaje_avance:100, es_paquete_trabajo:false, es_hito:false, estado:'completo', responsable:'Equipo', predecesores:[], alerta:null,
      hijos:[
        {id:'1.1',codigo:'1.1',nivel:2,nombre:'Investigación y guion',costo:8000000,duracion_dias:10,porcentaje_avance:100,es_paquete_trabajo:true,es_hito:false,estado:'completo',responsable:'Investigación',predecesores:[],alerta:null,hijos:[]},
        {id:'1.2',codigo:'1.2',nivel:2,nombre:'Casting y scouting',costo:6000000,duracion_dias:8,porcentaje_avance:100,es_paquete_trabajo:true,es_hito:false,estado:'completo',responsable:'Dirección',predecesores:['1.1'],alerta:null,hijos:[]},
        {id:'1.3',codigo:'1.3',nivel:2,nombre:'Permisos y logística',costo:4000000,duracion_dias:5,porcentaje_avance:100,es_paquete_trabajo:true,es_hito:false,estado:'completo',responsable:'Producción',predecesores:[],alerta:null,hijos:[]},
      ]
    },
    { id:'1.M',codigo:'1.M',nivel:1,nombre:'Arranque aprobado',costo:0,duracion_dias:0,porcentaje_avance:100,es_paquete_trabajo:false,es_hito:true,estado:'completo',responsable:'GG',predecesores:['1.1','1.2','1.3'],alerta:null,hijos:[]},
    { id:'2.0',codigo:'2.0',nivel:1,nombre:'Producción / Rodaje',costo:38000000,duracion_dias:15,porcentaje_avance:55,es_paquete_trabajo:false,es_hito:false,estado:'en_curso',responsable:'Dirección',predecesores:['1.M'],alerta:null,
      hijos:[
        {id:'2.1',codigo:'2.1',nivel:2,nombre:'Rodaje episodio 2',costo:20000000,duracion_dias:7,porcentaje_avance:43,es_paquete_trabajo:true,es_hito:false,estado:'en_curso',responsable:'Dirección',predecesores:['1.M'],alerta:'día 3/5',hijos:[]},
        {id:'2.2',codigo:'2.2',nivel:2,nombre:'Post-producción ep. 1',costo:18000000,duracion_dias:9,porcentaje_avance:0,es_paquete_trabajo:true,es_hito:false,estado:'planificado',responsable:'Dirección',predecesores:['2.1'],alerta:null,hijos:[]},
      ]
    },
    { id:'3.0',codigo:'3.0',nivel:1,nombre:'Post-producción',costo:32000000,duracion_dias:30,porcentaje_avance:0,es_paquete_trabajo:false,es_hito:false,estado:'planificado',responsable:'Editor',predecesores:['2.0'],alerta:null,
      hijos:[
        {id:'3.1',codigo:'3.1',nivel:2,nombre:'Edición rough cut',costo:12000000,duracion_dias:12,porcentaje_avance:0,es_paquete_trabajo:true,es_hito:false,estado:'planificado',responsable:'Editor',predecesores:['2.2'],alerta:null,hijos:[]},
        {id:'3.2',codigo:'3.2',nivel:2,nombre:'Color y sonido',costo:15000000,duracion_dias:15,porcentaje_avance:0,es_paquete_trabajo:true,es_hito:false,estado:'planificado',responsable:'Post',predecesores:['3.1'],alerta:null,hijos:[]},
        {id:'3.3',codigo:'3.3',nivel:2,nombre:'Máster final',costo:5000000,duracion_dias:3,porcentaje_avance:0,es_paquete_trabajo:true,es_hito:false,estado:'planificado',responsable:'Director',predecesores:['3.2'],alerta:null,hijos:[]},
      ]
    },
    { id:'3.M',codigo:'3.M',nivel:1,nombre:'Rough cut listo',costo:0,duracion_dias:0,porcentaje_avance:0,es_paquete_trabajo:false,es_hito:true,estado:'planificado',responsable:'GG',predecesores:['3.1'],alerta:null,hijos:[]},
    { id:'4.0',codigo:'4.0',nivel:1,nombre:'Entrega y distribución',costo:18000000,duracion_dias:7,porcentaje_avance:0,es_paquete_trabajo:false,es_hito:false,estado:'planificado',responsable:'Producción',predecesores:['3.3'],alerta:null,
      hijos:[
        {id:'4.1',codigo:'4.1',nivel:2,nombre:'Entrega FDC',costo:10000000,duracion_dias:2,porcentaje_avance:0,es_paquete_trabajo:true,es_hito:false,estado:'planificado',responsable:'Producción',predecesores:['3.3'],alerta:null,hijos:[]},
        {id:'4.2',codigo:'4.2',nivel:2,nombre:'Distribución plataformas',costo:8000000,duracion_dias:5,porcentaje_avance:0,es_paquete_trabajo:true,es_hito:false,estado:'planificado',responsable:'GA',predecesores:['4.1'],alerta:null,hijos:[]},
      ]
    },
    { id:'4.M',codigo:'4.M',nivel:1,nombre:'Entrega final aprobada',costo:0,duracion_dias:0,porcentaje_avance:0,es_paquete_trabajo:false,es_hito:true,estado:'planificado',responsable:'GG',predecesores:['4.2'],alerta:null,hijos:[]},
  ]
};

function _flatEdt(nodes) {
  const flat = [];
  function walk(arr) { (arr||[]).forEach(n=>{ flat.push(n); walk(n.hijos); }); }
  walk(nodes);
  return flat;
}

function _healthClass(avance, alerta) {
  if(alerta) return 'critico';
  if(avance >= 90) return 'optimo';
  if(avance >= 50) return 'estable';
  if(avance >= 20) return 'friccion';
  return 'critico';
}

function _cpm(nodes, fechaInicioISO) {
  const flat = _flatEdt(nodes);
  const byId = {};
  flat.forEach(n => byId[n.id] = n);
  const es = {}, ef = {};
  const calcEF = (n) => {
    if(ef[n.id] !== undefined) return ef[n.id];
    const preds = (n.predecesores||[]).map(pid => { const p = byId[pid]; if(!p) return 0; return calcEF(p); });
    es[n.id] = preds.length ? Math.max(...preds) : 0;
    ef[n.id] = (es[n.id]||0) + (n.duracion_dias||0);
    return ef[n.id];
  };
  flat.forEach(n => calcEF(n));
  const total = flat.length ? Math.max(...Object.values(ef)) : 0;
  const ls = {}, lf = {};
  flat.forEach(n => {
    if(!flat.some(m => (m.predecesores||[]).includes(n.id))) lf[n.id] = total;
  });
  const calcLS = (n) => {
    if(ls[n.id] !== undefined) return ls[n.id];
    if(lf[n.id] === undefined) {
      const succs = flat.filter(m => (m.predecesores||[]).includes(n.id));
      const vals = succs.map(m => { calcLS(m); return ls[m.id] !== undefined ? ls[m.id] : total; });
      lf[n.id] = vals.length ? Math.min(...vals) : total;
    }
    ls[n.id] = (lf[n.id]||0) - (n.duracion_dias||0);
    return ls[n.id];
  };
  flat.forEach(n => { calcLS(n); });
  const fecha0 = fechaInicioISO ? new Date(fechaInicioISO) : new Date('2025-01-15');
  const addDias = (d) => { const r = new Date(fecha0); r.setDate(r.getDate()+d); return r.toISOString().slice(0,10); };
  return flat.map(n => ({
    ...n,
    es_dias: es[n.id]||0, ef_dias: ef[n.id]||0,
    ls_dias: ls[n.id]||0, lf_dias: lf[n.id]||0,
    holgura: (ls[n.id]||0)-(es[n.id]||0),
    critica: ((ls[n.id]||0)-(es[n.id]||0)) === 0,
    fecha_inicio: addDias(es[n.id]||0),
    fecha_fin: addDias(ef[n.id]||0),
    duracion_total: total,
  }));
}

function _buildCurvaS(cpmResult, todayISO) {
  if(!cpmResult || !cpmResult.length) return null;
  const total = cpmResult[0].duracion_total || 120;
  const paquetes = cpmResult.filter(n => n.es_paquete_trabajo);
  const bac = paquetes.reduce((s,n) => s+(n.costo||0), 0);
  const today = todayISO ? new Date(todayISO) : new Date();
  const fecha0 = new Date(cpmResult[0].fecha_inicio);
  const diasHoy = Math.max(0, Math.round((today-fecha0)/(1000*86400)));
  const periodos = 12;
  const diasPorPeriodo = Math.ceil(total/periodos);
  const pv=[], ev=[], ac=[];
  for(let i=0; i<=periodos; i++) {
    const d = i*diasPorPeriodo;
    const pvVal = paquetes.filter(n=>n.ef_dias<=d).reduce((s,n)=>s+(n.costo||0),0);
    const evVal = paquetes.filter(n=>n.ef_dias<=d).reduce((s,n)=>s+(n.costo||0)*(n.porcentaje_avance||0)/100,0);
    pv.push(Math.round(pvVal/bac*100));
    ev.push(Math.round(evVal/bac*100));
    ac.push(Math.round(evVal/bac*100*1.082));
  }
  const periodHoy = Math.min(periodos, Math.floor(diasHoy/diasPorPeriodo));
  const evHoy = ev[periodHoy]||0;
  const pvHoy = pv[periodHoy]||1;
  const acHoy = ac[periodHoy]||0;
  const cpi = evHoy > 0 ? evHoy/acHoy : 1;
  const spi = pvHoy > 0 ? evHoy/pvHoy : 1;
  const eac = cpi > 0 ? bac/cpi : bac;
  return { bac, ev: Math.round(bac*evHoy/100), ac: Math.round(bac*acHoy/100), cpi: Math.round(cpi*100)/100, spi: Math.round(spi*100)/100, eac: Math.round(eac), pv, ev_arr: ev, ac_arr: ac, periodos, periodHoy };
}

const ADQUISICIONES_FALLBACK = [
  { id:'A01', elemento:'Arriendo cámara ARRI', tipo:'bien', metodo:'Cotización directa', contrato:'CTR-001', inicio:'2025-01-20', entrega:'2025-02-10', costo:8000000, estado:'entregado' },
  { id:'A02', elemento:'Transporte y logística', tipo:'servicio', metodo:'Orden de servicio', contrato:'OS-003', inicio:'2025-02-01', entrega:'2025-03-15', costo:6000000, estado:'vencido' },
  { id:'A03', elemento:'Edición y post-producción', tipo:'servicio', metodo:'Licitación menor', contrato:'CTR-004', inicio:'2025-03-01', entrega:'2025-04-20', costo:12000000, estado:'vencido' },
  { id:'A04', elemento:'Licencias de software', tipo:'intangible', metodo:'Compra directa', contrato:'—', inicio:'2025-01-15', entrega:'2025-01-18', costo:2000000, estado:'entregado' },
  { id:'A05', elemento:'Hospedaje equipo campo', tipo:'servicio', metodo:'Orden de servicio', contrato:'OS-007', inicio:'2025-02-10', entrega:'2025-03-30', costo:4000000, estado:'vencido' },
  { id:'A06', elemento:'Diseño gráfico piezas', tipo:'servicio', metodo:'Cotización directa', contrato:'CTR-009', inicio:'2026-04-01', entrega:'2026-06-30', costo:3500000, estado:'en_proceso' },
];

function _detectCuellos(adqs) {
  const hoy = new Date();
  return adqs.map(a => {
    if(a.estado === 'entregado') return {...a, semaforo:'entregado'};
    const d = new Date(a.entrega);
    const diff = Math.round((d-hoy)/(1000*86400));
    if(diff < 0) return {...a, semaforo:'rojo'};
    if(diff <= 14) return {...a, semaforo:'naranja'};
    return {...a, semaforo:'verde'};
  });
}

const RIESGOS_FALLBACK = {
  sugeridos: [
    { id:'RS01', descripcion:'Bloqueo comunitario en Caribe', causa:'Falta de acuerdo con comunidad local', efecto:'Paro del rodaje >5 días', area:'Proyectos', probabilidad:4, impacto:5, estrategia:'Evitar', responsable:'Director GP', paquete:'2.1' },
    { id:'RS02', descripcion:'Sobrecosto material Pereira', causa:'Inflación de alquiler de equipos', efecto:'Desfase presupuestal +15%', area:'Proyectos', probabilidad:4, impacto:4, estrategia:'Mitigar', responsable:'GCF', paquete:'2.1' },
    { id:'RS03', descripcion:'Editor sin contrato vigente', causa:'Contrato vencido sin renovar', efecto:'Retraso en edición rough cut', area:'Proyectos', probabilidad:4, impacto:4, estrategia:'Transferir', responsable:'Director GP', paquete:'3.1' },
  ],
  activos: [
    { id:'R01', descripcion:'Lluvia en zona de rodaje', causa:'Temporada de lluvias Eje Cafetero', efecto:'Pérdida de días de rodaje', area:'Proyectos', probabilidad:3, impacto:5, estrategia:'Mitigar', responsable:'Director GP', paquete:'2.1', estado_mitigacion:'en_mitigacion' },
    { id:'R02', descripcion:'Retraso en aprobación FDC', causa:'Cambio de directivos en FDC', efecto:'Congelamiento de fondos 30 días', area:'Comercial', probabilidad:2, impacto:5, estrategia:'Aceptar', responsable:'GG', paquete:'4.1', estado_mitigacion:'monitoreado' },
  ]
};

function _detectRiesgosSugeridos(paquetes, adqs) {
  const sugeridos = [];
  paquetes.forEach(p => {
    if(p.alerta && !sugeridos.find(s=>s.paquete===p.codigo)) {
      sugeridos.push({ id:'RS-auto-'+p.codigo, descripcion:'Alerta activa: '+p.nombre, causa:'Paquete con alerta en cronograma', efecto:'Posible retraso en fase', area:'Proyectos', probabilidad:4, impacto:5, estrategia:'Evitar', responsable:'Director GP', paquete:p.codigo, auto:true });
    }
    if(p.critica && p.porcentaje_avance < 30 && !sugeridos.find(s=>s.paquete===p.codigo)) {
      sugeridos.push({ id:'RS-crit-'+p.codigo, descripcion:'Ruta crítica con bajo avance: '+p.nombre, causa:'Holgura cero con avance insuficiente', efecto:'Retraso en entrega final', area:'Proyectos', probabilidad:3, impacto:5, estrategia:'Mitigar', responsable:'Director GP', paquete:p.codigo, auto:true });
    }
  });
  (adqs||[]).forEach(a => {
    if(a.semaforo === 'rojo') {
      sugeridos.push({ id:'RS-adq-'+a.id, descripcion:'Adquisición vencida: '+a.elemento, causa:'Fecha de entrega superada', efecto:'Cuello de botella en producción', area:'Proyectos', probabilidad:3, impacto:4, estrategia:'Transferir', responsable:'GCF', paquete:'—', auto:true });
    }
  });
  return sugeridos;
}

function _gentilRiesgoFeedback(estrategia, prob, imp) {
  const nr = prob * imp;
  if(nr >= 15) return `Gentil: Riesgo CRÍTICO (Nr=${nr}). Estrategia ${estrategia} apropiada. Considera activar plan de contingencia inmediato.`;
  if(nr >= 10) return `Gentil: Riesgo ALTO (Nr=${nr}). Estrategia ${estrategia} válida. Monitoreo semanal recomendado.`;
  return `Gentil: Riesgo MODERADO (Nr=${nr}). Estrategia ${estrategia} suficiente por ahora.`;
}

const COMUNICACIONES_FALLBACK = [
  { id:'C01', tipo:'inf_semanal', descripcion:'Informe semanal de avance', origen:'auto_cronograma', receptor:'GG / Clementino', email:'clementino@lafalla.co', metodo:'email', frecuencia:'semanal', responsable:'Director GP', estado:'pendiente' },
  { id:'C02', tipo:'alerta_riesgo', descripcion:'Alerta riesgo crítico RS01', origen:'auto_riesgo', receptor:'GG / Clementino', email:'clementino@lafalla.co', metodo:'whatsapp', frecuencia:'evento', responsable:'Director GP', estado:'enviado' },
  { id:'C03', tipo:'acta', descripcion:'Acta de reunión quincenal', origen:'manual', receptor:'Equipo interno', email:'', metodo:'reunion', frecuencia:'quincenal', responsable:'Director GP', estado:'enviado' },
  { id:'C04', tipo:'notif_proveedor', descripcion:'Notificación proveedor vencido: Transporte', origen:'auto_adquisicion', receptor:'GCF / Quinaya', email:'quinaya@lafalla.co', metodo:'email', frecuencia:'evento', responsable:'GCF', estado:'pendiente' },
  { id:'C05', tipo:'hito', descripcion:'Hito Rough Cut listo', origen:'auto_hito', receptor:'GG / Stakeholders', email:'clementino@lafalla.co', metodo:'email', frecuencia:'evento', responsable:'Director GP', estado:'pendiente' },
];

function _detectComunicaciones(paquetes, adqs, risks) {
  const auto = [{ id:'C-auto-inf', tipo:'inf_semanal', descripcion:'Informe semanal automático', origen:'auto_cronograma', receptor:'GG', email:'', metodo:'email', frecuencia:'semanal', responsable:'Director GP', estado:'pendiente' }];
  (paquetes||[]).filter(p=>p.es_hito).forEach(h => {
    auto.push({ id:'C-hito-'+h.codigo, tipo:'hito', descripcion:'Hito: '+h.nombre, origen:'auto_hito', receptor:'GG / Stakeholders', email:'', metodo:'email', frecuencia:'evento', responsable:'Director GP', estado:'pendiente' });
  });
  (risks||[]).filter(r=>r.probabilidad*r.impacto>=15).forEach(r => {
    auto.push({ id:'C-riesgo-'+r.id, tipo:'alerta_riesgo', descripcion:'Alerta: '+r.descripcion, origen:'auto_riesgo', receptor:'GG', email:'', metodo:'whatsapp', frecuencia:'evento', responsable:'Director GP', estado:'pendiente' });
  });
  (adqs||[]).filter(a=>a.semaforo==='rojo').forEach(a => {
    auto.push({ id:'C-adq-'+a.id, tipo:'notif_proveedor', descripcion:'Proveedor vencido: '+a.elemento, origen:'auto_adquisicion', receptor:'GCF', email:'', metodo:'email', frecuencia:'evento', responsable:'GCF', estado:'pendiente' });
  });
  return auto;
}

function _buildMailto(comm, proyecto) {
  const asunto = encodeURIComponent(`[${proyecto||'La Falla'}] ${comm.descripcion}`);
  const cuerpo = encodeURIComponent(`Estimado equipo,\n\nSe informa:\n${comm.descripcion}\n\nProyecto: ${proyecto||'—'}\n\nGentil · Centro de Mando La Falla D.F.`);
  return `mailto:${comm.email||''}?subject=${asunto}&body=${cuerpo}`;
}

function _buildCalendarUrl(comm, proyecto) {
  const titulo = encodeURIComponent(`[${proyecto||'La Falla'}] ${comm.descripcion}`);
  const detalle = encodeURIComponent(`Comunicación: ${comm.descripcion}\nResponsable: ${comm.responsable}`);
  return `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${titulo}&details=${detalle}`;
}

const RACI_FALLBACK = {
  personas: [
    { id:'p1', nombre:'Clementino', rol:'GG', iniciales:'CL' },
    { id:'p2', nombre:'Director GP', rol:'GP', iniciales:'DG' },
    { id:'p3', nombre:'Director GA', rol:'GA', iniciales:'DA' },
    { id:'p4', nombre:'Dir. GCF', rol:'GCF', iniciales:'CF' },
    { id:'p5', nombre:'Beto', rol:'Producción', iniciales:'BE' },
    { id:'p6', nombre:'Lina', rol:'Investigación', iniciales:'LN' },
    { id:'p7', nombre:'Editor ext.', rol:'Editor', iniciales:'ED' },
  ],
  asignaciones: {
    '1.1':{ p1:'I', p2:'A', p3:'I', p4:'I', p5:'C', p6:'R', p7:'I' },
    '1.2':{ p1:'I', p2:'A', p3:'C', p4:'I', p5:'R', p6:'I', p7:'I' },
    '1.3':{ p1:'I', p2:'A', p3:'I', p4:'C', p5:'R', p6:'I', p7:'I' },
    '2.1':{ p1:'I', p2:'A', p3:'R', p4:'I', p5:'C', p6:'C', p7:'I' },
    '2.2':{ p1:'I', p2:'A', p3:'R', p4:'I', p5:'C', p6:'I', p7:'C' },
    '3.1':{ p1:'I', p2:'A', p3:'C', p4:'I', p5:'I', p6:'I', p7:'R' },
    '3.2':{ p1:'I', p2:'A', p3:'C', p4:'I', p5:'I', p6:'I', p7:'R' },
    '3.3':{ p1:'A', p2:'R', p3:'C', p4:'I', p5:'I', p6:'I', p7:'C' },
    '4.1':{ p1:'A', p2:'R', p3:'I', p4:'C', p5:'C', p6:'I', p7:'I' },
    '4.2':{ p1:'I', p2:'A', p3:'R', p4:'C', p5:'C', p6:'I', p7:'I' },
  }
};

function _buildRaciAuto(flat) {
  const paquetes = flat.filter(n=>n.es_paquete_trabajo);
  const personas = [{ id:'p1', nombre:'Responsable', rol:'Asignado', iniciales:'RS' }];
  const asignaciones = {};
  paquetes.forEach(p => { asignaciones[p.codigo] = { p1:'R' }; });
  return { personas, asignaciones };
}

/* ============================================================
   EDT VIEWER — 9 modos: árbol/tabla/calor/cronograma/evm/adq/riesgos/com/raci
   ============================================================ */
function EdtViewer({ project }) {
  const [mode, setMode] = useSt('arbol');
  const [wizardOpen, setWizardOpen] = useSt(false);
  const [edtData, setEdtData] = useSt(null);
  const [cpmResult, setCpmResult] = useSt(null);
  const [adqData, setAdqData] = useSt(null);
  const [riskSugeridos, setRiskSugeridos] = useSt([]);
  const [riskActivos, setRiskActivos] = useSt([]);
  const [sugeridosState, setSugeridosState] = useSt({});
  const [comData, setComData] = useSt(null);
  const [comEstados, setComEstados] = useSt({});
  const [raciData, setRaciData] = useSt(null);
  const [raciView, setRaciView] = useSt('matriz');
  const [hovRisk, setHovRisk] = useSt(null);
  const [showNewRisk, setShowNewRisk] = useSt(false);
  const [newRiskForm, setNewRiskForm] = useSt({ descripcion:'', causa:'', efecto:'', probabilidad:3, impacto:3, estrategia:'Mitigar', responsable:'', paquete:'', area:'Proyectos' });
  const [gentilFeedback, setGentilFeedback] = useSt('');
  const [showNewCom, setShowNewCom] = useSt(false);
  const [newComForm, setNewComForm] = useSt({ tipo:'inf_semanal', metodo:'email', descripcion:'', receptor:'', email:'', frecuencia:'evento', responsable:'' });
  const [shPicker, setShPicker] = useSt('');
  const [showSyncModal, setShowSyncModal] = useSt(false);
  const [showAddPersona, setShowAddPersona] = useSt(false);
  const [newPersonaForm, setNewPersonaForm] = useSt({ nombre:'', rol:'' });

  const mono = { fontFamily:'IBM Plex Mono, monospace' };
  const title = { fontFamily:'Space Mono, monospace' };
  const SC = { done:'#00FF41', progress:'#e89c2b', pending:'#c8c8c2', phase:'' };
  const SL = { done:'✓', progress:'◐', pending:'○' };

  // Build phases from API project data
  const ents = (project.entregables || []);
  const pct = project.pct_ejecutado || 0;
  const phases = [
    { id:'1.0', name:'Pre-producción', dur:20,
      tasks: ents.slice(0,2).length > 0 ? ents.slice(0,2).map((e,i)=>({ id:`1.${i+1}`, name:e.titulo||e.t, dur:8+i*3, resp:'Equipo', status:e.completado||e.done?'done':'pending' })) : [
        {id:'1.1',name:'Investigación y guion',dur:10,resp:'Investigación',status:pct>=20?'done':'pending'},
        {id:'1.2',name:'Casting y scouting',dur:8,resp:'Dirección',status:pct>=20?'done':'pending'},
        {id:'1.3',name:'Permisos y logística',dur:5,resp:'Producción',status:pct>=15?'done':'pending'},
      ]
    },
    { id:'2.0', name:'Producción / Rodaje', dur:15, milestone:true,
      tasks: ents.slice(2,4).length > 0 ? ents.slice(2,4).map((e,i)=>({ id:`2.${i+1}`, name:e.titulo||e.t, dur:7+i*2, resp:'Dirección', status:e.completado||e.done?'done':pct>=50?'progress':'pending' })) : [
        {id:'2.1',name:'Rodaje principal',dur:10,resp:'Dirección',status:pct>=60?'done':pct>=30?'progress':'pending'},
        {id:'2.2',name:'Material adicional',dur:5,resp:'Dirección',status:pct>=70?'done':'pending'},
      ]
    },
    { id:'3.0', name:'Post-producción', dur:30,
      tasks:[
        {id:'3.1',name:'Edición rough cut',dur:12,resp:'Editor',status:pct>=80?'done':pct>=60?'progress':'pending'},
        {id:'3.2',name:'Color y sonido',dur:15,resp:'Post',status:pct>=95?'done':'pending'},
        {id:'3.3',name:'Máster final',dur:3,resp:'Director',status:pct>=99?'done':'pending'},
      ]
    },
    { id:'4.0', name:'Entrega y distribución', dur:7, milestone:true,
      tasks: ents.slice(-1).length > 0 && ents.slice(-1)[0] ? [{id:'4.1',name:ents[ents.length-1].titulo||ents[ents.length-1].t,dur:5,resp:'Producción',status:(ents[ents.length-1].completado||ents[ents.length-1].done)?'done':'pending'}] : [
        {id:'4.1',name:'Entrega final',dur:2,resp:'Producción',status:pct>=100?'done':'pending'},
        {id:'4.2',name:'Distribución',dur:5,resp:'GA',status:'pending'},
      ]
    },
  ];

  // Load EDT/CPM data
  useEff(() => {
    const base = (window.__API_BASE__||'').replace(/\/$/,'');
    const k = window.__API_KEY__||'';
    
    // Fetch EDT
    fetch(`${base}/api/projects/${project.id}/edt`, k?{headers:{'X-API-Key':k}}:{})
      .then(r=>r.ok?r.json():Promise.reject())
      .then(d=>{ setEdtData(d); const c=_cpm(d.nodos, d.fechaInicio); setCpmResult(c); })
      .catch(()=>{ setEdtData(EDT_FALLBACK); const c=_cpm(EDT_FALLBACK.nodos, EDT_FALLBACK.fechaInicio); setCpmResult(c); });
      
    // Fetch RACI
    fetch(`${base}/api/projects/${project.id}/raci`, k?{headers:{'X-API-Key':k}}:{})
      .then(r=>r.ok?r.json():Promise.reject())
      .then(d=>setRaciData(d))
      .catch(()=>setRaciData(RACI_FALLBACK));

    setAdqData(_detectCuellos(ADQUISICIONES_FALLBACK));
    setRiskSugeridos(RIESGOS_FALLBACK.sugeridos);
    setRiskActivos(RIESGOS_FALLBACK.activos);
    setComData(COMUNICACIONES_FALLBACK);
  }, [project.id]);

  const flat = edtData ? _flatEdt(edtData.nodos) : [];
  const paquetes = flat.filter(n=>n.es_paquete_trabajo);
  const evm = cpmResult ? _buildCurvaS(cpmResult, new Date().toISOString().slice(0,10)) : null;
  const autoComm = comData ? _detectComunicaciones(cpmResult||[], adqData||[], riskActivos) : [];
  const allCom = [...(comData||[]), ...autoComm.filter(ac=>!(comData||[]).find(c=>c.id===ac.id))];

  // Mode buttons
  const modes9 = [
    ['arbol','🌳 Árbol'],['tabla','📋 Tabla'],['calor','🌡 Calor'],['cronograma','📅 Gantt'],
    ['curva-s','📈 Curva S'],['adquisiciones','🛒 Adq.'],['riesgos','⚠️ Riesgos'],['comunicaciones','📨 Com.'],['raci','👥 RACI'],
  ];

  return (
    <div style={{ paddingBottom:16 }}>
      {/* Mode switcher */}
      <div style={{ display:'flex', gap:6, marginBottom:16, flexWrap:'wrap', alignItems:'center' }}>
        {modes9.map(([m,l])=>(
          <button key={m} onClick={()=>setMode(m)} style={{
            padding:'4px 10px', fontSize:10, ...mono, letterSpacing:'0.07em',
            background: mode===m ? '#00FF41' : 'transparent',
            color: mode===m ? '#000' : 'var(--ink-3)',
            border: mode===m ? '1.5px solid #00FF41' : '1.5px solid var(--line)',
            borderRadius:6, cursor:'pointer', fontWeight: mode===m?700:400, whiteSpace:'nowrap',
          }}>{l}</button>
        ))}
        <span style={{ marginLeft:'auto', fontSize:10, ...mono, color:'var(--mute)', letterSpacing:'0.1em' }}>
          EDT · {phases.length} FASES · {phases.reduce((s,p)=>s+p.tasks.length,0)} TAREAS
        </span>
      </div>

      {/* MODO: ÁRBOL */}
      {mode==='arbol' && (
        <div>
          {phases.map(phase=>(
            <div key={phase.id} style={{ marginBottom:8 }}>
              <div style={{ display:'flex', alignItems:'center', gap:10, padding:'8px 12px', borderRadius:8, marginBottom:4, background:phase.milestone?'#00FF4110':'var(--bg)', borderLeft:phase.milestone?'3px solid #00FF41':'3px solid var(--line)' }}>
                <span style={{ ...mono, fontSize:11, fontWeight:700, color:'#00C433', minWidth:32 }}>{phase.id}</span>
                <span style={{ ...title, fontSize:12, fontWeight:700, letterSpacing:'-0.01em', flex:1 }}>{phase.name}</span>
                {phase.milestone && <span style={{ fontSize:9, ...mono, letterSpacing:'0.12em', color:'#00C433', background:'#00FF4118', padding:'2px 8px', borderRadius:4 }}>★ HITO</span>}
                <span style={{ ...mono, fontSize:10, color:'var(--mute)', minWidth:34, textAlign:'right' }}>{phase.dur}d</span>
              </div>
              {phase.tasks.map(t=>(
                <div key={t.id} style={{ display:'flex', alignItems:'center', gap:10, padding:'5px 12px 5px 28px', borderRadius:6, marginBottom:2, background:t.status==='done'?'#00FF4106':'transparent' }}>
                  <span style={{ color:SC[t.status], fontSize:13, minWidth:16 }}>{SL[t.status]}</span>
                  <span style={{ ...mono, fontSize:10, color:'var(--mute)', minWidth:28 }}>{t.id}</span>
                  <span style={{ fontFamily:'Work Sans,system-ui,sans-serif', fontSize:13, flex:1, color:t.status==='done'?'var(--mute)':'var(--ink)', textDecoration:t.status==='done'?'line-through':'none' }}>{t.name}</span>
                  <span style={{ ...mono, fontSize:10, color:'var(--mute)', minWidth:70 }}>{t.resp}</span>
                  <span style={{ ...mono, fontSize:10, color:'var(--ink-3)', minWidth:30, textAlign:'right' }}>{t.dur}d</span>
                </div>
              ))}
            </div>
          ))}
          <div style={{ marginTop:16, padding:'10px 16px', borderRadius:8, border:'1.5px dashed #00FF4140', textAlign:'center', cursor:'pointer', background:'#00FF4106' }} onClick={()=>setWizardOpen&&setWizardOpen(true)}>
            <span style={{ ...mono, fontSize:10, color:'#00C433', letterSpacing:'0.08em' }}>🧠 EDT ESTIMADO · Clic para construirlo con documentos reales vía Gentil</span>
          </div>
        </div>
      )}

      {/* MODO: TABLA */}
      {mode==='tabla' && (
        <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
          <thead>
            <tr style={{ borderBottom:'1.5px solid var(--line)' }}>
              {['ID','Nombre','Responsable','Dur.','Estado'].map(h=>(
                <th key={h} style={{ textAlign:'left', padding:'6px 8px', ...mono, fontSize:10, letterSpacing:'0.1em', color:'var(--mute)', fontWeight:600 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {phases.flatMap(p=>[{id:p.id,name:p.name,resp:'—',dur:p.dur,status:'phase',milestone:p.milestone},...p.tasks]).map(row=>(
              <tr key={row.id} style={{ borderBottom:'1px solid var(--line)', background:row.status==='phase'?'var(--bg)':'transparent' }}>
                <td style={{ padding:'6px 8px', ...mono, fontSize:11, fontWeight:row.status==='phase'?700:400, color:row.status==='phase'?'#00C433':'var(--ink-3)' }}>{row.id}</td>
                <td style={{ padding:'6px 8px', fontFamily:row.status==='phase'?'Space Mono,monospace':'Work Sans,system-ui,sans-serif', fontWeight:row.status==='phase'?700:400, paddingLeft:row.status==='phase'?8:20 }}>{row.name}</td>
                <td style={{ padding:'6px 8px', ...mono, fontSize:11, color:'var(--mute)' }}>{row.resp||'—'}</td>
                <td style={{ padding:'6px 8px', ...mono, fontSize:11 }}>{row.dur}d</td>
                <td style={{ padding:'6px 8px' }}>
                  {row.status!=='phase' && <span style={{ display:'inline-block', padding:'2px 8px', borderRadius:4, fontSize:10, ...mono, letterSpacing:'0.08em', background:row.status==='done'?'#00FF4118':row.status==='progress'?'#e89c2b18':'#f0f0ee', color:row.status==='done'?'#00C433':row.status==='progress'?'#e89c2b':'var(--mute)' }}>{row.status==='done'?'✓ LISTO':row.status==='progress'?'◐ EN CURSO':'○ PENDIENTE'}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* MODO: MAPA DE CALOR */}
      {mode==='calor' && (
        <div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(140px,1fr))', gap:8, marginBottom:16 }}>
            {flat.filter(n=>n.es_paquete_trabajo||n.es_hito).map(n=>{
              const hc = _healthClass(n.porcentaje_avance||0, n.alerta);
              const bg = hc==='optimo'?'#00FF4130':hc==='estable'?'#00FF4118':hc==='friccion'?'#e89c2b20':'#cc333320';
              const bc = hc==='optimo'?'#00FF41':hc==='estable'?'#00C433':hc==='friccion'?'#e89c2b':'#cc3333';
              return (
                <div key={n.id} style={{ padding:'10px 12px', borderRadius:8, background:bg, border:`1.5px solid ${bc}40` }}>
                  <div style={{ ...mono, fontSize:9, color:bc, letterSpacing:'0.1em', marginBottom:4 }}>{n.codigo} {n.es_hito?'◆':''}</div>
                  <div style={{ fontFamily:'Work Sans,system-ui,sans-serif', fontSize:11, color:'var(--ink)', lineHeight:1.3, marginBottom:6 }}>{n.nombre}</div>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                    <div style={{ height:4, flex:1, background:'var(--line)', borderRadius:2, overflow:'hidden', marginRight:8 }}>
                      <div style={{ height:'100%', width:(n.porcentaje_avance||0)+'%', background:bc, borderRadius:2 }}/>
                    </div>
                    <span style={{ ...mono, fontSize:10, color:bc, fontWeight:700 }}>{n.porcentaje_avance||0}%</span>
                  </div>
                  {n.alerta && <div style={{ ...mono, fontSize:9, color:'#cc3333', marginTop:4 }}>⚠ {n.alerta}</div>}
                </div>
              );
            })}
          </div>
          <div style={{ display:'flex', gap:12, ...mono, fontSize:10, color:'var(--mute)', letterSpacing:'0.08em' }}>
            {[['#00FF41','Óptimo ≥90%'],['#00C433','Estable 50-89%'],['#e89c2b','Fricción 20-49%'],['#cc3333','Crítico <20%']].map(([c,l])=>(
              <span key={c} style={{ display:'flex', alignItems:'center', gap:5 }}>
                <span style={{ width:10, height:10, background:c, borderRadius:2, display:'inline-block' }}/>
                {l}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* MODO: CRONOGRAMA (Gantt + CPM) */}
      {mode==='cronograma' && (
        <div>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:12 }}>
            <span style={{ ...mono, fontSize:10, color:'var(--mute)', letterSpacing:'0.1em' }}>GANTT · RUTA CRÍTICA · CPM</span>
            <button onClick={()=>setShowSyncModal(true)} style={{ padding:'4px 12px', fontSize:10, ...mono, background:'transparent', border:'1.5px solid var(--line)', borderRadius:6, cursor:'pointer', color:'var(--ink-3)' }}>☁ Sincronizar Google</button>
          </div>
          {(() => {
            const items = cpmResult || [];
            const total = items.length && items[0].duracion_total ? items[0].duracion_total : 80;
            const rowH = 32, padL = 120, W = 560;
            const toX = d => padL + (d/total)*(W-padL-8);
            const meses = Math.ceil(total/30);
            return (
              <div style={{ overflowX:'auto' }}>
                <svg width={W} height={Math.max(200, items.length*rowH+40)} style={{ fontFamily:'IBM Plex Mono, monospace', display:'block' }}>
                  {/* Encabezado meses */}
                  {Array.from({length:meses+1},(_,i)=> (
                    <g key={i}>
                      <line x1={toX(i*30)} x2={toX(i*30)} y1={0} y2={items.length*rowH+30} stroke="#e8e8e4" strokeWidth="0.8"/>
                      <text x={toX(i*30)+3} y={12} fontSize="8" fill="#aaa">S{i*4}</text>
                    </g>
                  ))}
                  {/* Hoy */}
                  {(() => { const d = Math.round((new Date()-new Date('2025-01-15'))/(1000*86400)); return d>0&&d<total?<line x1={toX(d)} x2={toX(d)} y1={0} y2={items.length*rowH+30} stroke="#888" strokeWidth="1" strokeDasharray="3,3"/>:null; })()}
                  {/* Filas */}
                  {items.map((n,i)=>{
                    const y = 20 + i*rowH;
                    const x1 = toX(n.es_dias||0);
                    const x2 = toX(n.ef_dias||0);
                    const barW = Math.max(4, x2-x1);
                    const isHito = n.es_hito;
                    const isCrit = n.critica;
                    const barColor = isCrit ? '#cc3333' : n.estado==='completo' ? '#00FF41' : n.estado==='en_curso' ? '#e89c2b' : '#89b4fa';
                    return (
                      <g key={n.id}>
                        <text x={2} y={y+16} fontSize="9" fill="var(--ink-3)" style={{ fontFamily:'IBM Plex Mono,monospace' }}>{(n.codigo||n.id).slice(0,10)}</text>
                        {isHito ? (
                          <polygon points={`${x1},${y+rowH/2} ${x1+8},${y+8} ${x1+16},${y+rowH/2} ${x1+8},${y+rowH-8}`}
                                   fill="#9370DB" opacity="0.9"/>
                        ) : (
                          <rect x={x1} y={y+6} width={barW} height={rowH-14} rx="3"
                                fill={barColor} fillOpacity={n.estado==='planificado'?0.35:0.8}
                                stroke={isCrit?'#cc3333':'none'} strokeWidth={isCrit?1.5:0}/>
                        )}
                        {isCrit && !isHito && <text x={x2+4} y={y+16} fontSize="8" fill="#cc3333">RC</text>}
                        {n.porcentaje_avance > 0 && !isHito && <rect x={x1} y={y+6} width={barW*(n.porcentaje_avance/100)} height={rowH-14} rx="3" fill="#00FF41" fillOpacity="0.35"/>}
                      </g>
                    );
                  })}
                </svg>
              </div>
            );
          })()}
          <div style={{ display:'flex', gap:12, marginTop:12, ...mono, fontSize:10, color:'var(--mute)' }}>
            {[['#cc3333','Ruta crítica'],['#00FF41','Completo'],['#e89c2b','En curso'],['#89b4fa','Planificado'],['#9370DB','◆ Hito']].map(([c,l])=>(
              <span key={c} style={{ display:'flex', alignItems:'center', gap:4 }}><span style={{ width:10, height:8, background:c, borderRadius:2, display:'inline-block', opacity:0.8 }}/>{l}</span>
            ))}
          </div>
          {showSyncModal && (
            <div style={{ position:'fixed', inset:0, background:'#00000060', display:'flex', alignItems:'center', justifyContent:'center', zIndex:9999 }} onClick={()=>setShowSyncModal(false)}>
              <div style={{ background:'#fff', borderRadius:12, padding:24, minWidth:320, maxWidth:400 }} onClick={e=>e.stopPropagation()}>
                <div style={{ ...mono, fontSize:10, color:'var(--mute)', letterSpacing:'0.1em', marginBottom:8 }}>☁ SINCRONIZAR GOOGLE</div>
                <p style={{ fontFamily:'Work Sans,sans-serif', fontSize:13, color:'var(--ink-3)', marginBottom:16 }}>Los hitos y paquetes de la ruta crítica se exportarán a los servicios seleccionados.</p>
                {[['📅 Google Calendar','Hitos → eventos con responsable'],['📊 Google Sheets','EDT completa como tabla viva'],['✅ Google Tasks','Paquetes por responsable con deadline']].map(([tit,desc])=>(
                  <div key={tit} style={{ padding:'10px 14px', borderRadius:8, border:'1.5px solid var(--line)', marginBottom:8, cursor:'pointer', opacity:0.6 }}>
                    <div style={{ ...mono, fontSize:11, color:'var(--ink)' }}>{tit}</div>
                    <div style={{ fontFamily:'Work Sans,sans-serif', fontSize:11, color:'var(--mute)', marginTop:2 }}>{desc} · <em>Disponible en Sprint 2</em></div>
                  </div>
                ))}
                <button onClick={()=>setShowSyncModal(false)} style={{ marginTop:8, padding:'6px 16px', ...mono, fontSize:10, background:'transparent', border:'1.5px solid var(--line)', borderRadius:6, cursor:'pointer' }}>Cerrar</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* MODO: CURVA S */}
      {mode==='curva-s' && <CurvaSViewer project={project}/>}

      {/* MODO: ADQUISICIONES */}
      {mode==='adquisiciones' && (
        <div>
          {(() => {
            const adqs = adqData || [];
            const total = adqs.length;
            const sinEntregar = adqs.filter(a=>a.semaforo!=='entregado').length;
            const cuellos = adqs.filter(a=>a.semaforo==='rojo').length;
            const monto = adqs.reduce((s,a)=>s+(a.costo||0),0);
            return (
              <>
                <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10, marginBottom:16 }}>
                  {[
                    {label:'ADQUISICIONES',val:total,color:'#89b4fa'},
                    {label:'MONTO EST.',val:`$${(monto/1e6).toFixed(1)}M`,color:'var(--ink)'},
                    {label:'SIN ENTREGAR',val:sinEntregar,color:'#e89c2b'},
                    {label:'CUELLOS',val:cuellos,color:cuellos>0?'#cc3333':'#00FF41'},
                  ].map(c=>(
                    <div key={c.label} style={{ padding:'12px 14px', borderRadius:8, border:`1.5px solid ${c.color}30`, background:`${c.color}08` }}>
                      <div style={{ ...mono, fontSize:9, color:'var(--mute)', letterSpacing:'0.1em', marginBottom:4 }}>{c.label}</div>
                      <div style={{ ...mono, fontSize:18, color:c.color, fontWeight:700 }}>{c.val}</div>
                    </div>
                  ))}
                </div>
                {cuellos > 0 && <div style={{ padding:'8px 14px', borderRadius:8, background:'#cc333318', border:'1.5px solid #cc333340', marginBottom:14, ...mono, fontSize:11, color:'#cc3333' }}>⚠ {cuellos} adquisición(es) vencida(s) — cuello de botella activo</div>}
                <table style={{ width:'100%', borderCollapse:'collapse', fontSize:11 }}>
                  <thead>
                    <tr style={{ borderBottom:'1.5px solid var(--line)' }}>
                      {['Elemento','Tipo','Método','Entrega','Costo est.','Estado'].map(h=>(
                        <th key={h} style={{ textAlign:'left', padding:'6px 8px', ...mono, fontSize:9, letterSpacing:'0.1em', color:'var(--mute)', fontWeight:600 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {adqs.map(a=>{
                      const smColor = a.semaforo==='entregado'?'#00FF41':a.semaforo==='rojo'?'#cc3333':a.semaforo==='naranja'?'#e89c2b':'#00C433';
                      const smLabel = a.semaforo==='entregado'?'✓ ENTREGADO':a.semaforo==='rojo'?'⚠ VENCIDO':a.semaforo==='naranja'?'◐ PRÓXIMO':'○ EN PROCESO';
                      const tipoColor = a.tipo==='bien'?'#89b4fa':a.tipo==='servicio'?'#e89c2b':a.tipo==='intangible'?'#cba6f7':'var(--ink-3)';
                      return (
                        <tr key={a.id} style={{ borderBottom:'1px solid var(--line)', background:a.semaforo==='rojo'?'#cc333308':a.semaforo==='naranja'?'#e89c2b06':'transparent' }}>
                          <td style={{ padding:'7px 8px', fontFamily:'Work Sans,sans-serif', fontSize:12 }}>{a.elemento}</td>
                          <td style={{ padding:'7px 8px' }}><span style={{ ...mono, fontSize:9, color:tipoColor, background:`${tipoColor}18`, padding:'2px 6px', borderRadius:4 }}>{a.tipo}</span></td>
                          <td style={{ padding:'7px 8px', ...mono, fontSize:10, color:'var(--ink-3)' }}>{a.metodo}</td>
                          <td style={{ padding:'7px 8px', ...mono, fontSize:10 }}>{a.entrega}</td>
                          <td style={{ padding:'7px 8px', ...mono, fontSize:11, fontWeight:600 }}>${(a.costo/1e6).toFixed(1)}M</td>
                          <td style={{ padding:'7px 8px' }}><span style={{ ...mono, fontSize:9, color:smColor, background:`${smColor}15`, padding:'2px 8px', borderRadius:4, fontWeight:600 }}>{smLabel}</span></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <div style={{ display:'flex', gap:12, marginTop:12, ...mono, fontSize:10, color:'var(--mute)' }}>
                  {[['#00FF41','Entregado'],['#00C433','En proceso'],['#e89c2b','Próximo ≤14d'],['#cc3333','Vencido']].map(([c,l])=>(
                    <span key={c} style={{ display:'flex', alignItems:'center', gap:5 }}><span style={{ width:8, height:8, background:c, borderRadius:'50%', display:'inline-block' }}/>{l}</span>
                  ))}
                </div>
              </>
            );
          })()}
        </div>
      )}

      {/* MODO: RIESGOS */}
      {mode==='riesgos' && (
        <div>
          {/* Sugeridos auto */}
          {riskSugeridos.filter(r=>!sugeridosState[r.id]).length > 0 && (
            <div style={{ marginBottom:16, padding:'12px 14px', borderRadius:10, border:'1.5px solid #e89c2b40', background:'#e89c2b08' }}>
              <div style={{ ...mono, fontSize:10, color:'#e89c2b', letterSpacing:'0.1em', marginBottom:10 }}>⚡ SUGERIDOS POR GENTIL · DETECCIÓN AUTOMÁTICA</div>
              {riskSugeridos.filter(r=>!sugeridosState[r.id]).map(r=>{
                const nr = r.probabilidad*r.impacto;
                const lvl = nr>=15?'CRÍTICO':nr>=10?'ALTO':nr>=6?'MEDIO':'BAJO';
                const lvlC = nr>=15?'#cc3333':nr>=10?'#e89c2b':'var(--mute)';
                return (
                  <div key={r.id} style={{ display:'flex', alignItems:'flex-start', gap:10, padding:'8px 10px', borderRadius:8, background:'#fff', border:'1px solid var(--line)', marginBottom:8 }}>
                    <div style={{ flex:1 }}>
                      <div style={{ display:'flex', gap:8, alignItems:'center', marginBottom:4 }}>
                        <span style={{ ...mono, fontSize:9, color:lvlC, background:`${lvlC}15`, padding:'2px 6px', borderRadius:3 }}>{lvl} Nr={nr}</span>
                        <span style={{ ...mono, fontSize:9, color:'var(--mute)' }}>{r.estrategia} · {r.paquete}</span>
                      </div>
                      <div style={{ fontFamily:'Work Sans,sans-serif', fontSize:12, color:'var(--ink)' }}>{r.descripcion}</div>
                    </div>
                    <div style={{ display:'flex', gap:6 }}>
                      <button onClick={()=>{ setSugeridosState(s=>({...s,[r.id]:'aceptado'})); setRiskActivos(prev=>[...prev,{...r,id:r.id,estado_mitigacion:'monitoreado'}]); }} style={{ padding:'4px 10px', ...mono, fontSize:10, background:'#00FF4118', border:'1.5px solid #00FF4140', color:'#00C433', borderRadius:5, cursor:'pointer' }}>✓ Aceptar</button>
                      <button onClick={()=>setSugeridosState(s=>({...s,[r.id]:'rechazado'}))} style={{ padding:'4px 10px', ...mono, fontSize:10, background:'#cc333318', border:'1.5px solid #cc333340', color:'#cc3333', borderRadius:5, cursor:'pointer' }}>✗</button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Matriz 5×5 */}
          <div style={{ display:'flex', gap:20, marginBottom:16 }}>
            <div>
              <div style={{ ...mono, fontSize:9, color:'var(--mute)', letterSpacing:'0.1em', marginBottom:8, textAlign:'center' }}>IMPACTO →</div>
              <div style={{ display:'flex', gap:4 }}>
                <div style={{ display:'flex', flexDirection:'column', gap:4, alignItems:'flex-end', justifyContent:'center', marginRight:4 }}>
                  {[5,4,3,2,1].map(p=><span key={p} style={{ ...mono, fontSize:9, color:'var(--mute)', height:36, lineHeight:'36px' }}>P{p}</span>)}
                </div>
                <div style={{ display:'grid', gridTemplateColumns:'repeat(5,36px)', gridTemplateRows:'repeat(5,36px)', gap:4 }}>
                  {[5,4,3,2,1].flatMap(prob=>[1,2,3,4,5].map(imp=>{
                    const nr=prob*imp;
                    const bg=nr>=15?'#cc333330':nr>=10?'#e89c2b25':nr>=6?'#f9e2af20':'#00FF4110';
                    const dots=(riskActivos||[]).filter(r=>r.probabilidad===prob&&r.impacto===imp);
                    return (
                      <div key={`${prob}-${imp}`} style={{ width:36, height:36, borderRadius:4, background:bg, border:'1px solid var(--line)', display:'flex', alignItems:'center', justifyContent:'center', flexWrap:'wrap', gap:2, position:'relative' }}>
                        {dots.map(r=>(
                          <span key={r.id} title={r.descripcion} onMouseEnter={()=>setHovRisk(r.id)} onMouseLeave={()=>setHovRisk(null)} style={{ width:8, height:8, borderRadius:'50%', background:hovRisk===r.id?'#00FF41':'#cc3333', cursor:'pointer', display:'inline-block' }}/>
                        ))}
                      </div>
                    );
                  }))}
                </div>
              </div>
              <div style={{ display:'flex', gap:4, marginTop:4, paddingLeft:24 }}>
                {[1,2,3,4,5].map(i=><span key={i} style={{ width:36, textAlign:'center', ...mono, fontSize:9, color:'var(--mute)' }}>I{i}</span>)}
              </div>
            </div>
            {/* Tabla activos */}
            <div style={{ flex:1, overflowX:'auto' }}>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
                <div style={{ ...mono, fontSize:10, color:'var(--mute)', letterSpacing:'0.1em' }}>RIESGOS ACTIVOS</div>
                <button onClick={()=>setShowNewRisk(true)} style={{ padding:'4px 10px', ...mono, fontSize:10, background:'#00FF4118', border:'1.5px solid #00FF4140', color:'#00C433', borderRadius:6, cursor:'pointer' }}>+ Nuevo riesgo</button>
              </div>
              {riskActivos.length === 0 ? <div style={{ ...mono, fontSize:11, color:'var(--mute)', padding:'16px 0' }}>Sin riesgos activos.</div> : (
                <table style={{ width:'100%', borderCollapse:'collapse', fontSize:11 }}>
                  <thead><tr style={{ borderBottom:'1.5px solid var(--line)' }}>
                    {['ID','Descripción','P','I','Nr','Estrategia','Estado'].map(h=><th key={h} style={{ textAlign:'left', padding:'5px 6px', ...mono, fontSize:9, color:'var(--mute)', letterSpacing:'0.1em' }}>{h}</th>)}
                  </tr></thead>
                  <tbody>
                    {riskActivos.sort((a,b)=>b.probabilidad*b.impacto-a.probabilidad*a.impacto).map(r=>{
                      const nr=r.probabilidad*r.impacto;
                      const lvlC=nr>=15?'#cc3333':nr>=10?'#e89c2b':nr>=6?'var(--ink-3)':'var(--mute)';
                      const estC=r.estado_mitigacion==='critico'?'#cc3333':r.estado_mitigacion==='en_mitigacion'?'#e89c2b':'var(--mute)';
                      return (
                        <tr key={r.id} style={{ borderBottom:'1px solid var(--line)', background:hovRisk===r.id?'#00FF4108':'transparent' }}
                            onMouseEnter={()=>setHovRisk(r.id)} onMouseLeave={()=>setHovRisk(null)}>
                          <td style={{ padding:'5px 6px', ...mono, fontSize:9, color:'var(--mute)' }}>{r.id}</td>
                          <td style={{ padding:'5px 6px', fontFamily:'Work Sans,sans-serif', fontSize:12, maxWidth:180 }}>{r.descripcion}</td>
                          <td style={{ padding:'5px 6px', ...mono, fontSize:11, textAlign:'center' }}>{r.probabilidad}</td>
                          <td style={{ padding:'5px 6px', ...mono, fontSize:11, textAlign:'center' }}>{r.impacto}</td>
                          <td style={{ padding:'5px 6px', ...mono, fontSize:11, color:lvlC, fontWeight:700 }}>{nr}</td>
                          <td style={{ padding:'5px 6px', ...mono, fontSize:9 }}>{r.estrategia}</td>
                          <td style={{ padding:'5px 6px', ...mono, fontSize:9, color:estC }}>{r.estado_mitigacion||'monitoreado'}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* Modal nuevo riesgo */}
          {showNewRisk && (
            <div style={{ position:'fixed', inset:0, background:'#00000060', display:'flex', alignItems:'center', justifyContent:'center', zIndex:9999 }} onClick={()=>setShowNewRisk(false)}>
              <div style={{ background:'#fff', borderRadius:12, padding:24, minWidth:380, maxWidth:500 }} onClick={e=>e.stopPropagation()}>
                <div style={{ ...mono, fontSize:10, color:'var(--mute)', letterSpacing:'0.1em', marginBottom:14 }}>+ NUEVO RIESGO</div>
                {[['Descripción','descripcion','text'],['Causa','causa','text'],['Efecto','efecto','text'],['Responsable','responsable','text'],['Paquete','paquete','text']].map(([label,key,type])=>(
                  <div key={key} style={{ marginBottom:10 }}>
                    <label style={{ ...mono, fontSize:10, color:'var(--mute)', display:'block', marginBottom:4 }}>{label}</label>
                    <input type={type} value={newRiskForm[key]||''} onChange={e=>setNewRiskForm(f=>({...f,[key]:e.target.value}))}
                           style={{ width:'100%', padding:'6px 10px', borderRadius:6, border:'1.5px solid var(--line)', fontFamily:'Work Sans,sans-serif', fontSize:12, boxSizing:'border-box' }}/>
                  </div>
                ))}
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:10, marginBottom:10 }}>
                  {[['Probabilidad','probabilidad',[1,2,3,4,5]],['Impacto','impacto',[1,2,3,4,5]],['Estrategia','estrategia',['Evitar','Mitigar','Transferir','Aceptar']]].map(([label,key,opts])=>(
                    <div key={key}>
                      <label style={{ ...mono, fontSize:10, color:'var(--mute)', display:'block', marginBottom:4 }}>{label}</label>
                      <select value={newRiskForm[key]} onChange={e=>setNewRiskForm(f=>({...f,[key]:e.target.value}))}
                              style={{ width:'100%', padding:'6px 8px', borderRadius:6, border:'1.5px solid var(--line)', fontFamily:'IBM Plex Mono,monospace', fontSize:11 }}>
                        {opts.map(o=><option key={o}>{o}</option>)}
                      </select>
                    </div>
                  ))}
                </div>
                {gentilFeedback && <div style={{ padding:'8px 12px', borderRadius:8, background:'#9370DB18', border:'1.5px solid #9370DB40', ...mono, fontSize:11, color:'#9370DB', marginBottom:12 }}>{gentilFeedback}</div>}
                <div style={{ display:'flex', gap:8, justifyContent:'flex-end' }}>
                  <button onClick={()=>{ setGentilFeedback(''); setTimeout(()=>setGentilFeedback(_gentilRiesgoFeedback(newRiskForm.estrategia, parseInt(newRiskForm.probabilidad)||3, parseInt(newRiskForm.impacto)||3)),400); }} style={{ padding:'6px 14px', ...mono, fontSize:10, background:'#9370DB18', border:'1.5px solid #9370DB40', color:'#9370DB', borderRadius:6, cursor:'pointer' }}>⬡ Validar con Gentil</button>
                  <button onClick={()=>setShowNewRisk(false)} style={{ padding:'6px 14px', ...mono, fontSize:10, background:'transparent', border:'1.5px solid var(--line)', borderRadius:6, cursor:'pointer' }}>Cancelar</button>
                  <button onClick={()=>{ const nr = parseInt(newRiskForm.probabilidad||3)*parseInt(newRiskForm.impacto||3); setRiskActivos(prev=>[...prev,{...newRiskForm,id:'R'+Date.now(),probabilidad:parseInt(newRiskForm.probabilidad||3),impacto:parseInt(newRiskForm.impacto||3),nr,estado_mitigacion:'monitoreado'}]); setShowNewRisk(false); setGentilFeedback(''); }}
                        style={{ padding:'6px 14px', ...mono, fontSize:10, background:'#00FF4118', border:'1.5px solid #00FF4140', color:'#00C433', borderRadius:6, cursor:'pointer' }}>Guardar</button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* MODO: COMUNICACIONES */}
      {mode==='comunicaciones' && (
        <div>
          {(() => {
            const all = allCom;
            const pendientes = all.filter(c=>(comEstados[c.id]||c.estado)==='pendiente').length;
            const enviadas = all.filter(c=>(comEstados[c.id]||c.estado)==='enviado').length;
            const porEvento = all.filter(c=>c.frecuencia==='evento').length;
            return (
              <>
                <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10, marginBottom:14 }}>
                  {[{label:'TOTAL',val:all.length,color:'var(--ink)'},{label:'PENDIENTES',val:pendientes,color:'#e89c2b'},{label:'ENVIADAS',val:enviadas,color:'#00FF41'},{label:'POR EVENTO',val:porEvento,color:'#89b4fa'}].map(c=>(
                    <div key={c.label} style={{ padding:'12px 14px', borderRadius:8, border:`1.5px solid ${c.color}30`, background:`${c.color}06` }}>
                      <div style={{ ...mono, fontSize:9, color:'var(--mute)', letterSpacing:'0.1em', marginBottom:4 }}>{c.label}</div>
                      <div style={{ ...mono, fontSize:18, color:c.color, fontWeight:700 }}>{c.val}</div>
                    </div>
                  ))}
                </div>
                <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:10 }}>
                  <button onClick={()=>setShowNewCom(true)} style={{ padding:'5px 14px', ...mono, fontSize:10, background:'#00FF4118', border:'1.5px solid #00FF4140', color:'#00C433', borderRadius:6, cursor:'pointer' }}>+ Nueva comunicación</button>
                </div>
                <table style={{ width:'100%', borderCollapse:'collapse', fontSize:11 }}>
                  <thead><tr style={{ borderBottom:'1.5px solid var(--line)' }}>
                    {['Tipo','Descripción','Receptor','Método','Frecuencia','Responsable','Estado','Acciones'].map(h=><th key={h} style={{ textAlign:'left', padding:'5px 8px', ...mono, fontSize:9, color:'var(--mute)', letterSpacing:'0.1em', fontWeight:600 }}>{h}</th>)}
                  </tr></thead>
                  <tbody>
                    {all.map(c=>{
                      const est = comEstados[c.id]||c.estado;
                      const tipoC = c.tipo==='inf_semanal'?'#89b4fa':c.tipo==='alerta_riesgo'?'#cc3333':c.tipo==='acta'?'#00C433':c.tipo==='notif_proveedor'?'#e89c2b':'#cba6f7';
                      const metC = c.metodo==='email'?'#89b4fa':c.metodo==='whatsapp'?'#00C433':c.metodo==='reunion'?'#e89c2b':'var(--ink-3)';
                      return (
                        <tr key={c.id} style={{ borderBottom:'1px solid var(--line)' }}>
                          <td style={{ padding:'6px 8px' }}>
                            <span style={{ ...mono, fontSize:9, color:tipoC, background:`${tipoC}15`, padding:'2px 6px', borderRadius:3 }}>{c.tipo.replace('_',' ')}</span>
                            {c.origen&&c.origen.startsWith('auto_')&&<span style={{ ...mono, fontSize:8, color:'var(--mute)', marginLeft:4 }}>auto</span>}
                          </td>
                          <td style={{ padding:'6px 8px', fontFamily:'Work Sans,sans-serif', fontSize:12, maxWidth:180 }}>{c.descripcion}</td>
                          <td style={{ padding:'6px 8px', fontFamily:'Work Sans,sans-serif', fontSize:11, color:'var(--ink-3)' }}>{c.receptor}</td>
                          <td style={{ padding:'6px 8px' }}><span style={{ ...mono, fontSize:9, color:metC, background:`${metC}15`, padding:'2px 6px', borderRadius:3 }}>{c.metodo}</span></td>
                          <td style={{ padding:'6px 8px', ...mono, fontSize:10, color:'var(--mute)' }}>{c.frecuencia}</td>
                          <td style={{ padding:'6px 8px', fontFamily:'Work Sans,sans-serif', fontSize:11, color:'var(--ink-3)' }}>{c.responsable}</td>
                          <td style={{ padding:'6px 8px' }}>
                            <button onClick={()=>setComEstados(s=>({...s,[c.id]:est==='pendiente'?'enviado':'pendiente'}))}
                                    style={{ ...mono, fontSize:9, padding:'2px 8px', borderRadius:3, cursor:'pointer', background:est==='enviado'?'#00FF4118':'#e89c2b18', border:`1px solid ${est==='enviado'?'#00FF4140':'#e89c2b40'}`, color:est==='enviado'?'#00C433':'#e89c2b' }}>
                              {est==='enviado'?'✓ Enviado':'○ Pendiente'}
                            </button>
                          </td>
                          <td style={{ padding:'6px 8px' }}>
                            <div style={{ display:'flex', gap:4 }}>
                              {c.email&&<a href={_buildMailto(c, project.nombre||project.name)} style={{ ...mono, fontSize:11, color:'#89b4fa', textDecoration:'none' }} title="Abrir en email">📧</a>}
                              <a href={_buildCalendarUrl(c, project.nombre||project.name)} target="_blank" rel="noreferrer" style={{ ...mono, fontSize:11, color:'#e89c2b', textDecoration:'none' }} title="Agregar a Google Calendar">📅</a>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {showNewCom && (
                  <div style={{ position:'fixed', inset:0, background:'#00000060', display:'flex', alignItems:'center', justifyContent:'center', zIndex:9999 }} onClick={()=>setShowNewCom(false)}>
                    <div style={{ background:'#fff', borderRadius:12, padding:24, minWidth:380, maxWidth:500 }} onClick={e=>e.stopPropagation()}>
                      <div style={{ ...mono, fontSize:10, color:'var(--mute)', letterSpacing:'0.1em', marginBottom:14 }}>+ NUEVA COMUNICACIÓN</div>
                      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10, marginBottom:10 }}>
                        {[['Tipo','tipo',['inf_semanal','alerta_riesgo','acta','notif_proveedor','hito']],['Método','metodo',['email','whatsapp','reunion','dashboard']],['Frecuencia','frecuencia',['evento','inmediato','semanal','quincenal','mensual']]].map(([label,key,opts])=>(
                          <div key={key}>
                            <label style={{ ...mono, fontSize:10, color:'var(--mute)', display:'block', marginBottom:4 }}>{label}</label>
                            <select value={newComForm[key]} onChange={e=>setNewComForm(f=>({...f,[key]:e.target.value}))} style={{ width:'100%', padding:'6px 8px', borderRadius:6, border:'1.5px solid var(--line)', fontFamily:'IBM Plex Mono,monospace', fontSize:11 }}>
                              {opts.map(o=><option key={o}>{o}</option>)}
                            </select>
                          </div>
                        ))}
                      </div>
                      {[['Descripción','descripcion','text'],['Responsable','responsable','text']].map(([label,key,type])=>(
                        <div key={key} style={{ marginBottom:10 }}>
                          <label style={{ ...mono, fontSize:10, color:'var(--mute)', display:'block', marginBottom:4 }}>{label}</label>
                          <input type={type} value={newComForm[key]||''} onChange={e=>setNewComForm(f=>({...f,[key]:e.target.value}))} style={{ width:'100%', padding:'6px 10px', borderRadius:6, border:'1.5px solid var(--line)', fontFamily:'Work Sans,sans-serif', fontSize:12, boxSizing:'border-box' }}/>
                        </div>
                      ))}
                      <div style={{ marginBottom:10 }}>
                        <label style={{ ...mono, fontSize:10, color:'var(--mute)', display:'block', marginBottom:4 }}>Receptor</label>
                        <div style={{ position:'relative' }}>
                          <input value={newComForm.receptor||''} onChange={e=>{ setNewComForm(f=>({...f,receptor:e.target.value})); setShPicker(e.target.value); }} placeholder="Nombre o buscar en directorio..." style={{ width:'100%', padding:'6px 10px', borderRadius:6, border:'1.5px solid var(--line)', fontFamily:'Work Sans,sans-serif', fontSize:12, boxSizing:'border-box' }}/>
                          {shPicker.length>1 && (
                            <div style={{ position:'absolute', top:'100%', left:0, right:0, background:'#fff', border:'1.5px solid var(--line)', borderRadius:8, zIndex:100, maxHeight:120, overflowY:'auto' }}>
                              {CONTACTS_DATA.filter(c=>c.name.toLowerCase().includes(shPicker.toLowerCase())).slice(0,5).map(c=>(
                                <div key={c.id} style={{ padding:'6px 10px', cursor:'pointer', fontFamily:'Work Sans,sans-serif', fontSize:12 }} onClick={()=>{ setNewComForm(f=>({...f,receptor:c.name,email:c.email})); setShPicker(''); }}>
                                  {c.name} <span style={{ color:'var(--mute)', fontSize:11 }}>· {c.type}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                      <div style={{ display:'flex', gap:8, justifyContent:'flex-end' }}>
                        <button onClick={()=>setShowNewCom(false)} style={{ padding:'6px 14px', ...mono, fontSize:10, background:'transparent', border:'1.5px solid var(--line)', borderRadius:6, cursor:'pointer' }}>Cancelar</button>
                        <button onClick={()=>{ setComData(prev=>[...(prev||[]),{...newComForm,id:'C'+Date.now(),origen:'manual',estado:'pendiente'}]); setShowNewCom(false); }} style={{ padding:'6px 14px', ...mono, fontSize:10, background:'#00FF4118', border:'1.5px solid #00FF4140', color:'#00C433', borderRadius:6, cursor:'pointer' }}>Guardar</button>
                      </div>
                    </div>
                  </div>
                )}
              </>
            );
          })()}
        </div>
      )}

      {/* MODO: RACI */}
      {mode==='raci' && (
        <div>
          {(() => {
            const raci = raciData || _buildRaciAuto(flat);
            const paqIds = Object.keys(raci.asignaciones);
            const personas = raci.personas;
            const sinR = paqIds.filter(pid=>!personas.some(p=>(raci.asignaciones[pid]||{})[p.id]==='R'));
            const mulA = paqIds.filter(pid=>personas.filter(p=>(raci.asignaciones[pid]||{})[p.id]==='A').length>1);
            const raciColor = {R:'#89b4fa',A:'#cba6f7',C:'#e89c2b',I:'#00C433'};

            return (
              <>
                <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10, marginBottom:12 }}>
                  {[{label:'PAQUETES',val:paqIds.length,color:'var(--ink)'},{label:'PERSONAS',val:personas.length,color:'#89b4fa'},{label:'SIN R',val:sinR.length,color:sinR.length>0?'#cc3333':'#00FF41'},{label:'MÚLTIPLE A',val:mulA.length,color:mulA.length>0?'#e89c2b':'#00FF41'}].map(c=>(
                    <div key={c.label} style={{ padding:'10px 12px', borderRadius:8, border:`1.5px solid ${c.color}30`, background:`${c.color}06` }}>
                      <div style={{ ...mono, fontSize:9, color:'var(--mute)', letterSpacing:'0.1em', marginBottom:4 }}>{c.label}</div>
                      <div style={{ ...mono, fontSize:18, color:c.color, fontWeight:700 }}>{c.val}</div>
                    </div>
                  ))}
                </div>

                <div style={{ display:'flex', gap:10, alignItems:'center', marginBottom:12 }}>
                  {[['matriz','Matriz'],['persona','Por persona']].map(([v,l])=>(
                    <button key={v} onClick={()=>setRaciView(v)} style={{ padding:'4px 12px', ...mono, fontSize:10, background:raciView===v?'#00FF41':'transparent', color:raciView===v?'#000':'var(--ink-3)', border:raciView===v?'1.5px solid #00FF41':'1.5px solid var(--line)', borderRadius:6, cursor:'pointer', fontWeight:raciView===v?700:400 }}>{l}</button>
                  ))}
                  {(sinR.length>0||mulA.length>0) ? <span style={{ ...mono, fontSize:10, color:'#cc3333', marginLeft:'auto' }}>⚠ {sinR.length>0?`${sinR.length} paq. sin R`:''}{sinR.length>0&&mulA.length>0?' · ':''}{mulA.length>0?`${mulA.length} con múltiple A`:''}</span>
                  : <span style={{ ...mono, fontSize:10, color:'#00C433', marginLeft:'auto' }}>✓ Matriz validada</span>}
                  <button onClick={()=>setShowAddPersona(true)} style={{ padding:'4px 10px', ...mono, fontSize:10, background:'transparent', border:'1.5px solid var(--line)', borderRadius:6, cursor:'pointer', color:'var(--ink-3)' }}>+ Persona</button>
                </div>

                {raciView==='matriz' && (
                  <div style={{ overflowX:'auto' }}>
                    <table style={{ borderCollapse:'collapse', fontSize:11, minWidth:500 }}>
                      <thead>
                        <tr style={{ borderBottom:'1.5px solid var(--line)' }}>
                          <th style={{ padding:'6px 8px', textAlign:'left', ...mono, fontSize:9, color:'var(--mute)', minWidth:140 }}>PAQUETE</th>
                          {personas.map(p=>(
                            <th key={p.id} style={{ padding:'6px 8px', textAlign:'center', ...mono, fontSize:9, color:'var(--mute)', minWidth:50 }}>
                              <div style={{ width:28, height:28, borderRadius:'50%', background:'#89b4fa20', border:'1.5px solid #89b4fa40', display:'flex', alignItems:'center', justifyContent:'center', margin:'0 auto 2px', ...mono, fontSize:10, fontWeight:700, color:'#89b4fa' }}>{p.iniciales}</div>
                              {p.rol}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {paqIds.map(pid=>{
                          const asgn = raci.asignaciones[pid]||{};
                          const sinRFila = !personas.some(p=>asgn[p.id]==='R');
                          const pNode = flat.find(n=>n.codigo===pid);
                          return (
                            <tr key={pid} style={{ borderBottom:'1px solid var(--line)', background:sinRFila?'#cc333306':'transparent' }}>
                              <td style={{ padding:'6px 8px', ...mono, fontSize:10 }}>
                                <span style={{ color:'var(--mute)' }}>{pid}</span>
                                <span style={{ fontFamily:'Work Sans,sans-serif', fontSize:11, marginLeft:6 }}>{pNode?.nombre||pid}</span>
                              </td>
                              {personas.map(p=>{
                                const role = asgn[p.id]||'';
                                return (
                                  <td key={p.id} style={{ padding:'6px 8px', textAlign:'center' }}>
                                    {role && <span style={{ display:'inline-flex', alignItems:'center', justifyContent:'center', width:22, height:22, borderRadius:4, background:`${raciColor[role]||'var(--line)'}25`, ...mono, fontSize:11, fontWeight:700, color:raciColor[role]||'var(--ink-3)' }}>{role}</span>}
                                  </td>
                                );
                              })}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    <div style={{ display:'flex', gap:12, marginTop:10, ...mono, fontSize:10, color:'var(--mute)' }}>
                      {Object.entries(raciColor).map(([k,c])=>(
                        <span key={k} style={{ display:'flex', alignItems:'center', gap:5 }}>
                          <span style={{ width:18, height:18, borderRadius:3, background:`${c}25`, border:`1px solid ${c}40`, display:'inline-flex', alignItems:'center', justifyContent:'center', ...mono, fontSize:10, fontWeight:700, color:c }}>{k}</span>
                          {k==='R'?'Responsable':k==='A'?'Aprobador':k==='C'?'Consultado':'Informado'}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {raciView==='persona' && (
                  <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(200px,1fr))', gap:12 }}>
                    {personas.map(p=>{
                      const myPaq = paqIds.filter(pid=>{ const r=(raci.asignaciones[pid]||{})[p.id]; return r&&r!==''; });
                      const counts = {R:0,A:0,C:0,I:0};
                      myPaq.forEach(pid=>{ const r=(raci.asignaciones[pid]||{})[p.id]; if(r) counts[r]++; });
                      const sobrecard = counts.R > 5;
                      return (
                        <div key={p.id} style={{ padding:'14px 16px', borderRadius:10, border:`1.5px solid ${sobrecard?'#e89c2b':'var(--line)'}`, background:sobrecard?'#e89c2b06':'var(--bg)' }}>
                          <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10 }}>
                            <div style={{ width:36, height:36, borderRadius:'50%', background:'#89b4fa20', border:'1.5px solid #89b4fa40', display:'flex', alignItems:'center', justifyContent:'center', ...mono, fontSize:12, fontWeight:700, color:'#89b4fa', flexShrink:0 }}>{p.iniciales}</div>
                            <div>
                              <div style={{ fontFamily:'Work Sans,sans-serif', fontSize:13, fontWeight:600, color:'var(--ink)' }}>{p.nombre}</div>
                              <div style={{ ...mono, fontSize:10, color:'var(--mute)' }}>{p.rol}</div>
                            </div>
                          </div>
                          <div style={{ display:'flex', gap:6, marginBottom:10 }}>
                            {Object.entries(counts).map(([k,v])=>(
                              <span key={k} style={{ ...mono, fontSize:10, color:raciColor[k], background:`${raciColor[k]}15`, padding:'2px 6px', borderRadius:3 }}>{k}:{v}</span>
                            ))}
                            {sobrecard && <span style={{ ...mono, fontSize:9, color:'#e89c2b' }}>Alta carga</span>}
                          </div>
                          <div style={{ display:'flex', flexDirection:'column', gap:3 }}>
                            {myPaq.map(pid=>{
                              const r=(raci.asignaciones[pid]||{})[p.id];
                              const pNode=flat.find(n=>n.codigo===pid);
                              return (
                                <div key={pid} style={{ display:'flex', gap:6, alignItems:'center' }}>
                                  <span style={{ width:18, height:18, borderRadius:3, background:`${raciColor[r]||'var(--line)'}25`, display:'inline-flex', alignItems:'center', justifyContent:'center', ...mono, fontSize:10, fontWeight:700, color:raciColor[r]||'var(--ink-3)', flexShrink:0 }}>{r}</span>
                                  <span style={{ fontFamily:'Work Sans,sans-serif', fontSize:11, color:'var(--ink-3)' }}>{pNode?.nombre||pid}</span>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {showAddPersona && (
                  <div style={{ position:'fixed', inset:0, background:'#00000060', display:'flex', alignItems:'center', justifyContent:'center', zIndex:9999 }} onClick={()=>setShowAddPersona(false)}>
                    <div style={{ background:'#fff', borderRadius:12, padding:24, minWidth:300 }} onClick={e=>e.stopPropagation()}>
                      <div style={{ ...mono, fontSize:10, color:'var(--mute)', letterSpacing:'0.1em', marginBottom:14 }}>+ AGREGAR PERSONA</div>
                      {[['Nombre','nombre'],['Rol','rol']].map(([label,key])=>(
                        <div key={key} style={{ marginBottom:10 }}>
                          <label style={{ ...mono, fontSize:10, color:'var(--mute)', display:'block', marginBottom:4 }}>{label}</label>
                          <input value={newPersonaForm[key]||''} onChange={e=>setNewPersonaForm(f=>({...f,[key]:e.target.value}))} style={{ width:'100%', padding:'6px 10px', borderRadius:6, border:'1.5px solid var(--line)', fontFamily:'Work Sans,sans-serif', fontSize:12, boxSizing:'border-box' }}/>
                        </div>
                      ))}
                      <div style={{ display:'flex', gap:8, justifyContent:'flex-end' }}>
                        <button onClick={()=>setShowAddPersona(false)} style={{ padding:'6px 14px', ...mono, fontSize:10, background:'transparent', border:'1.5px solid var(--line)', borderRadius:6, cursor:'pointer' }}>Cancelar</button>
                        <button onClick={()=>{ if(!newPersonaForm.nombre.trim()) return; const pid='p'+Date.now(); setRaciData(prev=>({ ...prev, personas:[...(prev?.personas||[]),{id:pid, nombre:newPersonaForm.nombre, rol:newPersonaForm.rol, iniciales:newPersonaForm.nombre.slice(0,2).toUpperCase()}] })); setShowAddPersona(false); setNewPersonaForm({nombre:'',rol:''}); }} style={{ padding:'6px 14px', ...mono, fontSize:10, background:'#00FF4118', border:'1.5px solid #00FF4140', color:'#00C433', borderRadius:6, cursor:'pointer' }}>Agregar</button>
                      </div>
                    </div>
                  </div>
                )}
              </>
            );
          })()}
        </div>
      )}

      {wizardOpen && <EdtWizard project={project} onClose={()=>setWizardOpen(false)}/>}
    </div>
  );
}

/* ============================================================
   EDT WIZARD — upload docs → Gentil preguntas → EDT real
   ============================================================ */
function EdtWizard({ project, onClose }) {
  const [step, setStep] = useSt('upload');
  const [files, setFiles] = useSt([]);
  const [transcribing, setTranscribing] = useSt(null);
  const [extracted, setExtracted] = useSt(null);
  const [questions, setQuestions] = useSt([]);
  const [answers, setAnswers] = useSt({});
  const [edtResult, setEdtResult] = useSt(null);
  const [err, setErr] = useSt('');

  const k = window.__API_KEY__ || '';
  const b = (window.__API_BASE__ || '').replace(/\/$/,'');
  const hdr = {'Content-Type':'application/json', ...(k?{'X-API-Key':k}:{})};

  const apiPost = async (path, body) => {
    const r = await fetch(`${b}${path}`, {method:'POST', headers:hdr, body:JSON.stringify(body)});
    if(!r.ok) throw new Error(await r.text());
    return r.json();
  };

  const readText = (file) => new Promise((res,rej)=>{
    const fr = new FileReader();
    fr.onload = e => res({name:file.name, content:e.target.result});
    fr.onerror = rej;
    fr.readAsText(file,'utf-8');
  });

  const transcribeAudio = async (file) => {
    setTranscribing(file.name);
    const form = new FormData();
    form.append('file', file);
    const r = await fetch(`${b}/edt-onboarding/transcribe`, {
      method:'POST', headers: k?{'X-API-Key':k}:{}, body:form,
    });
    setTranscribing(null);
    if(!r.ok) throw new Error(`Whisper: ${(await r.text()).slice(0,120)}`);
    const {text} = await r.json();
    return {name:`[audio] ${file.name}`, content:text};
  };

  const addFiles = async (list) => {
    const AUDIO = /\.(mp3|mp4|m4a|wav|ogg|webm|mpeg|mpga)$/i;
    for(const f of list) {
      try {
        const doc = (AUDIO.test(f.name)||f.type.startsWith('audio/'))
          ? await transcribeAudio(f)
          : await readText(f);
        setFiles(p=>[...p.filter(x=>x.name!==doc.name), doc]);
      } catch(e) { setErr(`${f.name}: ${e.message}`); }
    }
  };

  const runAnalysis = async () => {
    if(!files.length) return;
    setErr(''); setStep('analyzing');
    try {
      const pi = {name:project.nombre||project.name||'Proyecto', type:'audiovisual', area:project.area||'GP'};
      const ing = await apiPost('/api/edt-onboarding/ingest', {project:pi, documents:files});
      setExtracted(ing.extracted);
      const qr = await apiPost('/api/edt-onboarding/questions', {project:pi, extracted:ing.extracted, gaps:ing.gaps||[]});
      setQuestions(qr.questions||[]);
      setAnswers({});
      setStep('questions');
    } catch(e) { setErr(e.message.slice(0,200)); setStep('upload'); }
  };

  const runSynthesize = async () => {
    setErr(''); setStep('synthesizing');
    try {
      const pi = {name:project.nombre||project.name||'Proyecto', type:'audiovisual', area:project.area||'GP'};
      const r = await apiPost('/api/edt-onboarding/synthesize', {project:pi, extracted, answers});
      setEdtResult(r); setStep('done');
    } catch(e) { setErr(e.message.slice(0,200)); setStep('questions'); }
  };

  const mn = {fontFamily:'IBM Plex Mono, monospace'};
  const F = '#00FF41';

  const stepLabel = {upload:'1 · DOCUMENTOS', analyzing:'1 · DOCUMENTOS', questions:'2 · PREGUNTAS', synthesizing:'2 · PREGUNTAS', done:'3 · EDT LISTO'}[step]||'';

  return (
    <div style={{position:'fixed',inset:0,zIndex:3000,background:'rgba(0,0,0,0.75)',display:'flex',alignItems:'center',justifyContent:'center'}}
         onClick={onClose}>
      <div style={{width:'min(620px,95vw)',maxHeight:'88vh',overflowY:'auto',
                   background:'var(--surface)',borderRadius:16,border:'1.5px solid var(--line)',
                   boxShadow:'0 24px 64px rgba(0,0,0,0.6)',display:'flex',flexDirection:'column'}}
           onClick={e=>e.stopPropagation()}>

        {/* Header */}
        <div style={{display:'flex',alignItems:'center',gap:10,padding:'16px 22px 12px',borderBottom:'1.5px solid var(--line)'}}>
          <span style={{...mn,fontSize:9,letterSpacing:'0.14em',color:F,background:'#00FF4115',padding:'3px 10px',borderRadius:4}}>WIZARD EDT</span>
          <span style={{...mn,fontSize:11,color:'var(--mute)',flex:1,letterSpacing:'0.06em'}}>{stepLabel}</span>
          <button onClick={onClose} style={{background:'transparent',border:'none',color:'var(--mute)',fontSize:20,cursor:'pointer',padding:'0 4px',lineHeight:1}}>×</button>
        </div>

        <div style={{padding:'22px',flex:1}}>

          {/* UPLOAD */}
          {step==='upload' && (<>
            <p style={{...mn,fontSize:11,color:'var(--mute)',marginBottom:14,lineHeight:1.6}}>
              Sube briefs, actas, cronogramas, presupuestos, WhatsApps, audios — lo que tengas.
              Gentil analiza y construye el EDT automáticamente.
            </p>
            <div onDragOver={e=>e.preventDefault()}
                 onDrop={e=>{e.preventDefault();addFiles([...e.dataTransfer.files]);}}
                 onClick={()=>{const i=document.createElement('input');i.type='file';i.multiple=true;i.onchange=e=>addFiles([...e.target.files]);i.click();}}
                 style={{border:`2px dashed ${files.length?F:'var(--line)'}`,borderRadius:12,padding:'28px 16px',
                         textAlign:'center',cursor:'pointer',background:files.length?'#00FF4106':'var(--bg)',transition:'all 0.2s'}}>
              {transcribing
                ? <div style={{...mn,fontSize:11,color:F}}>🎙️ Transcribiendo: {transcribing}…</div>
                : (<>
                    <div style={{fontSize:26,marginBottom:6}}>📂</div>
                    <div style={{...mn,fontSize:11,color:'var(--ink-3)',letterSpacing:'0.06em'}}>Arrastra aquí o clic para seleccionar</div>
                    <div style={{...mn,fontSize:10,color:'var(--mute)',marginTop:3}}>TXT · MD · CSV · DOCX · MP3 · WAV · M4A · WebM (audio → Whisper)</div>
                  </>)}
            </div>
            {files.length>0 && (
              <div style={{marginTop:10}}>
                {files.map((f,i)=>(
                  <div key={i} style={{display:'flex',alignItems:'center',gap:8,padding:'5px 10px',
                                       borderRadius:6,marginBottom:3,background:'var(--bg)',border:'1px solid var(--line)'}}>
                    <span style={{fontSize:13}}>{f.name.startsWith('[audio]')?'🎙️':'📄'}</span>
                    <span style={{...mn,fontSize:10,flex:1,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',color:'var(--ink)'}}>{f.name}</span>
                    <span style={{...mn,fontSize:9,color:'var(--mute)'}}>{(f.content.length/1024).toFixed(0)}KB</span>
                    <button onClick={()=>setFiles(p=>p.filter((_,j)=>j!==i))}
                      style={{background:'transparent',border:'none',color:'var(--mute)',cursor:'pointer',fontSize:14,lineHeight:1}}>×</button>
                  </div>
                ))}
              </div>
            )}
            {err && <div style={{...mn,fontSize:10,color:'#f38ba8',marginTop:8,padding:'6px 10px',borderRadius:4,background:'#f38ba808'}}>{err}</div>}
            <button onClick={runAnalysis} disabled={!files.length}
              style={{marginTop:18,width:'100%',padding:'11px',...mn,fontSize:12,letterSpacing:'0.1em',fontWeight:700,
                      background:files.length?F:'var(--line)',color:files.length?'#000':'var(--mute)',
                      border:'none',borderRadius:8,cursor:files.length?'pointer':'default'}}>
              ANALIZAR CON GENTIL →
            </button>
          </>)}

          {/* LOADING */}
          {(step==='analyzing'||step==='synthesizing') && (
            <div style={{textAlign:'center',padding:'48px 0'}}>
              <div style={{...mn,fontSize:12,color:F,letterSpacing:'0.1em',marginBottom:8}}>
                {step==='analyzing'?'GENTIL LEYENDO DOCUMENTOS…':'CONSTRUYENDO EDT…'}
              </div>
              <div style={{...mn,fontSize:10,color:'var(--mute)'}}>
                {step==='analyzing'?`${files.length} docs · extrayendo fases, hitos, riesgos, stakeholders`:'Sintetizando respuestas → árbol EDT + riesgos + hitos'}
              </div>
            </div>
          )}

          {/* QUESTIONS */}
          {step==='questions' && (<>
            <p style={{...mn,fontSize:11,color:F,marginBottom:14}}>
              Gentil tiene {questions.length} preguntas · Responde las que puedas (el resto queda pendiente)
            </p>
            {questions.map((q,i)=>(
              <div key={q.key} style={{marginBottom:14,padding:'12px 14px',borderRadius:10,
                                       border:'1.5px solid var(--line)',background:'var(--bg)'}}>
                <div style={{...mn,fontSize:9,letterSpacing:'0.12em',color:F,marginBottom:4}}>
                  PREGUNTA {i+1}/{questions.length}
                </div>
                <div style={{fontFamily:'Work Sans,system-ui,sans-serif',fontSize:14,fontWeight:500,
                             lineHeight:1.5,marginBottom:6}}>{q.question}</div>
                <div style={{...mn,fontSize:10,color:'var(--mute)',marginBottom:8}}>¿Por qué? {q.why_asking}</div>
                <textarea value={answers[q.key]||''}
                  onChange={e=>setAnswers(p=>({...p,[q.key]:e.target.value}))}
                  placeholder="Tu respuesta (opcional)"
                  style={{width:'100%',minHeight:56,padding:'8px 10px',borderRadius:6,border:'1.5px solid var(--line)',
                          background:'var(--surface)',fontFamily:'Work Sans,system-ui,sans-serif',fontSize:13,
                          color:'var(--ink)',resize:'vertical',boxSizing:'border-box'}}/>
              </div>
            ))}
            {err && <div style={{...mn,fontSize:10,color:'#f38ba8',padding:'6px 10px',borderRadius:4,background:'#f38ba808',marginBottom:8}}>{err}</div>}
            <button onClick={runSynthesize}
              style={{width:'100%',padding:'11px',...mn,fontSize:12,letterSpacing:'0.1em',fontWeight:700,
                      background:F,color:'#000',border:'none',borderRadius:8,cursor:'pointer'}}>
              GENERAR EDT →
            </button>
          </>)}

          {/* DONE */}
          {step==='done' && edtResult && (<>
            <div style={{...mn,fontSize:10,letterSpacing:'0.1em',color:F,background:'#00FF4115',
                         padding:'8px 14px',borderRadius:6,marginBottom:14}}>
              EDT GENERADO · {edtResult.summary?.total_tareas||0} tareas · {edtResult.summary?.total_hitos||0} hitos ·
              Confianza: {edtResult.summary?.confidence||'—'}
            </div>
            {(edtResult.edt_nodes||[]).slice(0,12).map((n,i)=>(
              <div key={i} style={{display:'flex',alignItems:'center',gap:8,padding:'5px 10px',
                                   paddingLeft:n.nivel===1?10:26,borderRadius:6,marginBottom:3,
                                   background:n.es_hito?'#00FF4108':'transparent',
                                   borderLeft:n.nivel===1?'3px solid #00C433':'3px solid transparent'}}>
                <span style={{...mn,fontSize:10,color:'#00C433',minWidth:36}}>{n.codigo}</span>
                <span style={{fontFamily:'Work Sans,system-ui,sans-serif',fontSize:13,flex:1}}>{n.nombre}</span>
                {n.es_hito&&<span style={{...mn,fontSize:9,color:'#00C433',background:'#00FF4118',padding:'2px 6px',borderRadius:3}}>★</span>}
                <span style={{...mn,fontSize:10,color:'var(--mute)'}}>{n.duracion_dias||0}d</span>
              </div>
            ))}
            {(edtResult.edt_nodes||[]).length>12 && (
              <div style={{...mn,fontSize:10,color:'var(--mute)',padding:'4px 10px'}}>… {(edtResult.edt_nodes||[]).length-12} nodos más</div>
            )}
            {(edtResult.pending_panels||[]).length>0 && (
              <div style={{marginTop:10,...mn,fontSize:10,color:'var(--mute)',padding:'8px 12px',borderRadius:6,border:'1px dashed var(--line)'}}>
                Pendientes: {edtResult.pending_panels.join(' · ')}
              </div>
            )}
            <button onClick={onClose}
              style={{marginTop:18,width:'100%',padding:'11px',...mn,fontSize:12,letterSpacing:'0.1em',fontWeight:700,
                      background:F,color:'#000',border:'none',borderRadius:8,cursor:'pointer'}}>
              CERRAR Y VER EDT ↗
            </button>
          </>)}

        </div>
      </div>
    </div>
  );
}

/* ============================================================
   CURVA S VIEWER — ejecución planificada vs real · #00FF41
   ============================================================ */
function CurvaSViewer({ project }) {
  const weeks = 12;
  const pct = project.pct_ejecutado || 0;
  const weekNow = Math.max(1, Math.round(weeks * (pct / 100) * 1.2));

  const planned = Array.from({length:weeks+1}, (_,i)=>{
    const t = i/weeks;
    return Math.round(100*(3*t*t - 2*t*t*t));
  });
  const actual = Array.from({length:weeks+1}, (_,i)=>{
    if(i > weekNow) return null;
    const t = i/weeks;
    const base = Math.round(100*(3*t*t - 2*t*t*t));
    const dev = i===weekNow ? pct : Math.min(pct, base + (i%3===0?2:-1));
    return Math.max(0, Math.min(100, dev));
  });

  const W=520, H=180, padL=38, padB=28, padT=14, padR=16;
  const iW=W-padL-padR, iH=H-padT-padB;
  const toX=i=>padL+(i/weeks)*iW;
  const toY=v=>padT+iH-(v/100)*iH;
  const plannedPath=planned.map((v,i)=>`${i===0?'M':'L'}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
  const actualPts=actual.filter(v=>v!==null);
  const actualPath=actualPts.map((v,i)=>`${i===0?'M':'L'}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
  const cx=toX(weekNow), cy=toY(pct);
  const mono={ fontFamily:'IBM Plex Mono, monospace' };

  return (
    <div style={{ paddingBottom:16 }}>
      <div style={{ display:'flex', gap:20, marginBottom:12, alignItems:'center' }}>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <svg width="24" height="2"><line x1="0" y1="1" x2="24" y2="1" stroke="#00FF41" strokeWidth="2.5"/></svg>
          <span style={{ ...mono, fontSize:11, color:'var(--ink-3)' }}>Real (ejecución)</span>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <svg width="24" height="2"><line x1="0" y1="1" x2="24" y2="1" stroke="var(--line-2)" strokeWidth="1.5" strokeDasharray="4,3"/></svg>
          <span style={{ ...mono, fontSize:11, color:'var(--ink-3)' }}>Planificado</span>
        </div>
        <span style={{ marginLeft:'auto', ...mono, fontSize:12, color:'#00C433', fontWeight:700 }}>
          {pct}% EJECUTADO
        </span>
      </div>

      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display:'block', overflow:'visible' }}>
        {[0,25,50,75,100].map(v=>(
          <g key={v}>
            <line x1={padL} x2={W-padR} y1={toY(v)} y2={toY(v)} stroke="var(--line)" strokeWidth="0.6"/>
            <text x={padL-6} y={toY(v)+4} textAnchor="end" fontSize="9"
                  fontFamily="IBM Plex Mono, monospace" fill="#8a8a8a">{v}%</text>
          </g>
        ))}
        {Array.from({length:weeks+1},(_,i)=> i%3===0 && (
          <text key={i} x={toX(i)} y={H-4} textAnchor="middle" fontSize="9"
                fontFamily="IBM Plex Mono, monospace" fill="#8a8a8a">S{i}</text>
        ))}
        {/* Hoy */}
        <line x1={cx} x2={cx} y1={padT} y2={H-padB} stroke="var(--line-2)" strokeWidth="1" strokeDasharray="3,3"/>
        <text x={cx+4} y={padT+10} fontSize="8" fontFamily="IBM Plex Mono, monospace" fill="#8a8a8a">HOY</text>
        {/* Planificado */}
        <path d={plannedPath} fill="none" stroke="#d0d0cc" strokeWidth="1.5" strokeDasharray="5,4"/>
        {/* Área real */}
        <path d={`${actualPath} L${toX(Math.min(weekNow,weeks)).toFixed(1)},${toY(0).toFixed(1)} L${toX(0)},${toY(0).toFixed(1)} Z`}
              fill="#00FF41" fillOpacity="0.07"/>
        {/* Línea real #00FF41 */}
        <path d={actualPath} fill="none" stroke="#00FF41" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
        {/* Punto actual */}
        <circle cx={cx} cy={cy} r="5" fill="#00FF41"/>
        <circle cx={cx} cy={cy} r="9" fill="none" stroke="#00FF41" strokeWidth="1.5" strokeOpacity="0.35"/>
        <text x={cx+13} y={cy+4} fontSize="11" fontFamily="IBM Plex Mono, monospace" fill="#00C433" fontWeight="700">
          {pct}%
        </text>
      </svg>

      <div style={{ marginTop:12, padding:'8px 14px', borderRadius:8,
                    background:'var(--bg)', ...mono, fontSize:10,
                    color:'var(--mute)', letterSpacing:'0.06em' }}>
        CURVA S · ACUMULADO SEMANAL · {weeks} SEMANAS · La Falla D.F. · Gentil monitorea desviaciones
      </div>
    </div>
  );
}

/* ============================================================
   DASHBOARD DE PROYECTOS — modal grande
   ============================================================ */
function ProjectsDashboard({ open, onClose }){
  const [sel, setSel] = useSt(null);
  const [projects, setProjects] = useSt([]);
  const [loading, setLoading] = useSt(false);
  const [newProj, setNewProj] = useSt(false);
  const [activeTab, setActiveTab] = useSt('resumen');

  useEff(()=>{
    if(!open) return;
    const h = (e) => {
      if(e.key==='Escape'){
        if(sel) setSel(null);
        else onClose();
      }
    };
    window.addEventListener('keydown', h);
    return ()=> window.removeEventListener('keydown', h);
  },[open, sel, onClose]);

  useEff(()=>{
    if(!open) return;
    setLoading(true);
    const k = window.__API_KEY__ || '';
    const b = (window.__API_BASE__ || '').replace(/\/$/,'');
    fetch(`${b}/projects`, k ? {headers:{'X-API-Key':k}} : {})
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => setProjects(data))
      .catch(() => setProjects(PROJECTS_DATA.map((p,idx) => ({
        id: idx+1, codigo: p.id, nombre: p.name||p.nombre, area: p.area,
        presupuesto: 0, ejecutado: 0, pct_ejecutado: 0, estado: 'activo',
        entregables: (p.entregables||[]).map((e,i)=>({id:i+1, titulo:e.t||e.titulo, completado:e.done||e.completado||false, orden:i})),
        docs: p.docs||[],
      }))))
      .finally(() => setLoading(false));
  },[open]);

  if(!open) return null;

  const fmtCOP = (n) => {
    if(!n) return '—';
    return n >= 1e6 ? `${(n/1e6).toFixed(0)}M COP` : `${Math.round(n/1e3)}K COP`;
  };
  const project = sel != null ? projects.find(p=>p.id===sel) : null;
  const addProject = (proj) => setProjects(prev => [...prev, proj]);

  return (
    <>
      <div className="proj-scrim" onClick={onClose}>
        <div className="proj-box" onClick={e=>e.stopPropagation()}>
          <div className="proj-hd">
            <div>
              <div className="proj-eye">DASHBOARD DE PROYECTOS · LA FALLA D.F.</div>
              <h2 className="proj-title">{project ? project.nombre : <>Proyectos <em>activos</em></>}</h2>
            </div>
            {project && <button className="proj-back" onClick={()=>setSel(null)}>← Volver al listado</button>}
            {!project && !loading && (
              <button className="proj-new-btn" onClick={e=>{e.stopPropagation(); setNewProj(true);}}>+ Añadir proyecto</button>
            )}
            <button className="proj-close" onClick={()=>{ if(sel) setSel(null); else onClose(); }}>×</button>
          </div>

          {loading && <div className="proj-loading">Cargando proyectos…</div>}

          {!loading && !project && (
            <div className="proj-grid">
              {projects.length === 0 && (
                <div className="proj-empty">No hay proyectos activos · Haz clic en <strong>+ Añadir proyecto</strong> para comenzar</div>
              )}
              {projects.map(p => {
                const done = p.entregables.filter(e=>e.completado).length;
                const total = p.entregables.length;
                const pct = total > 0 ? Math.round(done/total*100) : Math.round(p.pct_ejecutado||0);
                return (
                  <button key={p.id} className="proj-card" onClick={()=>{setSel(p.id);setActiveTab('resumen');}}>
                    <div className="proj-card-hd">
                      <span className="proj-card-area">{p.area}</span>
                      <span className="proj-card-budget">{fmtCOP(p.presupuesto)}</span>
                    </div>
                    <div className="proj-card-name">{p.nombre}</div>
                    <div className="proj-card-bar">
                      <div className="proj-card-fill" style={{width:pct+'%'}}/>
                    </div>
                    <div className="proj-card-meta">
                      <span>{done}/{total} entregables</span>
                      <span className="proj-card-pct num-mono">{pct}%</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {!loading && project && (
            <div className="proj-detail">
              {/* Tab bar — RESUMEN | EDT | CURVA S */}
              <div style={{ display:'flex', gap:0, borderBottom:'1.5px solid var(--line)',
                            marginBottom:18, marginTop:2 }}>
                {[['resumen','RESUMEN'],['edt','EDT']].map(([id,label])=>(
                  <button key={id} onClick={()=>setActiveTab(id)} style={{
                    padding:'8px 20px', fontSize:11, letterSpacing:'0.1em',
                    fontFamily:'IBM Plex Mono, monospace', fontWeight: activeTab===id ? 700 : 400,
                    background:'transparent', border:'none', cursor:'pointer',
                    borderBottom: activeTab===id ? '2.5px solid #00FF41' : '2.5px solid transparent',
                    color: activeTab===id ? 'var(--ink)' : 'var(--mute)',
                    marginBottom:'-1.5px',
                  }}>{label}</button>
                ))}
              </div>

              {activeTab==='resumen' && (
                <>
                  <div className="proj-det-row">
                    <div className="proj-det-block">
                      <h4>Presupuesto</h4>
                      <div className="proj-det-budget">
                        <div className="proj-det-big num-mono">{fmtCOP(project.presupuesto)}</div>
                        <div className="proj-det-spent">Ejecutado: <strong>{fmtCOP(project.ejecutado)} ({project.pct_ejecutado}%)</strong></div>
                      </div>
                    </div>
                    <div className="proj-det-block">
                      <h4>Área responsable</h4>
                      <div className="proj-det-area">{project.area}</div>
                    </div>
                  </div>

                  <div className="proj-det-block">
                    <h4>Entregables <span className="tiny">{project.entregables.filter(e=>e.completado).length}/{project.entregables.length}</span></h4>
                    <ul className="proj-checklist">
                      {project.entregables.map((e,i)=>(
                        <li key={e.id||i} className={e.completado?'done':''}>
                          <span className="proj-check">{e.completado ? '✓' : '○'}</span>
                          <span>{e.titulo}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {(project.docs||[]).length > 0 && (
                    <div className="proj-det-block">
                      <h4>Documentación vinculada</h4>
                      <div className="proj-docs">
                        {project.docs.map((d,i)=>(
                          <div key={i} className="proj-doc">
                            <span className="proj-doc-ico">📄</span>
                            <span>{d}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}

              {activeTab==='edt' && <EdtViewer project={project}/>}
            </div>
          )}
        </div>
      </div>
      <NewProjectModal open={newProj} onClose={()=>setNewProj(false)} onSave={addProject}/>
    </>
  );
}

/* Export to window */
Object.assign(window, {
  FAB, CapturaModal, StakeholderModal, Sidebar, ProjectsDashboard, NewProjectModal, EdtWizard,
  INBOX_ITEMS, CONTACTS_DATA, PROJECTS_DATA,
});
