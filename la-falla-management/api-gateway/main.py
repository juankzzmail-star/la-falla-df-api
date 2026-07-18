import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Security, HTTPException
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .routers import goals, plans, tasks, health, dashboard
from .routers import risks, roadmap, financial, inbox, projects, stakeholders, chat, strategy, rag
from .routers import edt_onboarding, oportunidades, interview

API_KEY = os.environ.get("FASTAPI_GM_API_KEY") or os.environ.get("FASTAPI_API_KEY", "")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def verify_key(key: str = Security(api_key_header)):
    if not API_KEY:
        raise HTTPException(500, "FASTAPI_GM_API_KEY not configured")
    if key != API_KEY:
        raise HTTPException(403, "Invalid API key")
    return key


@asynccontextmanager
async def lifespan(app: FastAPI):
    # change auto-import-google-tasks: keep the Pulso live by reimporting Google Tasks on a cadence.
    bg_tasks = []
    if tasks.auto_import_enabled():
        bg_tasks.append(asyncio.create_task(tasks.auto_import_loop()))
    # Risk radar: Gentil's deep brain (DeepSeek V4 Pro) keeps the Risk Map alive — analyses new risks
    # and proposes strategic ones from live signals. Off unless RISK_RADAR_ENABLED=1 + DEEPSEEK_API_KEY.
    if risks.radar_enabled():
        bg_tasks.append(asyncio.create_task(risks.risk_radar_loop()))
    try:
        yield
    finally:
        for bg in bg_tasks:
            bg.cancel()
            try:
                await bg
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title="La Falla DF — Gerencia General API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)

# CORS: restrict to the known dashboard origin(s); override via CORS_ORIGINS (comma-separated).
# The SPA is served same-origin from this app, so a tight list does not break it.
_cors_origins = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS", "https://la-falla-df-api-gm.7ubo23.easypanel.host"
).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type"],
)

# --- Archivos estáticos (CSS, JSX, assets) ---
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# --- Dashboard HTML (público, sin auth) ---
@app.get("/", include_in_schema=False)
def serve_dashboard():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

# --- Health check público ---
@app.get("/healthz", tags=["meta"])
def health_check():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}

# --- Config pública: entrega la API key al frontend (VPS privado) ---
@app.get("/config", include_in_schema=False)
def get_config():
    return {"apiKey": API_KEY, "apiBase": "/api"}

# --- Endpoints de datos bajo /api (requieren API key) ---
protected = [
    goals.router,
    plans.router,
    tasks.router,
    health.router,
    dashboard.router,
    risks.router,
    roadmap.router,
    financial.router,
    inbox.router,
    projects.router,
    stakeholders.router,
    chat.router,
    strategy.router,
    rag.router,
    oportunidades.router,
    interview.router,
]
for router in protected:
    app.include_router(router, prefix="/api", dependencies=[Security(verify_key)])

# --- EDT Onboarding (sin auth — wizard publico de creacion de proyecto) ---
# El router ya tiene prefix="/api/edt-onboarding"
app.include_router(edt_onboarding.router)

# --- Webhook financiero (sin la API key global; valida su propio token de app_config) ---
# change real-financial-source (push): el Apps Script onEdit de MOVIMIENTOS 2026 dispara /hooks/financial-sheets
app.include_router(financial.webhook_router)
