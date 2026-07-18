"""Pytest fixtures for the Gerencia api-gateway.

IMPORTANT — package layout: when deployed, the app is the package `api_gateway`
(the Dockerfile copies `api-gateway/` -> `/app/api_gateway/`). Run these tests in
that layout (CI/container) where `import api_gateway` works. On the local Windows
working tree the folder is `api-gateway` (hyphen) — not a valid module name — so
the tests are authored here but EXECUTE at deploy/CI, not in this working tree.

The fixtures set env BEFORE the app imports `db.py` (which reads DATABASE_URL at
import time), point the DB at an in-memory SQLite (the smoke tests don't touch the
DB), and expose a FastAPI TestClient.
"""
import os

import pytest

# Set before importing the app (db.py / main.py read these at import time).
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FASTAPI_GM_API_KEY", "test-key-123")
os.environ.setdefault("FASTAPI_API_KEY", "test-key-123")


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from api_gateway.main import app  # noqa: import deferred until env is set

    return TestClient(app)
