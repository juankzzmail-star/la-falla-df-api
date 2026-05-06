from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from ..db import get_db
from ..models import Project, Deliverable, EdtNode, Risk
from ..schemas import EdtNodeCreate, EdtNodePatch, EdtNodeOut
from .edt_onboarding import call_llm

router = APIRouter(prefix="/projects", tags=["projects"])


class DeliverableOut(BaseModel):
    id: int
    titulo: str
    completado: bool
    orden: int

    class Config:
        from_attributes = True


class ProjectOut(BaseModel):
    id: int
    codigo: str
    nombre: str
    area: str
    presupuesto: float
    ejecutado: float
    pct_ejecutado: float
    estado: str
    entregables: List[DeliverableOut] = []
    docs: List[str] = []

    class Config:
        from_attributes = True


class ProjectCreate(BaseModel):
    codigo: str
    nombre: str
    area: str
    presupuesto: float
    ejecutado: float = 0.0
    estado: str = "activo"


class DeliverableCreate(BaseModel):
    titulo: str
    completado: bool = False
    orden: int = 0


class DeliverablePatch(BaseModel):
    completado: Optional[bool] = None
    titulo: Optional[str] = None


@router.get("", response_model=List[ProjectOut])
def list_projects(area: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Project)
    if area:
        q = q.filter(Project.area == area)
    projects = q.filter(Project.estado == "activo").all()
    result = []
    for p in projects:
        deliverables = db.query(Deliverable).filter(Deliverable.project_id == p.id).order_by(Deliverable.orden).all()
        pct = (p.ejecutado / p.presupuesto * 100) if p.presupuesto else 0
        result.append(ProjectOut(
            id=p.id, codigo=p.codigo, nombre=p.nombre, area=p.area,
            presupuesto=float(p.presupuesto), ejecutado=float(p.ejecutado),
            pct_ejecutado=round(pct, 1), estado=p.estado,
            entregables=[DeliverableOut.model_validate(d) for d in deliverables],
        ))
    return result


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Proyecto no encontrado")
    deliverables = db.query(Deliverable).filter(Deliverable.project_id == p.id).order_by(Deliverable.orden).all()
    pct = (p.ejecutado / p.presupuesto * 100) if p.presupuesto else 0
    return ProjectOut(
        id=p.id, codigo=p.codigo, nombre=p.nombre, area=p.area,
        presupuesto=float(p.presupuesto), ejecutado=float(p.ejecutado),
        pct_ejecutado=round(pct, 1), estado=p.estado,
        entregables=[DeliverableOut.model_validate(d) for d in deliverables],
    )


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    p = Project(**body.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return ProjectOut(
        id=p.id, codigo=p.codigo, nombre=p.nombre, area=p.area,
        presupuesto=float(p.presupuesto), ejecutado=float(p.ejecutado),
        pct_ejecutado=0.0, estado=p.estado, entregables=[],
    )


@router.post("/{project_id}/deliverables", response_model=DeliverableOut, status_code=201)
def add_deliverable(project_id: int, body: DeliverableCreate, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Proyecto no encontrado")
    d = Deliverable(project_id=project_id, **body.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@router.patch("/{project_id}/deliverables/{deliverable_id}", response_model=DeliverableOut)
def update_deliverable(project_id: int, deliverable_id: int, body: DeliverablePatch, db: Session = Depends(get_db)):
    d = db.get(Deliverable, deliverable_id)
    if not d or d.project_id != project_id:
        raise HTTPException(404, "Entregable no encontrado")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(d, k, v)
    db.commit()
    db.refresh(d)
    return d


# ─── EDT endpoints (Opción 3) ────────────────────────────────

@router.get("/{project_id}/edt")
def get_edt(project_id: int, db: Session = Depends(get_db)):
    """Retorna árbol EDT del proyecto."""
    if not db.get(Project, project_id):
        raise HTTPException(404, "Proyecto no encontrado")
    nodes = db.query(EdtNode).filter(EdtNode.project_id == project_id).order_by(EdtNode.nivel, EdtNode.codigo).all()
    if not nodes:
        raise HTTPException(404, "EDT no encontrada")
    # Build tree recursively
    node_map = {n.id: {
        "id": n.id, "project_id": n.project_id, "parent_id": n.parent_id,
        "codigo": n.codigo, "nivel": n.nivel, "nombre": n.nombre,
        "responsable": n.responsable or "", "descripcion_dict": n.descripcion_dict or "",
        "accountable": n.accountable or "", "consulted": n.consulted or [], "informed": n.informed or [],
        "predecesores": n.predecesores or [], "costo_estimado": float(n.costo_estimado or 0),
        "duracion_dias": n.duracion_dias or 0, "porcentaje_avance": n.porcentaje_avance or 0,
        "es_paquete_trabajo": n.es_paquete_trabajo, "es_hito": n.es_hito,
        "estado": n.estado, "alerta": n.alerta, "hijos": [],
        "costo_hijos_sum": 0.0, "num_hijos": 0
    } for n in nodes}
    roots = []
    for n in nodes:
        node = node_map[n.id]
        if n.parent_id and n.parent_id in node_map:
            node_map[n.parent_id]["hijos"].append(node)
            node_map[n.parent_id]["costo_hijos_sum"] += node["costo_estimado"]
            node_map[n.parent_id]["num_hijos"] += 1
        else:
            roots.append(node)
    return roots

def _transform_name(name: str) -> str:
    # Transformación silenciosa de verbos a sustantivos
    system = "Eres Gentil. Convierte la frase a un sustantivo/entregable sin verbos de acción. Ej: 'Instalar 30 equipos' -> '30 equipos instalados'. 'Filmar escena' -> 'Escena filmada'. Responde SOLO con la frase transformada."
    try:
        res = call_llm(system, name, max_tokens=100)
        # Limpiar si responde con comillas
        return res.strip().strip('"').strip("'")
    except Exception:
        return name

@router.post("/{project_id}/edt", response_model=EdtNodeOut, status_code=201)
def create_edt_node(project_id: int, body: EdtNodeCreate, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Proyecto no encontrado")
        
    # Transformacion silenciosa de verbos
    body.nombre = _transform_name(body.nombre)
    
    node = EdtNode(project_id=project_id, **body.model_dump())
    db.add(node)
    db.commit()
    db.refresh(node)
    return node

@router.patch("/{project_id}/edt/{node_id}", response_model=EdtNodeOut)
def update_edt_node(project_id: int, node_id: int, body: EdtNodePatch, db: Session = Depends(get_db)):
    node = db.get(EdtNode, node_id)
    if not node or node.project_id != project_id:
        raise HTTPException(404, "Nodo EDT no encontrado")
        
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == 'nombre' and v:
            v = _transform_name(v)
        setattr(node, k, v)
        
    db.commit()
    db.refresh(node)
    return node


@router.get("/{project_id}/raci")
def get_raci(project_id: int, db: Session = Depends(get_db)):
    """Retorna RACI generado desde responsables en EDT."""
    if not db.get(Project, project_id):
        raise HTTPException(404, "Proyecto no encontrado")
    nodes = db.query(EdtNode).filter(
        EdtNode.project_id == project_id,
        EdtNode.es_paquete_trabajo == True
    ).order_by(EdtNode.codigo).all()
    if not nodes:
        raise HTTPException(404, "EDT no encontrada")
    nombres = sorted(list({n.responsable for n in nodes if n.responsable} | 
                          {n.accountable for n in nodes if n.accountable}))
    personas = [{"id": p.lower().replace(" ", "-"), "nombre": p, "rol": "Equipo"} for p in nombres]
    pid_of = {p["nombre"]: p["id"] for p in personas}
    
    matriz = []
    for n in nodes:
        asig = {}
        if n.responsable in pid_of: asig[pid_of[n.responsable]] = "R"
        if n.accountable in pid_of: asig[pid_of[n.accountable]] = "A"
        for c in (n.consulted or []):
            if c in pid_of: asig[pid_of[c]] = "C"
        for i in (n.informed or []):
            if i in pid_of: asig[pid_of[i]] = "I"
            
        matriz.append({
            "codigo": n.codigo, 
            "nombre": n.nombre,
            "asignaciones": asig
        })
        
    return {"personas": personas, "matriz": matriz}


@router.get("/{project_id}/communications")
def get_communications(project_id: int, db: Session = Depends(get_db)):
    """Genera comunicaciones automáticas desde riesgos + hitos."""
    if not db.get(Project, project_id):
        raise HTTPException(404, "Proyecto no encontrado")
    risks = db.query(Risk).filter(Risk.project_id == project_id, Risk.nivel_riesgo >= 15).all()
    nodes = db.query(EdtNode).filter(EdtNode.project_id == project_id, EdtNode.es_hito == True).all()
    comms = [{"id": "auto-semanal", "tipo": "informe", "descripcion": "Informe semanal de avance",
              "receptor": "Equipo + GG", "metodo": "email", "frecuencia": "semanal",
              "responsable": "Director GP", "estado": "pendiente", "origen": "auto_cronograma"}]
    for r in risks:
        comms.append({"id": f"auto-riesgo-{r.id}", "tipo": "alerta",
                      "descripcion": f"Alerta riesgo crítico: {r.descripcion[:60]}",
                      "receptor": r.responsable or "GG", "metodo": "email",
                      "frecuencia": "inmediato", "responsable": "Director GP",
                      "estado": "pendiente", "origen": "auto_riesgo"})
    for n in nodes:
        comms.append({"id": f"auto-hito-{n.id}", "tipo": "hito",
                      "descripcion": f"Hito alcanzado: {n.nombre}",
                      "receptor": "GG + Equipo", "metodo": "email",
                      "frecuencia": "evento", "responsable": n.responsable or "Director GP",
                      "estado": "pendiente", "origen": "auto_hito"})
    return comms
