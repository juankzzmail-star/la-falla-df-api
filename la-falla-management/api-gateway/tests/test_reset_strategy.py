"""Tests for /api/strategy/reset endpoint password authentication and table wiping logic."""
import pytest

from api_gateway.routers import strategy


def test_reset_strategy_wrong_password(client):
    res = client.delete(
        "/api/strategy/reset",
        headers={"X-API-Key": "test-key-123"},
        json={"password": "wrong_password"},
    )
    assert res.status_code == 403
    assert "Contraseña incorrecta" in res.json()["detail"]


def test_reset_strategy_correct_password(client, monkeypatch):
    monkeypatch.setattr(strategy, "DATABASE_URL", "sqlite://")
    monkeypatch.setattr(strategy, "RESET_PASSWORD", "Lafalladf8178.")

    res = client.delete(
        "/api/strategy/reset",
        headers={"X-API-Key": "test-key-123"},
        json={"password": "Lafalladf8178."},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "cleared_tables" in data
