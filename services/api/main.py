"""IMVERA VoiseUp API — health, calls, voice WebSocket."""

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from services.api.voice import router as voice_router

app = FastAPI(title="IMVERA VoiseUp API", version="0.3.0")
app.include_router(voice_router)

_client_dir = os.path.join(os.path.dirname(__file__), "..", "..", "apps", "voice-client")
if os.path.isdir(_client_dir):
    app.mount("/voice", StaticFiles(directory=_client_dir, html=True), name="voice-client")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "imvera-voiseup"}


@app.on_event("startup")
def _log_store() -> None:
    if os.environ.get("IMVERA_PG_URL") or os.environ.get("IMVERA_VOICE_DATABASE_URL"):
        return
