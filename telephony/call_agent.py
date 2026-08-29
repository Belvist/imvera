#!/usr/bin/env python3
"""MossVoice Call Agent — turn-based telephone agent.

Facade over the decomposed telephony package (see core/, adapters/, legacy/,
worker/, tools/). Bridges FreeSWITCH (via a Lua dialplan script) to the
MossVoice engine:
  * receives a recorded caller turn (WAV),
  * transcribes it with Whisper (STT),
  * the agent decides a reply (LLM via OPENAI_* env if set, else a scripted
    fallback that collects/mirrors the caller's info),
  * synthesizes the reply in the cloned voice via the local TTS daemon,
  * returns reply audio + transcripts + per-call notes.

HTTP (localhost):
  POST /turn           <- caller turn (8k WAV)  -> reply WAV + json
  POST /new            -> start a fresh call session
  GET  /health         -> readiness

This module keeps the historical public names importable from ``call_agent``
(Serve, Handler, StreamingSTT, TTSClient, Cloud*Adapter, ...) so tests and
moss_providers keep working unchanged, and remains runnable as
``python call_agent.py`` (supervisor + Docker entry points).
"""
import sys

from _paths import ensure_runtime_scripts

# Must come first: tts_common/backends live in the runtime scripts dir and
# are imported lazily by the adapters below (mirrors the original module).
ensure_runtime_scripts()

from core.orchestrator import Serve  # noqa: E402
from core.state import (  # noqa: E402
    CallContext,
    CallBusyError,
    DEFAULT_GREETING,
    SESSION_TTL_SEC,
)
from core.dialogue import (  # noqa: E402
    Agent,
    MVERA_GREETING,
    VERA_LLM_ID,
    VERA_LLM_URL,
    VERA_SYSTEM_PROMPT,
    OK_WORDS,
    BAD_WORDS,
    DISTRESS_WORDS,
    MED_WORDS,
    HELP_WORDS,
    clean_transcript,
    short_real_answer,
    _clean_llm,
)
from core.events import (  # noqa: E402
    StreamingSTT,
    STT_HOP_SECONDS,
    reply_segments,
)
from adapters.moss_tts import TTSClient  # noqa: E402
from adapters.stt import STTEngine  # noqa: E402
from adapters.llm import LLMClient  # noqa: E402
from adapters.cloud import (  # noqa: E402
    CloudSTTAdapter,
    CloudLLMAdapter,
    CloudTTSAdapter,
    _maybe_cloud_stt,
    _maybe_cloud_llm,
    _maybe_cloud_tts,
)
from adapters.redis_store import _maybe_session_store  # noqa: E402
from adapters.postgres_results import Recorder  # noqa: E402
from adapters.s3_recordings import save_wav, save_user_wav  # noqa: E402
from adapters.audio import wav_to_pcm, pcm_to_wav, parse_multipart_wav  # noqa: E402
from api.http import QuietHTTPServer, Handler  # noqa: E402
from agent_service.mossvoice_agent import build_server, run  # noqa: E402
from agent_service.main import main  # noqa: E402

__all__ = [
    "Serve",
    "Handler",
    "QuietHTTPServer",
    "CallContext",
    "CallBusyError",
    "DEFAULT_GREETING",
    "SESSION_TTL_SEC",
    "Agent",
    "MVERA_GREETING",
    "VERA_LLM_ID",
    "VERA_LLM_URL",
    "VERA_SYSTEM_PROMPT",
    "OK_WORDS",
    "BAD_WORDS",
    "DISTRESS_WORDS",
    "MED_WORDS",
    "HELP_WORDS",
    "clean_transcript",
    "short_real_answer",
    "_clean_llm",
    "StreamingSTT",
    "STT_HOP_SECONDS",
    "reply_segments",
    "TTSClient",
    "STTEngine",
    "LLMClient",
    "CloudSTTAdapter",
    "CloudLLMAdapter",
    "CloudTTSAdapter",
    "_maybe_cloud_stt",
    "_maybe_cloud_llm",
    "_maybe_cloud_tts",
    "_maybe_session_store",
    "Recorder",
    "save_wav",
    "save_user_wav",
    "wav_to_pcm",
    "pcm_to_wav",
    "parse_multipart_wav",
    "build_server",
    "run",
    "main",
]


if __name__ == "__main__":
    main()