import os
from datetime import datetime, timezone
from fastapi import FastAPI, Security, HTTPException
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware

from .routers import goals, plans, tasks, health, dashboard

API_KEY = os.environ.get("FASTAPI_GM_API_KEY", "")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


def verify_key(key: str = Security(api_key_header)):
    if not API_KEY:
        raise HTTPException(500, "FASTAPI_GM_API_KEY not configured")
    if key != API_KEY:
        raise HTTPException(403, "Invalid API key")
    return key


app = FastAPI(
    title="La Falla DF — Gerencia General API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in [goals.router, plans.router, tasks.router, health.router, dashboard.router]:
    app.include_router(router, dependencies=[Security(verify_key)])


@app.get("/healthz", tags=["meta"])
def health_check():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}
