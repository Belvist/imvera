"""TTS first_pcm gate helper."""

from __future__ import annotations

from unittest.mock import patch

from packages.voice_runtime.tts_gate import measure_tts_first_pcm_s


def test_measure_tts_first_pcm_parses_stream() -> None:
    lines = [
        '{"sequence": 0, "pcm_b64": "AAA=", "sample_rate": 24000, "is_last": false}',
        '{"done": true}',
    ]

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def iter_lines(self):
            yield from lines

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    class FakeClient:
        def stream(self, *args, **kwargs):
            return FakeResponse()

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    with patch("packages.voice_runtime.tts_gate.httpx.Client", return_value=FakeClient()):
        elapsed = measure_tts_first_pcm_s("http://127.0.0.1:9102")
    assert elapsed >= 0.0
