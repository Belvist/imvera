"""Offline tests for the audio core that feeds VAD/STT: LiveWavReader
(valid-header gating incl. the broken 44-byte WAVs, 8 kHz -> 16 kHz
resampling, LEFT-channel stereo extraction, partial-frame buffering) and
VAD (barge onset, completed turns, 400 ms pre-roll prepended to the turn).

Run:  python3 -m unittest voice_runtime.test_voice_core -v
"""
import os
import struct
import sys
import tempfile
import time
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from media_tap import (  # noqa: E402
    LiveWavReader, WAV_HEADER, resample_linear,
)
from vad import VAD, PRE_ROLL_SAMPLES, SILENCE_GAP_MS, MIN_SPEECH_MS  # noqa: E402
from call_session import CallSession  # noqa: E402


def wav_header(pcm_len, channels=1, rate=16000):
    h = bytearray(44)
    h[0:4] = b"RIFF"
    h[4:8] = struct.pack("<I", 36 + pcm_len)
    h[8:12] = b"WAVE"
    h[12:16] = b"fmt "
    h[16:20] = struct.pack("<I", 16)
    h[20:22] = struct.pack("<H", 1)
    h[22:24] = struct.pack("<H", channels)
    h[24:28] = struct.pack("<I", rate)
    h[28:32] = struct.pack("<I", rate * channels * 2)
    h[32:34] = struct.pack("<H", channels * 2)
    h[34:36] = struct.pack("<H", 16)
    h[36:40] = b"data"
    h[40:44] = struct.pack("<I", pcm_len)
    return bytes(h)


def pcm(samples):
    return struct.pack("<%dh" % len(samples), *samples)


def stereo_pcm(left, right):
    return pcm([v for pair in zip(left, right) for v in pair])


class ResampleTests(unittest.TestCase):
    def test_8k_to_16k_doubles_length(self):
        src = [100, -100, 200] * 40
        out = resample_linear(src, 8000, 16000)
        self.assertEqual(len(out), len(src) * 2)
        self.assertEqual(out[0], src[0])  # exact sample at even positions
        self.assertAlmostEqual(out[1], (src[0] + src[1]) / 2, delta=1)

    def test_equal_rate_unchanged(self):
        src = [1, 2, 3]
        self.assertIs(resample_linear(src, 16000, 16000), src)

    def test_empty(self):
        self.assertEqual(resample_linear([], 8000, 16000), [])


class LiveWavReaderTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

    def tearDown(self):
        try:
            os.remove(self.path)
        except OSError:
            pass

    def test_8k_stereo_left_resampled_to_16k(self):
        left = list(range(0, 320))          # 0.02 s of 8 kHz
        right = [9000] * 320
        with open(self.path, "wb") as f:
            f.write(wav_header(len(left) * 2 * 2, channels=2, rate=8000))
            f.write(stereo_pcm(left, right))
        rd = LiveWavReader(self.path)
        got = rd.read_new(rate=16000)
        self.assertEqual(rd.channels, 2)
        self.assertEqual(rd.rate, 8000)
        self.assertEqual(len(got), len(left) * 2)  # resampled to 16 kHz
        self.assertEqual(got[0], left[0])
        self.assertLess(max(got), 400)     # RIGHT (9000) never leaked in
        self.assertEqual(got[2::2], left[1:][:len(got) // 2])

    def test_16k_mono_passthrough(self):
        chunk = [40 if i % 2 == 0 else -40 for i in range(1600)]
        with open(self.path, "wb") as f:
            f.write(wav_header(len(chunk) * 2, channels=1, rate=16000))
            f.write(pcm(chunk))
        rd = LiveWavReader(self.path)
        got = rd.read_new()
        self.assertEqual(rd.rate, 16000)
        self.assertEqual(got, chunk)

    def test_broken_44_byte_garbage_is_refused(self):
        # exactly the record_stereo failure mode: 44 bytes, not RIFF/WAVE
        with open(self.path, "wb") as f:
            f.write(b"\x00" * 44)
        rd = LiveWavReader(self.path)
        self.assertIsNone(rd.probe())
        self.assertTrue(rd.broken)
        self.assertEqual(rd.read_new(), [])

    def test_truncated_header_returns_none_until_complete(self):
        with open(self.path, "wb") as f:
            f.write(wav_header(0)[:30])
        rd = LiveWavReader(self.path)
        self.assertIsNone(rd.probe())
        self.assertFalse(rd.broken)
        self.assertEqual(rd.audio_bytes(), 0)

    def test_partial_frame_buffered_across_reads(self):
        chunk = [111, -222, 333, 444]
        with open(self.path, "wb") as f:
            f.write(wav_header(len(chunk) * 2, channels=1, rate=16000))
            f.write(pcm(chunk)[:5])  # 2 complete frames + 1 byte of frame 3
        rd = LiveWavReader(self.path)
        got1 = rd.read_new()
        self.assertEqual(got1, [111, -222])  # never a spliced sample
        with open(self.path, "ab") as f:
            f.write(pcm(chunk)[5:])   # rest of frame 3 + frame 4
        got2 = rd.read_new()
        self.assertEqual(got2[:2], [333, 444])  # partial frame reassembled

    def test_audio_bytes_counts_payload_only(self):
        with open(self.path, "wb") as f:
            f.write(wav_header(100))
            f.write(pcm([0] * 50))
        rd = LiveWavReader(self.path)
        rd.probe()
        self.assertEqual(rd.audio_bytes(), 100)


def feed(v, level, n_ms, ms=30):
    """Feed n_ms of constant level in `ms`-long chunks; return
    ``(turns_list, onsets_list)`` over the whole script segment."""
    samples = [level] * (16000 * ms // 1000)
    turns, onsets = [], []
    for _ in range(n_ms // ms):
        turn, o = v.feed(samples, ms)
        if turn:
            turns.append(turn)
        if o:
            onsets.append(o)
    return turns, onsets


class VADTests(unittest.TestCase):
    def test_barge_onset_fires_once_at_speech_start(self):
        v = VAD()
        feed(v, 0, 300)                     # silence
        turns, onsets = feed(v, 1200, 330)  # speech starts
        self.assertGreaterEqual(len(onsets), 1)
        self.assertEqual(turns, [])         # still speaking, no turn yet

    def test_turn_completes_after_gap_and_includes_preroll(self):
        v = VAD()
        feed(v, 0, 1000, ms=50)              # ~1 s silence fills preroll cap
        turns, _ = feed(v, 1500, 300)        # ~0.3 s speech (> MIN_SPEECH_MS)
        self.assertEqual(turns, [])
        turns, _ = feed(v, 0, SILENCE_GAP_MS + 200)
        self.assertEqual(len(turns), 1)
        # 400 ms pre-roll of pre-onset silence is prepended to the turn
        self.assertGreaterEqual(len(turns[0]), PRE_ROLL_SAMPLES)

    def test_short_blip_is_rejected(self):
        v = VAD()
        feed(v, 0, 300)
        turns, _ = feed(v, 1500, 60)         # ~0.06 s -> below MIN_SPEECH_MS
        self.assertEqual(turns, [])
        turns, _ = feed(v, 0, SILENCE_GAP_MS + 200)
        self.assertEqual(turns, [])

    def test_max_len_force_flush(self):
        v = VAD()
        turns, _ = feed(v, 1200, 11000, ms=100)
        self.assertEqual(len(turns), 1)

    def test_short_noise_does_not_fire_barge_onset(self):
        """P3 (2026-08-29): a single loud 60 ms burst (cough/click) must
        NOT trigger the barge-in — it used to fire on one 30 ms chunk and
        killed Vera's utterance + the whole generation."""
        v = VAD()
        feed(v, 0, 300)                     # silence
        turns, onsets = feed(v, 1200, 60)   # 60 ms noise
        self.assertEqual(onsets, [])
        # and it does not accumulate into a turn later
        turns, _ = feed(v, 0, SILENCE_GAP_MS + 200)
        self.assertEqual(turns, [])

    def test_onset_fires_after_sustained_speech(self):
        """P3: the barge onset is delayed until MIN_SPEECH_MS of sustained
        speech, not fired at the first chunk."""
        v = VAD()
        feed(v, 0, 300)
        turns, onsets = feed(v, 1200, 150)   # 150 ms -> still below MIN
        self.assertEqual(onsets, [], "onset must not fire below MIN_SPEECH_MS")
        turns, onsets = feed(v, 1200, 200)   # cumulative ~350 ms
        self.assertGreaterEqual(len(onsets), 1)


class PlaybackWatchdogTests(unittest.TestCase):
    """P3 (2026-08-29): a lost PLAYBACK_STOP must not wedge the session —
    the watchdog clears playing once the file's nominal duration + grace
    has passed."""

    class _Noop:
        def __getattr__(self, name):
            return lambda *a, **k: None

    def _session(self):
        s = CallSession("uuid", self._Noop(), self._Noop(), "/tmp/x",
                        caller_id=None, log=lambda m: None)
        return s

    def test_watchdog_clears_wedged_playing(self):
        s = self._session()
        s.playing = True
        s.current_file = "/tmp/x.wav"
        s._play_end = 0.0                     # long past
        s._maybe_watchdog_playing(time.monotonic())
        self.assertFalse(s.playing)
        self.assertIsNone(s.current_file)

    def test_watchdog_keeps_playing_within_duration(self):
        s = self._session()
        s.playing = True
        s.current_file = "/tmp/x.wav"
        s._play_end = time.monotonic() + 10.0
        s._maybe_watchdog_playing(time.monotonic())
        self.assertTrue(s.playing, "playing must survive before the deadline")

    def test_playback_stop_event_resets_watchdog(self):
        s = self._session()
        s.playing = True
        s.current_file = "/tmp/x.wav"
        s._play_end = time.monotonic() + 10.0
        s.handle_event({"Event-Name": "PLAYBACK_STOP"})
        self.assertFalse(s.playing)
        self.assertIsNone(s._play_end)


if __name__ == "__main__":
    unittest.main(verbosity=2)