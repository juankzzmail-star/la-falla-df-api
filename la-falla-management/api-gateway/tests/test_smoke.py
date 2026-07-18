"""Smoke tests — verify the app boots and core wiring is correct (no DB required).

These exercise only public/auth paths that never touch PostgreSQL, so they run with
the in-memory SQLite from conftest. DB-backed and Playwright E2E tests are separate
(see docs/openspec-tasks-mandatory-steps.md).
"""


def test_healthz_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_config_exposes_key_shape(client):
    r = client.get("/config")
    assert r.status_code == 200
    body = r.json()
    assert "apiKey" in body and "apiBase" in body
    # Regression guard for the auth fallback fix: with FASTAPI_GM_API_KEY OR
    # FASTAPI_API_KEY set, the resolved key must be non-empty (was "" -> 500s before).
    assert body["apiKey"]


def test_protected_route_requires_key(client):
    # No X-API-Key -> rejected by verify_key before reaching the DB-backed handler.
    r = client.get("/api/dashboard/summary")
    assert r.status_code in (401, 403)


def test_protected_route_rejects_wrong_key(client):
    r = client.get("/api/dashboard/summary", headers={"X-API-Key": "wrong"})
    assert r.status_code == 403
