"""Thin wrapper over the n8n REST API v1."""
import json
import os
from typing import Optional

import requests

N8N_HOST = os.environ.get("N8N_HOST", "")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")


def _h() -> dict:
    return {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def _url(path: str) -> str:
    return N8N_HOST.rstrip("/") + "/api/v1" + path


def configured() -> bool:
    return bool(N8N_HOST and N8N_API_KEY)


def health() -> bool:
    if not configured():
        return False
    try:
        r = requests.get(_url("/workflows?limit=1"), headers=_h(), timeout=8)
        return r.ok
    except Exception:
        return False


def list_workflows() -> dict:
    r = requests.get(_url("/workflows"), headers=_h(), timeout=15)
    r.raise_for_status()
    return r.json()


def get_workflow(wid: str) -> dict:
    r = requests.get(_url(f"/workflows/{wid}"), headers=_h(), timeout=15)
    r.raise_for_status()
    return r.json()


def get_executions(limit: int = 20, status: Optional[str] = None) -> dict:
    qs = f"?limit={limit}"
    if status:
        qs += f"&status={status}"
    r = requests.get(_url(f"/executions{qs}"), headers=_h(), timeout=15)
    r.raise_for_status()
    return r.json()


def create_workflow(name: str, nodes: list, connections: dict, active: bool = False) -> dict:
    body = {
        "name": name,
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
        "active": active,
    }
    r = requests.post(_url("/workflows"), headers=_h(), json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def activate_workflow(wid: str) -> dict:
    r = requests.patch(_url(f"/workflows/{wid}/activate"), headers=_h(), timeout=15)
    r.raise_for_status()
    return r.json()


def deactivate_workflow(wid: str) -> dict:
    r = requests.patch(_url(f"/workflows/{wid}/deactivate"), headers=_h(), timeout=15)
    r.raise_for_status()
    return r.json()


def trigger_webhook(webhook_url: str, payload: dict) -> requests.Response:
    return requests.post(webhook_url, json=payload, timeout=20)
