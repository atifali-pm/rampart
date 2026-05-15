"""Rampart FastAPI entrypoint.

Phase 0 hello-world. The deterministic core and enforcement engine land in Phase 1.
"""

from fastapi import FastAPI

app = FastAPI(
    title="Rampart",
    description="Enforcement-first operational OS for field service ops.",
    version="0.0.1",
)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "rampart",
        "version": "0.0.1",
        "phase": "0-scaffold",
        "status": "hello",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
