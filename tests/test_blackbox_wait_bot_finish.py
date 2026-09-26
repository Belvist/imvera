"""Blackbox wait_bot_finish must require bot speech then silence."""

from __future__ import annotations

import threading
import time

from tools.blackbox_caller.speech_detector import DownlinkSpeechDetector, SpeechDetectorConfig


def _speech_frame(rms_like: int = 40, n: int = 160) -> bytes:
    return bytes([max(0, min(255, 128 + rms_like))] * n)


def _silence_frame(n: int = 160) -> bytes:
    return bytes([128] * n)


def test_detector_requires_silence_run_before_idle() -> None:
    det = DownlinkSpeechDetector(
        SpeechDetectorConfig(silence_frames_for_end=5, speech_rms_threshold=12.0)
    )
    for _ in range(3):
        speaking, finished = det.feed(_speech_frame())
        assert speaking and not finished
    assert det.bot_speaking
    for _ in range(4):
        speaking, finished = det.feed(_silence_frame())
        assert speaking and not finished
    speaking, finished = det.feed(_silence_frame())
    assert not speaking and finished
    assert not det.bot_speaking


def test_wait_bot_finish_ignores_pre_opening_silence() -> None:
    """Regression: old logic returned when recorder had bytes + silence."""

    class _Fake:
        def __init__(self) -> None:
            self._detector = DownlinkSpeechDetector(
                SpeechDetectorConfig(silence_frames_for_end=3, speech_rms_threshold=12.0)
            )

        def wait_bot_finish(self, timeout_s: float) -> bool:
            deadline = time.time() + timeout_s
            saw_speech = bool(self._detector.bot_speaking)
            while time.time() < deadline:
                if self._detector.bot_speaking:
                    saw_speech = True
                elif saw_speech:
                    return True
                time.sleep(0.01)
            return False

    fake = _Fake()
    assert fake.wait_bot_finish(0.2) is False

    for _ in range(4):
        fake._detector.feed(_speech_frame())
    assert fake._detector.bot_speaking

    def _end_speech() -> None:
        time.sleep(0.05)
        for _ in range(6):
            fake._detector.feed(_silence_frame())

    threading.Thread(target=_end_speech, daemon=True).start()
    assert fake.wait_bot_finish(2.0) is True
