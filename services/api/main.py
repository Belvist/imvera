"""Minimal API — Phase 6 placeholder, health for Docker."""

from fastapi import FastAPI

from packages import __version__ as _pkg_version  # noqa: F401

app = FastAPI(title="IMVERA VoiseUp API", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "imvera-backend-mock"}


@app.get("/version")
def version() -> dict:
    return {"architecture_freeze": "v1", "phase": 2}
