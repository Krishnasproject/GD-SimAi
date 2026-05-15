# =============================================================================
# backend/app/main.py
#
# PURPOSE: The entry point of the FastAPI application.
#
# HOW IT WORKS:
#   1. Creates the FastAPI app instance.
#   2. Configures CORS so the React frontend (localhost:5173) can talk to us.
#   3. Mounts all route groups (sessions, analytics, websocket).
#   4. Provides a health-check endpoint so deployment platforms (Render) know
#      the server is alive.
#
# TO RUN LOCALLY (without Docker):
#   cd backend
#   uvicorn app.main:app --reload
#   → API docs at http://localhost:8000/docs
# =============================================================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import sessions, analytics, ws
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🔥 Starting up MockTalk backend...")
    try:
        from app.services.chroma import init_chroma
        init_chroma()
        logger.info("✅ Startup complete.")
    except Exception as e:
        logger.warning(f"⚠️ Startup warning: {e}")
    yield
    logger.info("🛑 Shutting down.")



# ── 1. Create FastAPI App ─────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Multi-persona Group Discussion simulator for placement prep.",
    # /docs → Swagger UI, /redoc → ReDoc (both auto-generated)
    docs_url="/docs" if settings.DEBUG else None,
    lifespan=lifespan,
)


# ── 2. CORS Middleware ────────────────────────────────────────────────────────
# CORS = Cross-Origin Resource Sharing.
# Without this, the browser blocks requests from localhost:5173 → localhost:8000.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins(),
    allow_credentials=True,                  # Allow cookies / auth headers
    allow_methods=["*"],                     # GET, POST, PUT, DELETE, etc.
    allow_headers=["*"],                     # Authorization, Content-Type, etc.
)


# ── 3. Mount Route Groups ─────────────────────────────────────────────────────
# Each router lives in its own file (see app/routers/).
# Prefix = the URL path prefix for all routes in that file.

app.include_router(
    sessions.router,
    prefix="/api/sessions",      # e.g., POST /api/sessions/create
    tags=["Sessions"],           # groups endpoints in /docs
)

app.include_router(
    analytics.router,
    prefix="/api/analytics",     # e.g., GET /api/analytics/{session_id}
    tags=["Analytics"],
)

app.include_router(
    ws.router,
    prefix="/ws",                # e.g., WS /ws/{session_id}
    tags=["WebSocket"],
)


# ── 4. Health Check ───────────────────────────────────────────────────────────
# Render, Railway, etc. ping this to confirm the server is running.
@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}


# ── 5. Root ───────────────────────────────────────────────────────────────────
@app.get("/", tags=["System"])
async def root():
    return {"message": f"Welcome to {settings.APP_NAME} API 🎤"}
