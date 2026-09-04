"""Always-on RX voice activity detector (ported from tg/tg_server.py).

Pure-Python RMS VAD — no numpy, no webrtcvad (neither is available on this
host). Feed int16 samples; returns ``(completed_turn_or_None, barge_onset)``:

  * ``barge_onset`` fires ONCE the moment a speech burst starts — the exact
    signal the barge-in path needs to call ``uuid_break`` + ``stream-cancel``
    while still buffering the whole utterance for STT (nothing is lost);
  * ``completed_turn`` fires after SILENCE_GAP_MS of trailing silence and is
    the full int16 buffer (speech + tail), ready to write to a WAV.

The stereo tape already isolates the caller on LEFT, so Vera's playback does
not leak into this stream; ``agent_speaking`` remains available as an extra
gate for real-world speakerphone echo.
"""
SAMPLE_RATE = 16000
CHUNK_MS = 30
SILENCE_GAP_MS = 700
MIN_TURN_SAMPLES = SAMPLE_RATE // 10        # ignore < 0.1 s
MAX_TURN_SAMPLES = SAMPLE_RATE * 10         # hard cap 10 s
ENERGY_THRESHOLD = 300.0                    # absolute RMS gate (16-bit PCM)
MIN_SPEECH_MS = 220
NOISE_FLOOR_RATIO = 3.0
ECHO_THRESHOLD_RATIO = 2.6
ECHO_MIN_SPEECH_MS = 320
PRE_ROLL_MS = 400                           # pre-onset context for ASR
PRE_ROLL_SAMPLES = int(SAMPLE_RATE * PRE_ROLL_MS / 1000)
# Keep in sync with call_session.TURN_ENERGY_MIN / orchestrator SILENT gate.
MIN_TURN_MEAN_ENERGY = 0.004


def mean_abs_energy(samples):
    if not samples:
        return 0.0
    total = sum(abs(int(x)) for x in samples)
    return total / (32768.0 * len(samples))


def rms(samples):
    if not samples:
        return 0.0
    s = sum(x * x for x in samples)
    return (s / len(samples)) ** 0.5


class VAD:
    def __init__(self):
        self.silence = 0
        self.speech_ms = 0
        self.buffer = []
        self.noise_floor = None
        # Rolling pre-onset audio window (~400 ms): frozen while speaking,
        # prepended to every completed turn so a late VAD onset never clips
        # the first phonemes the caller actually said.
        self._in_speech = False
        self._onset_fired = False
        self.preroll = []

    def reset(self):
        self.silence = 0
        self.speech_ms = 0
        self.buffer = []
        self.noise_floor = None
        self._in_speech = False
        self._onset_fired = False
        self.preroll = []

    def speech_threshold(self, agent_speaking=False):
        base = ENERGY_THRESHOLD
        if self.noise_floor is not None:
            base = max(base, self.noise_floor * NOISE_FLOOR_RATIO)
        if agent_speaking:
            return base * ECHO_THRESHOLD_RATIO
        return base

    def _keep_preroll(self, samples):
        """Rolling window of the most recent non-speech samples (~400 ms)."""
        if not samples:
            return
        self.preroll.extend(samples)
        if len(self.preroll) > PRE_ROLL_SAMPLES:
            del self.preroll[:len(self.preroll) - PRE_ROLL_SAMPLES]

    def _finish_turn(self):
        """Assemble the completed turn = pre-onset context + speech + tail."""
        turn = self.preroll + self.buffer
        self.preroll = []
        self.buffer = []
        self.silence = 0
        self.speech_ms = 0
        self._in_speech = False
        self._onset_fired = False
        if mean_abs_energy(turn) < MIN_TURN_MEAN_ENERGY:
            return None
        return turn

    def feed(self, samples, chunk_ms=None, agent_speaking=False):
        """Returns ``(completed_turn_or_None, barge_in_onset_bool)``."""
        ms = float(chunk_ms or CHUNK_MS)
        e = rms(samples)
        if self.noise_floor is None:
            self.noise_floor = e if e < ENERGY_THRESHOLD * 4 else ENERGY_THRESHOLD
        thr = self.speech_threshold(agent_speaking=agent_speaking)
        onset = False
        if e >= thr:
            was_silent = self.speech_ms == 0
            self.silence = 0
            self.speech_ms += ms
            self.buffer.extend(samples)
            self.noise_floor = 0.999 * self.noise_floor + 0.001 * min(e, thr * 1.1)
            if was_silent:
                self._in_speech = True  # freeze preroll at the onset moment
                # BARGE-IN PORT (2026-08-29, FIXES_PLAN P3): a burst of
                # ONE 30 ms chunk used to fire the barge-in instantly — a
                # cough/click/chair-scrape mid-sentence killed Vera's
                # utterance and cancelled the whole generation. The onset
                # now fires only after the speech has been sustained for
                # MIN_SPEECH_MS (or ECHO_MIN_SPEECH_MS while she speaks) —
                # the buffer already holds everything since the real onset,
                # so nothing is clipped, we just break later.
                self._onset_fired = False
            if not self._onset_fired:
                min_ = ECHO_MIN_SPEECH_MS if agent_speaking else MIN_SPEECH_MS
                if self.speech_ms >= min_:
                    self._onset_fired = True
                    onset = True
        else:
            self.silence += ms
            self.noise_floor = 0.95 * self.noise_floor + 0.05 * e
            if self.silence < SILENCE_GAP_MS:
                self.buffer.extend(samples)
            self._in_speech = False
            self._keep_preroll(samples)

        if len(self.buffer) > MAX_TURN_SAMPLES:
            turn = self._finish_turn()
            return turn, onset

        if self.silence >= SILENCE_GAP_MS:
            min_ms = ECHO_MIN_SPEECH_MS if agent_speaking else MIN_SPEECH_MS
            if self.speech_ms < min_ms or len(self.buffer) < MIN_TURN_SAMPLES:
                self.buffer = []
                self.silence = 0
                self.speech_ms = 0
                self._in_speech = False
                self._onset_fired = False
                return None, onset
            turn = self._finish_turn()
            return turn, onset
        return None, onset