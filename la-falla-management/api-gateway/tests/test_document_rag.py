"""DB + API tests for the document RAG (change wire-document-rag).

Authored in the `api_gateway` package layout (CI/container). No network and no production Postgres:
embeddings are monkeypatched and the DB is an isolated **file**-SQLite (rag.py builds its own engine
from DATABASE_URL per call, so a file URL is shared across calls; in-memory would give each call its
own empty DB). The router emits portable SQL with a dialect-aware JSONB cast, so store/search logic is
exercised against SQLite here.

Covers tasks.md §6.2/§6.3/§6.4:
- embed -> store -> search, idempotent re-index (no duplicates), embedding persisted & parseable
- cosine orders by similarity; source_type filter; similarity floor
- anti-hallucination guard rejects an ungrounded amount
- analysis LLM must be a configured provider (default OpenAI; 503 if none)
- auth 401/403 on /rag/* and /strategy/ingest-resource (verify_key runs before the handler)
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FASTAPI_GM_API_KEY", "test-key-123")
os.environ.setdefault("FASTAPI_API_KEY", "test-key-123")
os.environ.setdefault("OPENAI_API_KEY", "test-openai")  # presence only; embeddings are monkeypatched

import pytest
from sqlalchemy import create_engine, text

from api_gateway.routers import rag as rag_mod
from api_gateway.routers import _guards

H = {"X-API-Key": "test-key-123"}

# Portable document_chunks schema (TEXT embedding/metadata; prod uses JSONB — rag.py casts per dialect).
_DDL = """
CREATE TABLE document_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_type TEXT NOT NULL,
  source_id   TEXT,
  source_name TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  chunk_text  TEXT NOT NULL,
  embedding   TEXT,
  metadata    TEXT,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def _fake_embed(text_in: str):
    """Deterministic 3-d vector so similarity is meaningful and stable (no OpenAI call)."""
    t = (text_in or "").lower()
    return [float(t.count("alfa") + 1), float(t.count("beta") + 1), float(len(t) % 7)]


@pytest.fixture()
def rag_db(tmp_path, monkeypatch):
    db = tmp_path / "rag.db"
    url = f"sqlite:///{db.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(text(_DDL))
    monkeypatch.setattr(rag_mod, "get_embedding", _fake_embed)
    return url


# ── Pure-logic guards / helpers ──────────────────────────────────────────────

def test_guard_grounded_and_ungrounded():
    src = "El presupuesto total es COP 600.000.000 para el programa de cine."
    assert _guards.value_is_grounded("COP 600.000.000", src) is True
    assert _guards.value_is_grounded("$600.000.000", src) is True   # digits match
    assert _guards.value_is_grounded("$999.999.999", src) is False
    assert _guards.value_is_grounded("", src) is True
    bad = _guards.ungrounded_amounts("Cita $999.999.999 y tambien COP 600.000.000", src)
    assert "$999.999.999" in bad
    assert all("600.000.000" not in b for b in bad)


def test_cosine_and_vector_coercion():
    assert rag_mod._cosine([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == pytest.approx(1.0)
    assert rag_mod._cosine([1.0, 0.0, 0.0], [0.0, 1.0, 0.0]) == pytest.approx(0.0)
    assert rag_mod._cosine([], [1.0]) == 0.0
    assert rag_mod._as_vector("[1, 2, 3]") == [1.0, 2.0, 3.0]   # JSON string (SQLite read)
    assert rag_mod._as_vector([1, 2]) == [1.0, 2.0]             # list (psycopg2 JSONB read)
    assert rag_mod._as_vector(None) == []


def test_chunk_text_nonempty_and_empty():
    chunks = rag_mod.chunk_text("\n".join(f"parrafo numero {i} con contenido" for i in range(8)))
    assert chunks and all(c.strip() for c in chunks)
    assert rag_mod.chunk_text("   ") == []


# ── Store / search against SQLite ────────────────────────────────────────────

def test_embed_store_idempotent_and_persisted(rag_db):
    n1 = rag_mod.embed_and_store("documento", "doc1.pdf", "alfa alfa contexto\nbeta texto", metadata={"k": "v"})
    assert n1 >= 1
    n2 = rag_mod.embed_and_store("documento", "doc1.pdf", "alfa de nuevo\nbeta beta", metadata={"k": "v2"})
    eng = create_engine(rag_db)
    with eng.connect() as c:
        total = c.execute(
            text("SELECT COUNT(*) FROM document_chunks WHERE source_name='doc1.pdf'")
        ).scalar()
        emb = c.execute(text("SELECT embedding FROM document_chunks LIMIT 1")).scalar()
    assert total == n2          # re-index replaced prior chunks (no duplication)
    assert rag_mod._as_vector(emb)  # embedding persisted and parseable


def test_similarity_orders_by_similarity(rag_db):
    rag_mod.embed_and_store("documento", "a", "alfa alfa alfa")
    rag_mod.embed_and_store("documento", "b", "beta beta beta")
    res = rag_mod.similarity_search("alfa alfa", limit=5, source_type="documento", min_similarity=0.0)
    assert res, "expected hits"
    sims = [r["similarity"] for r in res]
    assert sims == sorted(sims, reverse=True)
    assert res[0]["source_name"] == "a"   # the 'alfa' doc ranks above the 'beta' doc for an 'alfa' query


def test_similarity_source_type_filter_and_floor(rag_db):
    rag_mod.embed_and_store("documento", "d", "alfa")
    rag_mod.embed_and_store("otro", "o", "alfa")
    res = rag_mod.similarity_search("alfa", source_type="documento", min_similarity=0.0)
    assert {r["source_type"] for r in res} == {"documento"}
    # An impossible floor returns nothing.
    assert rag_mod.similarity_search("alfa", source_type="documento", min_similarity=1.1) == []


# ── Analysis provider selection (strategy) ───────────────────────────────────

def test_analysis_provider_default_openai_and_503(monkeypatch):
    from fastapi import HTTPException
    from api_gateway.routers import strategy as st
    monkeypatch.setattr(st, "ANALYSIS_PROVIDER", "openai")
    monkeypatch.setattr(st, "ANALYSIS_MODEL", "gpt-4o-mini")
    monkeypatch.setattr(st, "OPENAI_API_KEY", "x")
    monkeypatch.setattr(st, "GROQ_API_KEY", "")
    _client, model = st._analysis_client_model()
    assert model == "gpt-4o-mini"
    # No provider configured -> honest 503, never a fabricated analysis.
    monkeypatch.setattr(st, "OPENAI_API_KEY", "")
    with pytest.raises(HTTPException):
        st._analysis_client_model()


# ── Auth: verify_key rejects before the handler runs ─────────────────────────

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api_gateway.main import app
    return TestClient(app)


def test_rag_search_requires_key(client):
    assert client.post("/api/rag/search", json={"query": "x"}).status_code in (401, 403)


def test_rag_embed_requires_key(client):
    r = client.post("/api/rag/embed", json={"source_type": "documento", "source_name": "x", "text": "y"})
    assert r.status_code in (401, 403)


def test_ingest_resource_requires_key(client):
    assert client.post("/api/strategy/ingest-resource", data={"intent": "pend"}).status_code in (401, 403)


def test_wrong_key_rejected(client):
    assert client.post("/api/rag/search", json={"query": "x"}, headers={"X-API-Key": "nope"}).status_code == 403
