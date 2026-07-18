"""Automatic inbound import (change auto-import-google-tasks): the background scheduler reuses the same
import core as the POST endpoint. These tests cover the enable gate (off on sqlite / interval<=0) and
that a single cycle swallows the honest 503 when the Google seam is unconfigured (so the loop never
dies). The seam is monkeypatched — no network.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FASTAPI_GM_API_KEY", "test-key-123")
os.environ.setdefault("FASTAPI_API_KEY", "test-key-123")

from fastapi import HTTPException

from api_gateway.routers import _gtasks, tasks


def test_auto_import_disabled_on_sqlite(monkeypatch):
    # default interval is positive, but an ephemeral sqlite DB must keep the scheduler OFF
    monkeypatch.setenv("AUTO_IMPORT_INTERVAL_MIN", "120")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    assert tasks.auto_import_enabled() is False


def test_auto_import_enabled_on_postgres(monkeypatch):
    monkeypatch.setenv("AUTO_IMPORT_INTERVAL_MIN", "120")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host/db")
    assert tasks.auto_import_enabled() is True


def test_auto_import_disabled_when_interval_zero(monkeypatch):
    monkeypatch.setenv("AUTO_IMPORT_INTERVAL_MIN", "0")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host/db")
    assert tasks.auto_import_enabled() is False


def test_auto_import_once_swallows_503(monkeypatch):
    """No credentials -> the import core raises 503; one cycle must absorb it and report skipped."""
    def _raise(**kwargs):
        raise HTTPException(503, "Google Tasks no configurado")

    monkeypatch.setattr(_gtasks, "list_tasks", _raise)
    out = tasks.auto_import_once()
    assert out.get("skipped") == "google-no-config"
