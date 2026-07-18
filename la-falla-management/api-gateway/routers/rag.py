"""RAG — Retrieval Augmented Generation for the Centro de Mando.

Embeddings come from a configurable provider (default OpenAI `text-embedding-3-small`); each vector is
stored as a JSONB float array and similarity is computed in-app (cosine in Python). This deliberately
does NOT use pgvector: the production Postgres has the `vector` extension registered but its
`$libdir/vector` library is missing, so every `::vector` insert/query errors (change wire-document-rag).
"""
import json
import logging
import math
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text

router = APIRouter(prefix="/rag", tags=["rag"])
log = logging.getLogger(__name__)

EMBED_PROVIDER = os.environ.get("EMBED_PROVIDER", "openai").lower()
EMBED_MODEL    = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
CHUNK_SIZE     = 600   # chars per chunk
CHUNK_OVERLAP  = 80    # chars of overlap between chunks
# Cosine floor below which a chunk is treated as irrelevant (conservative for a small corpus).
MIN_SIMILARITY = float(os.environ.get("RAG_MIN_SIMILARITY", "0.15"))


def _db_url() -> str:
    # Read at call time (not import) so tests can point DATABASE_URL at an isolated DB.
    return os.environ.get("DATABASE_URL", "")


def _engine():
    return create_engine(_db_url(), pool_pre_ping=True)


# ─── Embeddings (configurable provider) ──────────────────────────────────────

def get_embedding(text_in: str) -> list[float]:
    """Embed `text_in` with the configured provider (default OpenAI text-embedding-3-small)."""
    provider = EMBED_PROVIDER
    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY no configurada")
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.embeddings.create(model=EMBED_MODEL, input=text_in)
        return list(resp.data[0].embedding)
    if provider == "ollama":
        import requests
        url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        r = requests.post(f"{url}/api/embed", json={"model": EMBED_MODEL, "input": text_in}, timeout=30)
        r.raise_for_status()
        embs = r.json().get("embeddings", [[]])
        if not embs or not embs[0]:
            raise ValueError("Ollama returned empty embedding")
        return list(embs[0])
    raise ValueError(f"EMBED_PROVIDER desconocido: {provider!r}")


# ─── Chunking ────────────────────────────────────────────────────────────────

def chunk_text(text_in: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks to preserve context across boundaries."""
    if not text_in or not text_in.strip():
        return []
    paragraphs = [p.strip() for p in text_in.split("\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 1 <= size:
            current = (current + "\n" + para).strip()
        else:
            if current:
                chunks.append(current)
            tail = current[-overlap:] if len(current) > overlap else current
            current = (tail + "\n" + para).strip()
    if current:
        chunks.append(current)
    return chunks


# ─── Store / search (JSONB + in-app cosine, no pgvector) ─────────────────────

def embed_and_store(
    source_type: str,
    source_name: str,
    doc_text: str,
    source_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> int:
    """Chunk, embed and persist `doc_text` into document_chunks (replace-on-reingest => idempotent).
    Returns the number of chunks stored."""
    if not _db_url():
        raise ValueError("DATABASE_URL no configurada")
    chunks = chunk_text(doc_text)
    if not chunks:
        return 0
    engine = _engine()
    is_pg = engine.dialect.name == "postgresql"
    # Postgres needs an explicit text->jsonb cast on insert; SQLite (tests) stores the JSON string.
    emb_expr  = "CAST(:emb AS JSONB)"  if is_pg else ":emb"
    meta_expr = "CAST(:meta AS JSONB)" if is_pg else ":meta"
    stored = 0
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM document_chunks WHERE source_type = :st AND source_name = :sn"),
            {"st": source_type, "sn": source_name},
        )
        for i, chunk in enumerate(chunks):
            try:
                emb = get_embedding(chunk)
            except Exception as exc:  # one bad chunk must not abort the rest
                log.warning("RAG embed error on chunk %d of %s: %s", i, source_name, exc)
                continue
            conn.execute(text(f"""
                INSERT INTO document_chunks
                    (source_type, source_id, source_name, chunk_index, chunk_text, embedding, metadata)
                VALUES
                    (:st, :sid, :sn, :idx, :txt, {emb_expr}, {meta_expr})
            """), {
                "st":  source_type,
                "sid": source_id,
                "sn":  source_name,
                "idx": i,
                "txt": chunk,
                "emb": json.dumps(emb),
                "meta": json.dumps(metadata or {}),
            })
            stored += 1
    return stored


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _as_vector(raw) -> list[float]:
    """Coerce a stored embedding (JSONB list from psycopg2, or a JSON string from SQLite) to floats."""
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    try:
        return [float(x) for x in raw]
    except Exception:
        return []


def similarity_search(
    query: str,
    limit: int = 5,
    source_type: Optional[str] = None,
    min_similarity: Optional[float] = None,
) -> list[dict]:
    """Top-`limit` chunks by in-app cosine similarity to `query`, above the similarity floor."""
    if not _db_url():
        return []
    floor = MIN_SIMILARITY if min_similarity is None else float(min_similarity)
    q_emb = get_embedding(query)
    engine = _engine()
    with engine.connect() as conn:
        where = "WHERE embedding IS NOT NULL"
        params: dict = {}
        if source_type:
            where += " AND source_type = :st"
            params["st"] = source_type
        rows = conn.execute(text(f"""
            SELECT source_type, source_name, chunk_index, chunk_text, embedding
            FROM document_chunks
            {where}
        """), params).fetchall()
    scored: list[dict] = []
    for r in rows:
        m = dict(r._mapping)
        sim = _cosine(q_emb, _as_vector(m.get("embedding")))
        if sim >= floor:
            scored.append({
                "source_type": m["source_type"],
                "source_name": m["source_name"],
                "chunk_index": m["chunk_index"],
                "chunk_text": m["chunk_text"],
                "similarity": round(sim, 4),
            })
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:limit]


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
    """Chunk + embed a text. Use it to index documents manually."""
    if not _db_url():
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
    """Semantic search over indexed documents. Returns the most relevant chunks."""
    if not _db_url():
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
    """RAG index statistics."""
    if not _db_url():
        raise HTTPException(503, "DATABASE_URL no configurada.")
    engine = _engine()
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
