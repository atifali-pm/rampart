"""Rampart FastAPI entrypoint.

Phase 2: event bus + SLA watcher + override flow + dashboard read API.
State changes still go through the deterministic transition service.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.events import router as events_router
from src.api.routes.incidents import router as incidents_router
from src.api.routes.jobs import router as jobs_router
from src.api.routes.transitions import router as transitions_router

app = FastAPI(
    title="Rampart",
    description="Enforcement-first operational OS for field service ops.",
    version="0.3.0",
)

# Dev-only permissive CORS so the Vite dev server on :5174 can hit the
# API on :8040. Tighten before any non-portfolio deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router)
app.include_router(transitions_router)
app.include_router(events_router)
app.include_router(incidents_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "rampart",
        "version": "0.3.0",
        "phase": "3-incident-command",
        "status": "hello",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
