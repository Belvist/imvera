"""Stage D STT streaming feature flag (spike; phone path unchanged).

``MOSS_STT_STREAMING=1`` enables experimental streaming STT on the **WebApp /
non-phone** ``/turn_stream`` path only. The FreeSWITCH Lua phone path
(``segment_dir`` set) intentionally keeps one-shot STT until mod_audio_fork
or ESL media-bug delivers continuous PCM — see ``docs/STT_STREAMING_SPIKE.md``.
"""
from __future__ import annotations

import os


def stt_streaming_requested() -> bool:
    """True when MOSS_STT_STREAMING is set to a truthy value."""
    return os.environ.get("MOSS_STT_STREAMING", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def phone_path_uses_batch_stt() -> bool:
    """Phone path always batch-decodes until Stage D media fork lands."""
    return True
