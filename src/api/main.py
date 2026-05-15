"""Rampart FastAPI entrypoint.

Phase 1: deterministic core. State changes go through the transition service,
which guarantees the audit row and the state mutation share one DB transaction.
"""

from __future__ import annotations

from fastapi import FastAPI

from src.api.routes.jobs import router as jobs_router

app = FastAPI(
    title="Rampart",
    description="Enforcement-first operational OS for field service ops.",
    version="0.1.0",
)

app.include_router(jobs_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "rampart",
        "version": "0.1.0",
        "phase": "1-deterministic-core",
        "status": "hello",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
