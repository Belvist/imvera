"""Per-call session: the barge-in dialogue loop (G3 acceptance core).

One ``CallSession`` owns one answered FreeSWITCH channel:

    attach tap (uuid_record stereo, LEFT=caller)
        -> greeting via /say + broadcast playback
        -> always-on VAD on LEFT
            | barge-in onset  -> uuid_break + POST stream-cancel (gen++)
            | completed turn  -> turn WAV -> POST turn_stream (bg)
        -> poll segment_dir, play seg-NNNN.wav sequentially
        -> on hangup: uuid_record stop + POST /calls/<id>/end

Cancellation model (matches the 4 acceptance tests):
  * user speaks while Vera plays -> barge_onset -> uuid_break stops audio
    in <=300 ms (PLAYBACK_STOP confirms), stream-cancel invalidates the old
    LLM/TTS generation, and the FULL utterance keeps being buffered by the
    VAD -> nothing is clipped (tests 2, 3);
  * segments of a cancelled generation are never started
    (``self.suppress``), done.json still clears the streaming flag ->
    no stale audio and no wedged state (test 4);
  * speaking after Vera finished needs no cancellation at all -> plain
    turn submission (test 1).

All of this is single-threaded: the runtime loop calls ``on_tick`` and
``handle_event``; nothing here blocks on network I/O except the ESL
broadcast/break calls, which are fast command replies.
"""
import logging
import os
import shutil
import time

try:
    from .agent_http import AgentClient, AgentError
    from .esl_client import EslClient
    from .media_tap import LiveWavReader, write_wav, SAMPLE_RATE
    from .vad import VAD, MIN_TURN_SAMPLES
except ImportError:  # run as a plain script (python3 voice_runtime/...py)
    from agent_http import AgentClient, AgentError
    from esl_client import EslClient
    from media_tap import LiveWavReader, write_wav, SAMPLE_RATE
    from vad import VAD, MIN_TURN_SAMPLES

DEFAULT_GREETING = "Здравствуйте! Это Имвэра. Как вы себя чувствуете?"
VAD_STEP = int(SAMPLE_RATE * 0.03)  # ~480 samples = 30 ms per VAD feed
TAP_VALID_GRACE = 5.0   # sec to see a VALID growing WAV before refusing


class CallSession:
    def __init__(self, fs_uuid, esl, agent, workdir, caller_id=None, log=None):
        self.fs_uuid = fs_uuid
        self.esl = esl
        self.agent = agent
        self.workdir = workdir
        self.caller_id = caller_id
        self.log = log or (lambda m: None)
        self.call_id = None
        self.tap_path = None
        self.reader = None
        self.vad = VAD()
        self.turn_no = 0
        self.playing = False          # a file is currently audible on the leg
        self.current_file = None
        self.streaming = False        # turn_stream POST is in flight
        self.suppress = False         # cancelled gen: do not start new segs
        self.segdir = None
        self.next_seg = 1
        self.seg_files = set()
        self.started = time.monotonic()
        self.greeting_attempted = False
        self._play_end = None

    # ---- lifecycle ------------------------------------------------------
    def start(self):
        # CALLER_ID (2026-08-29, FIXES_PLAN P2): the agent's new_call()
        # enables the 5-topic check-in agenda and the family-questions
        # snapshot ONLY when caller_id is present. Without it the realtime
        # path was a chatbot with no agenda and family questions stuck
        # pending forever.
        try:
            payload = {"caller_id": self.caller_id} if self.caller_id else {}
            self.call_id = self.agent.create_call(payload)
        except AgentError as e:
            self.log("create_call failed: %s" % e)
            return False
        if not self.call_id:
            self.log("create_call returned no call_id")
            return False
        os.makedirs(self.workdir, exist_ok=True)
        self.tap_path = os.path.join(self.workdir, "tap.wav")
        # record_stereo must be set BEFORE uuid_record starts: LEFT=caller.
        # On this FS build it is ONLY safe this way (setVar-then-record);
        # setting it the Lua way or after the record start produces the
        # broken 44-byte empty tapes that made VERA "answer nonsense".
        try:
            self.esl.uuid_setvar(self.fs_uuid, "record_stereo", "true")
            ret = self.esl.uuid_record_start(self.fs_uuid, self.tap_path)
        except Exception as e:  # noqa: BLE001
            self.log("tap attach failed: %s" % e)
            self._abort_agent_call()
            return False
        self.log("tap: call=%s uuid=%s rec=%r" %
                 (self.call_id, self.fs_uuid[:8], ret[:40]))
        if not str(ret).startswith("+OK"):
            self.log("tap: record did not start (%r) — refusing session"
                     % ret[:80])
            self._abort_agent_call()
            return False

        # Refuse to run a conversation on a broken/empty tape: this FS build
        # writes garbage 44-byte WAVs after a bad record_stereo state, and
        # feeding those to VAD/STT produced hallucinated "speech" (the
        # "она ерунду говорит" symptom). Wait for a VALID header AND the
        # first payload bytes; otherwise bail out before greeting.
        self.reader = LiveWavReader(self.tap_path)
        deadline = time.monotonic() + TAP_VALID_GRACE
        while time.monotonic() < deadline:
            self.reader.probe()
            if self.reader.broken:
                break
            if self.reader.audio_bytes() > 0:
                break
            time.sleep(0.1)
        if self.reader.broken or self.reader.audio_bytes() <= 0:
            self.log("tap invalid/empty (%d bytes, broken=%s) — "
                     "refusing session" % (self.reader.size,
                                           self.reader.broken))
            self.esl.uuid_record_stop(self.fs_uuid)
            if os.path.isdir(self.workdir):
                shutil.rmtree(self.workdir, ignore_errors=True)
            self._abort_agent_call()
            return False
        self.log("tap OK channels=%d rate=%d" %
                 (self.reader.channels, self.reader.rate))
        self._greet()
        return True

    def _abort_agent_call(self):
        try:
            self.agent.end_call(self.call_id)
        except Exception as e:  # noqa: BLE001
            self.log("end_call failed: %s" % e)

    def _greet(self):
        try:
            path = self.agent.say(DEFAULT_GREETING)
        except Exception as e:  # noqa: BLE001
            self.log("greeting TTS failed: %s" % e)
            return
        if not path:
            self.log("greeting: no wav_path from /say")
            return
        self.greeting_attempted = True
        self._play(path)

    # ---- event/loop entry points (called by the runtime loop) ------------
    def handle_event(self, ev):
        name = ev.get("Event-Name")
        if name == "PLAYBACK_STOP":
            self.playing = False
            self.current_file = None
            self._play_end = None
        elif name == "CHANNEL_HANGUP" or name == "DESTROY":
            pass  # stop() is invoked by the runtime on the tracked UUID

    def on_tick(self, now):
        self._drain_tap()
        self._pump_segments(now)

    def _drain_tap(self):
        if self.reader is None or self.reader.broken:
            return  # never feed VAD/STT garbage from a broken tape
        samples = self.reader.read_new()
        if not samples:
            return
        for i in range(0, len(samples), VAD_STEP):
            chunk = samples[i:i + VAD_STEP]
            ms = 1000.0 * len(chunk) / SAMPLE_RATE
            turn, onset = self.vad.feed(chunk, ms,
                                        agent_speaking=self.playing)
            if onset:
                self._on_barge_in()
            if turn:
                self._on_turn(turn)

    # ---- barge-in --------------------------------------------------------
    def _on_barge_in(self):
        self.log("BARGE-IN onset")
        if self.playing:
            self.log("  -> uuid_break (barge-in)")
            try:
                self.esl.api_break(self.fs_uuid)
            except Exception as e:  # noqa: BLE001
                self.log("  uuid_break failed: %s" % e)
            self.playing = False      # optimistic; PLAYBACK_STOP confirms
            self.current_file = None
            self._play_end = None
        if self.streaming:
            self._cancel_stream()

    def _cancel_stream(self):
        self.suppress = True          # old gen: never start its segments
        try:
            self.agent.stream_cancel(self.call_id)
            self.log("  stream-cancel posted")
        except Exception as e:  # noqa: BLE001
            self.log("  stream-cancel failed: %s" % e)

    # ---- turn submission --------------------------------------------------
    def _on_turn(self, turn):
        if len(turn) < MIN_TURN_SAMPLES:
            return
        self.log("TURN complete (%d samples, %.2fs)" %
                 (len(turn), len(turn) / SAMPLE_RATE))
        if self.playing:
            try:
                self.esl.api_break(self.fs_uuid)
            except Exception as e:  # noqa: BLE001
                self.log("  uuid_break failed: %s" % e)
            self.playing = False
            self.current_file = None
            self._play_end = None
        if self.streaming:
            self._cancel_stream()
        self.turn_no += 1
        my_turn = self.turn_no
        wav = os.path.join(self.workdir, "turn_%04d.wav" % self.turn_no)
        write_wav(wav, turn, SAMPLE_RATE)
        segdir = os.path.join(self.workdir, "t%d" % self.turn_no)
        os.makedirs(segdir, exist_ok=True)
        self.segdir = segdir
        self.next_seg = 1
        self.seg_files = set()
        self.suppress = False
        self.streaming = True
        self.agent.turn_stream(
            self.call_id, [wav], segdir,
            on_done=lambda ok, info, _t=my_turn:
                self._stream_done(ok, info, _t))
        self.log("turn %d submitted -> %s" % (self.turn_no, wav))

    def _stream_done(self, ok, info, turn_no):
        self.log("turn %d stream %s%s" % (turn_no, "OK" if ok else "FAIL",
                                          " " + info if not ok else ""))
        if ok:
            # done.json (written by the agent) is what clears the streaming
            # flag in _pump_segments; nothing else to do here.
            return
        # HARD FAILURE (2026-08-29, FIXES_PLAN P2): a rejected/aborted
        # turn_stream (429 busy, 404 call swept, timeout, mid-stream
        # disconnect) will NEVER produce done.json, so without this the
        # session sat in streaming=True forever and went deaf to the
        # caller. Only unblock when this failure belongs to the CURRENT
        # turn — a stale callback from an older turn must not kill a
        # newer submission.
        if self.turn_no == turn_no:
            self.streaming = False
            self.suppress = False
            self.segdir = None
            self.log("turn %d stream FAILED -> session unblocked" % turn_no)

    # ---- segment playback -------------------------------------------------
    PLAYBACK_WATCHDOG_GRACE = 0.5   # s of slack after nominal file duration

    @staticmethod
    def _wav_duration(path):
        """Nominal duration (s) of a 16-bit PCM WAV from its header, or
        None when it cannot be read. Used by the PLAYBACK_STOP watchdog."""
        try:
            import wave
            with wave.open(path, "rb") as w:
                return w.getnframes() / float(w.getframerate() or 16000)
        except Exception:  # noqa: BLE001
            return None

    def _play(self, path):
        try:
            self.esl.play(self.fs_uuid, path)
        except Exception as e:  # noqa: BLE001
            self.log("playback failed %s: %s" % (path, e))
            return False
        self.playing = True
        self.current_file = path
        # WATCHDOG (2026-08-29, FIXES_PLAN P3): a lost PLAYBACK_STOP used to
        # leave playing=True forever, so _pump_segments never started the
        # remaining segments and the caller heard one sentence + silence.
        # Record the expected end (nominal duration + grace) and clear the
        # flag from on_tick if no PLAYBACK_STOP ever arrives.
        dur = self._wav_duration(path)
        self._play_end = (time.monotonic() + dur + self.PLAYBACK_WATCHDOG_GRACE
                          if dur is not None else None)
        self.log("   >> play %s (dur=%ss)" %
                 (os.path.basename(path),
                  "%.1f" % dur if dur is not None else "?"))
        return True

    def _maybe_watchdog_playing(self, now):
        """Clear a wedged playing flag if the file should have finished."""
        if self.playing and self._play_end is not None \
                and now >= self._play_end:
            self.log("   PLAYBACK_STOP watchdog: %s exceeded nominal "
                     "duration" % os.path.basename(self.current_file or "?"))
            self.playing = False
            self.current_file = None
            self._play_end = None

    def _pump_segments(self, now):
        self._maybe_watchdog_playing(now)
        if not self.streaming or not self.segdir:
            return
        if self.playing:
            return
        done = os.path.join(self.segdir, "done.json")
        while not self.playing:
            if not self.suppress:
                seg = os.path.join(self.segdir, "seg-%04d.wav" % self.next_seg)
                if os.path.exists(seg) and seg not in self.seg_files:
                    self.seg_files.add(seg)
                    self.next_seg += 1
                    self._play(seg)
                    return
            if os.path.exists(done):
                # drain any segments still landing right behind done.json
                nxt = os.path.join(self.segdir, "seg-%04d.wav" % self.next_seg)
                if not self.suppress and os.path.exists(nxt) \
                        and nxt not in self.seg_files:
                    self.seg_files.add(nxt)
                    self.next_seg += 1
                    self._play(nxt)
                    return
                self.streaming = False
                self.suppress = False
                self.log("turn %d stream finished" % self.turn_no)
                return
            return  # no new seg yet; poll again next tick

    # ---- teardown ---------------------------------------------------------
    def stop(self):
        try:
            self.esl.uuid_record_stop(self.fs_uuid)
        except Exception:  # noqa: BLE001
            pass
        if self.call_id:
            try:
                self.agent.end_call(self.call_id)
            except Exception as e:  # noqa: BLE001
                self.log("end_call failed: %s" % e)
        if os.path.isdir(self.workdir):
            shutil.rmtree(self.workdir, ignore_errors=True)
        self.log("session stopped (%.1fs)" % (time.monotonic() - self.started))