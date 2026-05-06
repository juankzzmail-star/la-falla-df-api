"""RAG — Retrieval Augmented Generation usando pgvector + Ollama nomic-embed-text."""
import json
import os
import textwrap
from typing import Optional

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text

router = APIRouter(prefix="/rag", tags=["rag"])

DATABASE_URL = os.environ.get("DATABASE_URL", "")
OLLAMA_URL   = os.environ.get("OLLAMA_URL", "http://10.0.1.27:11434")
EMBED_MODEL  = "nomic-embed-text"
CHUNK_SIZE   = 600   # chars per chunk
CHUNK_OVERLAP = 80   # chars of overlap between chunks


# ─── Core helpers ─────────────────────────────────────────────────────────────

def get_embedding(text: str) -> list[float]:
    """Genera embedding de 768 dims con nomic-embed-text vía Ollama."""
    r = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": text},
        timeout=30,
    )
    r.raise_for_status()
    embs = r.json().get("embeddings", [[]])
    if not embs or not embs[0]:
        raise ValueError("Ollama returned empty embedding")
    return embs[0]


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Divide texto en chunks con overlap para preservar contexto en fronteras."""
    if not text.strip():
        return []
    # Split on paragraph breaks first, then merge into chunks
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 1 <= size:
            current = (current + "\n" + para).strip()
        else:
            if current:
                chunks.append(current)
            # Start new chunk with overlap from previous
            tail = current[-overlap:] if len(current) > overlap else current
            current = (tail + "\n" + para).strip()
    if current:
        chunks.append(current)
    return chunks


def embed_and_store(
    source_type: str,
    source_name: str,
    doc_text: str,
    source_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> int:
    """Chunkea texto, genera embeddings y los guarda en document_chunks. Retorna N chunks insertados."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL no configurada")
    chunks = chunk_text(doc_text)
    if not chunks:
        return 0
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM document_chunks
            WHERE source_type = :st AND source_name = :sn
        """), {"st": source_type, "sn": source_name})

        stored = 0
        for i, chunk in enumerate(chunks):
            try:
                emb = get_embedding(chunk)
                # Both ::vector and ::jsonb cast with literal to avoid SQLAlchemy :param:: conflict
                emb_literal  = "'" + "[" + ",".join(str(v) for v in emb) + "]" + "'::vector"
                meta_literal = "'" + json.dumps(metadata or {}).replace("'", "''") + "'::jsonb"
                conn.execute(text(f"""
                    INSERT INTO document_chunks
                        (source_type, source_id, source_name, chunk_index, chunk_text, embedding, metadata)
                    VALUES
                        (:st, :sid, :sn, :idx, :txt, {emb_literal}, {meta_literal})
                """), {
                    "st":  source_type,
                    "sid": source_id,
                    "sn":  source_name,
                    "idx": i,
                    "txt": chunk,
                })
                stored += 1
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("RAG chunk %d embed error: %s", i, exc)
    return stored


def similarity_search(query: str, limit: int = 5, source_type: Optional[str] = None) -> list[dict]:
    """Busca chunks relevantes por similitud coseno."""
    if not DATABASE_URL:
        return []
    emb = get_embedding(query)
    emb_literal = "'" + "[" + ",".join(str(v) for v in emb) + "]" + "'::vector"
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    with engine.connect() as conn:
        where = "WHERE source_type = :st" if source_type else ""
        params: dict = {"lim": limit}
        if source_type:
            params["st"] = source_type
        rows = conn.execute(text(f"""
            SELECT source_type, source_name, chunk_index, chunk_text,
                   1 - (embedding <=> {emb_literal}) AS similarity
            FROM document_chunks
            {where}
            ORDER BY embedding <=> {emb_literal}
            LIMIT :lim
        """), params).fetchall()
    return [dict(r._mapping) for r in rows]


# ─── Endpoints ────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    source_type: Optional[str] = None


class EmbedRequest(BaseModel):
    source_type: str
    source_name: str
    text: str
    source_id: Optional[str] = None
    metadata: Optional[dict] = None


@router.post("/embed")
def embed_document(req: EmbedRequest):
    """Chunkea y embede un texto. Úsalo para indexar documentos manualmente."""
    if not DATABASE_URL:
        raise HTTPException(503, "DATABASE_URL no configurada.")
    try:
        n = embed_and_store(
            source_type=req.source_type,
            source_name=req.source_name,
            doc_text=req.text,
            source_id=req.source_id,
            metadata=req.metadata,
        )
        return {"ok": True, "chunks_stored": n, "source": req.source_name}
    except Exception as e:
        raise HTTPException(500, f"Error generando embeddings: {str(e)[:200]}")


@router.post("/search")
def search_docs(req: SearchRequest):
    """Búsqueda semántica sobre documentos indexados. Retorna chunks más relevantes."""
    if not DATABASE_URL:
        raise HTTPException(503, "DATABASE_URL no configurada.")
    if not req.query.strip():
        raise HTTPException(400, "Query vacío.")
    try:
        results = similarity_search(req.query, limit=req.limit, source_type=req.source_type)
        return {"query": req.query, "results": results, "count": len(results)}
    except Exception as e:
        raise HTTPException(500, f"Error en búsqueda: {str(e)[:200]}")


@router.get("/stats")
def rag_stats():
    """Estadísticas del índice RAG."""
    if not DATABASE_URL:
        raise HTTPException(503, "DATABASE_URL no configurada.")
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT
                COUNT(*) AS total_chunks,
                COUNT(DISTINCT source_name) AS total_docs,
                COUNT(DISTINCT source_type) AS source_types,
                COUNT(*) FILTER (WHERE embedding IS NOT NULL) AS indexed
            FROM document_chunks
        """)).fetchone()
    return dict(row._mapping)
