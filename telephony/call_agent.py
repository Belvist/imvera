#!/usr/bin/env python3
"""MossVoice Call Agent — turn-based telephone agent.

Bridges FreeSWITCH (via a Lua dialplan script) to the MossVoice engine:
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
"""
import argparse
import base64
import datetime
import http.client
import json
import os
import random
import re
import struct
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid

from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def _runtime_scripts_dir():
    """Resolve the runtime scripts dir hosting tts_common/backends.

    Priority: $MOSS_RUNTIME_SCRIPTS -> <repo>/runtime/scripts -> the installed
    app runtime (~/Library/...). Keeps the agent operable from the repository
    without depending on a machine-specific home path.
    """
    env = os.environ.get("MOSS_RUNTIME_SCRIPTS")
    if env:
        return env
    _here = os.path.dirname(os.path.abspath(__file__))
    _repo_runtime = os.path.join(os.path.dirname(_here), "runtime", "scripts")
    if os.path.isdir(_repo_runtime):
        return _repo_runtime
    support = os.path.expanduser("~/Library/Application Support/MossVoice")
    return os.path.join(support, "runtime", "scripts")


sys.path.insert(0, _runtime_scripts_dir())


# ----------------------------------------------------------------------------
# TTS daemon client (talks to the app's tts_server.py over HTTP)
# ----------------------------------------------------------------------------
class TTSClient:
    def __init__(self, ref_paths=None, reference_text="", port_file=None, port=None,
                 inference_steps=12, style_enabled=True, host=None):
        self.refs = ref_paths or []
        self.reference_text = reference_text
        self.port_file = port_file
        self._fixed_port = port
        # Docker: the TTS daemon lives on another host (the "voice" service).
        # Default is loopback so the all-in-one macOS deployment is unchanged.
        self.host = (host or os.environ.get("MOSS_TTS_HOST", "")
                     or "127.0.0.1")
        self.port = None
        self.inference_steps = inference_steps
        self.style_enabled = style_enabled

    def refresh(self):
        if self._fixed_port:
            self.port = self._fixed_port
            return
        if not self.port_file:
            self.port = None
            return
        try:
            with open(self.port_file) as f:
                self.port = int(f.read().strip())
        except Exception:
            self.port = None

    def health(self):
        self.refresh()
        if not self.port:
            return False, "TTS-демон не запущен (порт не найден)"
        try:
            req = urllib.request.Request(f"http://{self.host}:{self.port}/health")
            with urllib.request.urlopen(req, timeout=5) as r:
                obj = json.loads(r.read().decode())
            return bool(obj.get("ready")), str(obj.get("error") or "")
        except Exception as e:
            return False, str(e)

    def ready(self):
        ok, _ = self.health()
        return ok

    def generate(self, text):
        self.refresh()
        if not self.port:
            return None
        payload = {
            "text": text,
            "refs": self.refs,
            "reference_text": self.reference_text,
            "max_new_tokens": 2048,
            "cfg_value": 1.2,
            "inference_steps": self.inference_steps,
            "style_enabled": self.style_enabled,
        }
        try:
            req = urllib.request.Request(
                f"http://{self.host}:{self.port}/generate",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=600) as r:
                obj = json.loads(r.read().decode())
        except Exception as e:
            print(f"[call-agent] TTS error: {e}", flush=True)
            return None
        if not obj.get("ok"):
            return None
        return base64.b64decode(obj["wav_b64"])

    def stream(self, text, cancel_event=None, stream_id=None):
        """Yield TTS frames (dicts with wav_b64) as they are produced.

        Reads the TTS daemon's /stream endpoint frame-by-frame using the
        length-prefixed wire format (4-byte big-endian length + JSON).
        ``cancel_event`` (threading.Event) aborts generation and stops yielding.
        ``stream_id`` (AUDIT FIX) is passed to the TTS daemon so a separate
        /stream-cancel call can abort generation *server-side* instead of the
        client just dropping the socket.
        """
        self.refresh()
        if not self.port:
            return
        payload = {
            "text": text,
            "refs": self.refs,
            "reference_text": self.reference_text,
            "max_new_tokens": 2048,
            "cfg_value": 1.2,
            "inference_steps": self.inference_steps,
            "style_enabled": self.style_enabled,
        }
        if stream_id:
            payload["stream_id"] = stream_id
        conn = None
        try:
            conn = http.client.HTTPConnection(self.host, self.port, timeout=600)
            conn.request(
                "POST", "/stream",
                body=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            resp = conn.getresponse()
            buf = b""
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    break
                chunk = resp.read1(65536)
                if not chunk:
                    break
                buf += chunk
                while True:
                    if len(buf) < 4:
                        break
                    n = int.from_bytes(buf[:4], "big")
                    if len(buf) < 4 + n:
                        break
                    frame_payload = buf[4:4 + n]
                    buf = buf[4 + n:]
                    frame = json.loads(frame_payload.decode("utf-8"))
                    yield frame
                    if frame.get("done"):
                        return
        except Exception as e:
            print(f"[call-agent] TTS stream error: {e}", flush=True)
        finally:
            if conn is not None:
                conn.close()

    def cancel_stream_by_id(self, stream_id):
        """Ask the TTS daemon to abort the generation for ``stream_id``.

        This is the server-side half of barge-in cancellation: it stops the
        model work, not just the delivery. Failures are logged and swallowed —
        the generation will finish either way, we only lose latency.
        """
        self.refresh()
        if not self.port or not stream_id:
            return
        try:
            req = urllib.request.Request(
                f"http://{self.host}:{self.port}/stream-cancel",
                data=json.dumps({"stream_id": stream_id}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                r.read()
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] TTS stream-cancel error: {e}", flush=True)


# ----------------------------------------------------------------------------
# STT (Whisper via mlx_audio)
# ----------------------------------------------------------------------------
class STTEngine:
    def __init__(self):
        self._model = None

    def _ensure(self):
        import tts_common

        if self._model is None:
            self._model = tts_common.load_stt(tts_common.DEFAULT_STT_MODEL)
        return self._model

    def transcribe(self, wav_path):
        try:
            model = self._ensure()
            result = model.generate(
                wav_path,
                verbose=False,
                task="transcribe",
                language="ru",
            )
            text = (getattr(result, "text", "") or "").strip()
            return text or None
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] STT error: {e}", flush=True)
            return None

    def transcribe_clean(self, wav_path):
        """Transcribe and reject Whisper hallucinations on silence/one-word junk."""
        text = self.transcribe(wav_path)
        return clean_transcript(text)


# P0-REALTIME-CORE step 11: replace batch (whole-WAV) STT with a streaming,
# incremental transcription. Whisper decodes whole clips, so we approximate a
# true stream by decoding NON-OVERLAPPING hops of the incoming PCM: each hop
# is transcribed as soon as HOP_SECONDS of new audio has arrived, and that
# text is confirmed immediately (no overlap => no duplicate words). The full
# utterance is decoded once more at finish() — using the hop + a small tail —
# to produce the authoritative transcript that drives the dialogue engine.
STT_HOP_SECONDS = 3.0


def _pcm_to_wav_bytes(pcm, sample_rate):
    """int16 mono PCM list -> WAV bytes (reuses pcm_to_wav writer)."""
    return pcm_to_wav(struct.pack("<%dh" % len(pcm), *pcm), sample_rate)


class StreamingSTT:
    """Incremental windowed STT (P0-REALTIME-CORE step 11).

    ``feed(samples, final=False)`` accepts new PCM and returns
    (text_or_None, running_interim): a confirmed hop text is returned once
    enough NEW audio accumulated. Tail audio that fell short of a full hop is
    retained and decoded during ``finish()`` so no speech at the utterance
    boundary is lost.

    ``finish()`` returns the authoritative transcript for the whole turn
    (fresh full-window decode, junk-filtered). Safe to call from a single
    consumer thread; ``engine`` must expose ``transcribe(wav_path) -> str|None``
    (STTEngine fits; tests inject a fake).
    """

    def __init__(self, engine, sample_rate=16000, hop_seconds=STT_HOP_SECONDS):
        self._engine = engine
        self._rate = sample_rate or 16000
        self._hop = max(1, int(self._rate * hop_seconds))
        self._pending = []                     # not yet decoded int16 samples
        self._all = []                         # every sample seen this turn
        self._confirmed = []                   # confirmed hop texts
        self._final = None

    def _decode(self, samples):
        """Decode one window to text (raw; caller filters junk on finish)."""
        if not samples:
            return ""
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            with open(path, "wb") as f:
                f.write(_pcm_to_wav_bytes(samples, self._rate))
            text = self._engine.transcribe(path) or ""
            return text.strip()
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] streaming STT decode error: {e}", flush=True)
            return ""
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def feed(self, samples, final=False):
        """Append PCM. Returns (hop_text_or_None, running_interim).

        AUDIT FIX: each decoded hop is junk-filtered immediately (Whisper
        hallucinations like "спасибо" on near-silence were previously only
        filtered in finish(), so interim hops could carry junk into the
        dialogue engine's interim transcript and meta frames).
        """
        self._pending.extend(list(samples))
        self._all.extend(list(samples))
        hop_texts = []
        while len(self._pending) >= self._hop and not final:
            win = self._pending[: self._hop]
            self._pending = self._pending[self._hop:]
            text = clean_transcript(self._decode(win))
            if text:
                self._confirmed.append(text)
                hop_texts.append(text)
        if final and self._pending:
            text = clean_transcript(self._decode(self._pending))
            if text:
                self._confirmed.append(text)
            self._pending = []
        interim = " ".join(self._confirmed)
        hop = hop_texts[-1] if hop_texts else None
        return hop, interim

    def finish(self):
        """Return the authoritative clean transcript for the whole turn.

        Fast path (common): concatenate the already-decoded hop texts. This
        keeps reply latency low — the hops were each decoded once already.

        CONVERSATION FIX (fallback): when the hop concatenation is empty or
        unusable, fall back to a SINGLE decode of the whole utterance. This
        recovers phrases the per-hop path missed without paying the cost of a
        full re-decode on every turn.
        """
        primary = clean_transcript(" ".join(self._confirmed))
        # LATENCY FIX: a sub-quarter-second tail is almost always breath/noise —
        # decoding it cost up to 3 s because Whisper loops on near-silence
        # fragments. Skip it; anything audible is covered by the hops.
        if self._pending and len(self._pending) >= int(self._rate * 0.25):
            text = clean_transcript(self._decode(self._pending))
            if text:
                primary = clean_transcript(
                    (primary + " " if primary else "") + text)
        self._pending = []
        self._final = primary
        if self._final:
            return self._final
        # nothing usable from hops: decode the whole turn once as a safety net
        if self._all:
            self._final = clean_transcript(self._decode(self._all))
        return self._final


# Whisper often hallucinates on near-silence / very short clips.
# AUDIT FIX: Russian filler/hallucination phrases added — "спасибо", "пока"
# etc. were slipping through and, pre-fix, became phantom user turns.
_JUNK_RE = re.compile(
    r"^(\s*"
    r"(i|the|a|an|and|so|uh|um|huh|what|is it|are you|are you awake|do you)"   # single filler words
    r"[\s.,!?]*"
    r"|"
    r"(thank you|thanks|thanks for watching|thanks for listening|bye|bye-bye|"
    r"goodbye|good bye|hello|hi|next|you know|uh huh|mm hmm|hmm|okay|ok)"
    r"[\s.,!?]*"
    r"|"
    r"(спасибо|пока|пока-пока|всё|все|да|нет|ну|ага|угу|а|о|э|мм|хм|"
    r"привет|здравствуйте|до свидания|хорошо|ладно|понятно|ясно)"
    r"[\s.,!?]*"
    r")$",
    re.IGNORECASE,
)

# If the SAME word repeats >=3 times it's a Whisper noise-hallucination
# ("Next Next Next...", "Bye Bye Bye..."), not real speech.
def _is_repetition(text):
    words = re.findall(r"[а-яёa-z]+", text.lower())
    if len(words) < 3:
        return False
    if len(set(words)) == 1 and len(words) >= 3:
        return True
    return False


def save_user_wav(outdir, wav_path, call_id=None, turn_id=None):
    """Copy the caller's audio to the call archive so it can be replayed later.

    Recordings are isolated per call: ``{outdir}/{call_id}/user-{turn}.wav``.
    A turn id is a per-call counter, so two simultaneous calls never collide.
    """
    if not wav_path or not os.path.exists(wav_path):
        return None
    if call_id:
        outdir = os.path.join(outdir, call_id)
    os.makedirs(outdir, exist_ok=True)
    stub = f"user-{turn_id:04d}.wav" if turn_id is not None \
        else f"user-{datetime.datetime.now().strftime('%H%M%S')}.wav"
    p = os.path.join(outdir, stub)
    try:
        import shutil

        shutil.copyfile(wav_path, p)
        return p
    except OSError:
        return None


# CONVERSATION FIX: real short answers ("да", "нет", "хорошо", "помощь") were
# being discarded by the hallucination junk filter, so the agent answered
# "Повторите, пожалуйста" to perfectly valid one-word replies — the most
# common complaint of a call that "behaves strangely". The audio reaching
# this filter has already been gated by VAD/endpointing (there WAS speech),
# so a canonical short answer is recovered here instead of being dropped.
_SHORT_ANSWER_MAP = {
    "да": "да", "ага": "да", "угу": "да", "конечно": "да", "есть": "да",
    "окей": "да", "ок": "да", "давай": "да",
    "нет": "нет", "неа": "нет", "не нужно": "помощь не нужна",
    "не надо": "помощь не нужна", "нет спасибо": "помощь не нужна",
    "хорошо": "всё хорошо", "всё хорошо": "всё хорошо", "все хорошо": "всё хорошо",
    "нормально": "всё нормально", "норм": "всё нормально",
    "все нормально": "всё нормально", "всё нормально": "всё нормально",
    "неплохо": "всё нормально", "терпимо": "всё терпимо", "так себе": "так себе",
    "плохо": "всё плохо", "не важно": "неважно",
    "неважно": "неважно", "ничего": "ничего не нужно",
    "помощь": "нужна помощь", "помощь нужна": "нужна помощь",
    "помощь требуется": "нужна помощь", "нужна помощь": "нужна помощь",
}

_SHORT_ANSWER_WORDS = frozenset((
    "всё", "все", "да", "ага", "угу", "ок", "окей", "давай", "неплохо",
    "хорошо", "нормально", "норм", "терпимо", "неважно", "плохо",
    "помощь", "требуется", "нужна", "нужно", "надо", "не", "нуждаюсь",
    "нет", "нет спасибо", "не нужно", "не надо", "ничего", "спасибо",
    "есть", "конечно", "неа",
))


def short_real_answer(raw):
    """Return the canonical form of a short real answer, or None.

    Only applies to very short (<=3 words) utterances where EVERY word is a
    known answer word — filters hallucinated fragments out while keeping
    "нет спасибо" intact.
    """
    if not raw:
        return None
    t = raw.strip().lower()
    t = re.sub(r"[.,!?…:;]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return None
    words = t.split()
    if len(words) > 3:
        return None
    if not all(w in _SHORT_ANSWER_WORDS for w in words):
        return None
    return _SHORT_ANSWER_MAP.get(t)


def clean_transcript(text):
    if not text:
        return None
    t = text.strip()
    # drop very short/fragmentary results
    if len(t) < 2:
        return None
    # drop whisper filler/hallucination phrases
    if _JUNK_RE.match(t):
        # CONVERSATION FIX: keep genuine short answers — the junk regex
        # intentionally overlaps them ("всё", "хорошо", "да", "нет"), yet a
        # VAD/endpoint-gated utterance that transcribes to exactly one of
        # them is a real reply, not hallucination.
        short = short_real_answer(t)
        if short:
            return short
        return None
    # drop repeating-word hallucinations ("Next Next Next...")
    if _is_repetition(t):
        return None
    # keep multi-word spoken turns
    return t


# ----------------------------------------------------------------------------
# Agent logic — MVERA wellness-check call
# ----------------------------------------------------------------------------
# MVERA: сервис сам звонит пожилому человеку, ведёт короткий разговор,
# спрашивает о самочувствии и необходимости помощи, а после — отдаёт
# родственнику вердикт: всё в порядке / требуется внимание / не ответил /
# обнаружена опасность.

MVERA_GREETING = "Здравствуйте! Это МВЕРА. Как вы себя чувствуете?"

OK_WORDS = ("хорош", "нормал", "порядк", "отлично", "прекрас", "замечатель",
            "неплохо", "бодр", "здоров", "всё ок", "в порядке", "не жал",
            "приемле", "норм")
BAD_WORDS = ("плохо", "не очень", "слабо", "устал", "устала", "худо",
             "нездор", "подавле", "груст", "тревожно", "сильно устал",
             "неважно", "не важ", "хуже", "тяжел", "тревог", "сильно плохо")
DISTRESS_WORDS = ("скора", "упал", "упала", "ушиб", "сильно болит",
                  "не могу встать", "не встаю", "трудно дышать", "не дыш",
                  "температур", "всё болит", "вызовите врача", "врача",
                  "неотложн", "срочно", "проанализ", "скорой", "не дышать")
MED_WORDS = ("принял", "приняла", "принимал", "принимала", "принял лекарство",
             "выпил", "выпила", "пью таблетки", "лекарства", "таблетки",
             "таблетку", "таблетку принял")
HELP_WORDS = ("помощь", "помогите", "помочь", "купить", "продукты", "магазин",
              "нужны лекар", "надо лекар", "врачу", "в больницу", "попросить",
              "помоге", "сходить", "позвонить близким")


# ----------------------------------------------------------------------------
# VERA live replies — the answer-generation model runs as its own service
# (llm_server.py, port 9500). This client talks to it over HTTP; if the
# daemon is down it falls back to loading the model in-process, and if that
# also fails the agent degrades to scripted canned phrases. Either way a
# call never stalls.
# ----------------------------------------------------------------------------
VERA_LLM_ID = os.environ.get("MOSS_LLM_MODEL", "mlx-community/Qwen3-1.7B-8bit")
VERA_LLM_URL = os.environ.get("MOSS_LLM_URL", "http://127.0.0.1:9500")

VERA_SYSTEM_PROMPT = (
    "Ты — Вера, молодая девушка, тёплая и заботливая телефонная помощница "
    "службы МВЕРА. Твоя задача — узнать о самочувствии человека по телефону, "
    "услышать его и при необходимости предложить помощь.\n"
    "Отвечай как живой человек: слушай собеседника, откликайся именно на его "
    "слова (помнишь всё, что он уже сказал в этом звонке), сопереживай, "
    "задавай один конкретный уточняющий вопрос. НЕ копируй и НЕ пересказывай "
    "фразы собеседника дословно, не отвечай шаблоном.\n"
    "Говори только на русском, коротко: одна-две фразы. Без медицинских "
    "советов и диагнозов: при жалобах на здоровье предлагай позвать кого-то "
    "из близких или вызвать помощь.\n"
    "Пиши только сам ответ — его прочитают вслух. Без кавычек, без подписей."
)


def _clean_llm(text):
    """Делает вывод модели безопасным для озвучки."""
    t = " ".join((text or "").split())
    t = re.sub(r"^(Вера|Assistant|Ответ)\s*:\s*", "", t, flags=re.IGNORECASE)
    parts = re.split(r"(?<=[.!?…])\s+", t)
    t = " ".join(parts[:2]).strip()
    if len(t) > 380:
        cut = t[:380].rfind(" ")
        t = t[:cut].rstrip() + "."
    return t


class LLMClient:
    """Qwen3 via mlx_lm for VERA's live replies.

    Lazily loaded ONE copy for the whole daemon (singleton), serialised with a
    lock because several calls may talk concurrently. Any failure returns None —
    the caller falls back to the scripted canned phrase, so the call never
    stalls when the LLM is unavailable.
    """

    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def get(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._model = None
        self._tok = None
        self._gen_lock = threading.Lock()
        self._loaded = False
        self._failed = False
        # Circuit breaker for the remote llm-server: after 3 consecutive
        # failures we stop probing it for 60 s and fall back to in-process.
        self._remote_failures = 0
        self._remote_down_until = 0.0
        # How long to wait at boot for the llm-server to finish loading
        # before loading a second model copy in-process.
        self._remote_wait = float(os.environ.get("MOSS_LLM_BOOT_WAIT", "60"))

    def _ensure(self):
        return self._ensure_local()

    def _ensure_local(self):
        if self._loaded or self._failed:
            return self._loaded
        with self._gen_lock:
            if self._loaded or self._failed:
                return self._loaded
            try:
                from mlx_lm import load as mlx_load
                self._model, self._tok = mlx_load(VERA_LLM_ID)
                self._loaded = True
                print(f"[call-agent] LLM ready in-process ({VERA_LLM_ID})", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[call-agent] LLM unavailable ({e}); scripted replies "
                      "only", flush=True)
                self._failed = True
                self._model = None
        return self._loaded

    def remote_ready(self, timeout=3.0):
        """Wait for the dedicated answer-generation daemon.

        If the daemon answers /health (even while its model is still loading)
        we wait up to ``wait_up`` for ready=True instead of loading a SECOND
        copy of the model in-process (RAM). If it does not answer at all we
        give up fast and fall back to in-process loading.
        """
        deadline = time.time() + self._remote_wait
        while time.time() < deadline:
            reachable = False
            try:
                req = urllib.request.Request(VERA_LLM_URL.strip("/") + "/health")
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    obj = json.loads(r.read().decode())
                reachable = True
                if obj.get("ready"):
                    self._remote_failures = 0
                    self._remote_down_until = 0.0
                    return True
            except Exception:  # noqa: BLE001
                if not reachable:
                    # daemon absent — don't stall startup for 60 s on it
                    time.sleep(0.3)
                    return False
            time.sleep(1.0)
        return False

    def ready(self):
        """Prefer the separate llm-server; load the model in-process only as
        a fallback so startup stays fast when the service is already up."""
        if self.remote_ready():
            return True
        return self._ensure_local()

    def _chat_remote(self, messages, max_tokens, temp, timeout):
        if time.time() < self._remote_down_until:
            return None
        try:
            req = urllib.request.Request(
                VERA_LLM_URL.strip("/") + "/chat",
                data=json.dumps({"messages": messages, "max_tokens": max_tokens,
                                 "temp": temp}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                obj = json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            self._remote_failures += 1
            if self._remote_failures >= 3:
                self._remote_down_until = time.time() + 60
            print(f"[call-agent] llm-server unreachable ({e})", flush=True)
            return None
        if obj.get("ok") and obj.get("text"):
            self._remote_failures = 0
            self._remote_down_until = 0.0
            return obj["text"]
        self._remote_failures += 1
        return None

    def chat(self, messages, max_tokens=100, temp=0.65, timeout=60):
        """Generate a reply for chat-style ``messages``. Returns cleaned text
        or None on any failure/timeout. Tries the llm-server first, then the
        in-process model — the scripted fallback is the final safety net."""
        out = self._chat_remote(messages, max_tokens, temp, min(timeout, 30))
        if out is None:
            out = self._chat_local(messages, max_tokens, temp, timeout)
        if not out:
            return None
        cleaned = _clean_llm(out)
        if not cleaned or len(cleaned) < 4:
            return None
        low = cleaned.lower()
        if any(x in low for x in ("as an ai", "к сожалению, я не могу",
                                  "i cannot", "я не могу помочь")):
            return None
        return cleaned

    def _chat_local(self, messages, max_tokens=100, temp=0.65, timeout=60):
        """Original in-process generation (fallback when llm-server is down)."""
        if not self._ensure_local():
            return None
        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler
        prompt = None
        try:
            prompt = self._tok.apply_chat_template(
                messages, add_generation_prompt=True, enable_thinking=False)
        except Exception:  # noqa: BLE001
            return None
        t0 = time.time()
        with self._gen_lock:
            try:
                out = generate(self._model, self._tok, prompt=prompt,
                               max_tokens=max_tokens, verbose=False,
                               sampler=make_sampler(temp=temp))
            except Exception as e:  # noqa: BLE001
                print(f"[call-agent] LLM error: {e}", flush=True)
                return None
        if time.time() - t0 > timeout:
            return None
        return out

    # ---- token streaming (REALTIME FIX, Stage 5) ----------------------------
    # The reply is generated as DELTAS so the dialogue engine can send the
    # first complete sentence to TTS while the rest is still being generated:
    #   remote llm-server /chat_stream  ->  in-process mlx stream_generate
    #   ->  batch chat() as a single-delta last resort.
    def chat_stream(self, messages, max_tokens=100, temp=0.65, timeout=60):
        """Yield text deltas. Never raises: a failed backend silently moves
        to the next fallback tier; an empty stream means the caller uses its
        canned fallback phrase."""
        gen = self._chat_stream_remote(
            messages, max_tokens, temp, min(timeout, 60))
        if gen is not None:
            try:
                for d in gen:
                    if d:
                        yield d
                return
            except Exception as e:  # noqa: BLE001
                self._remote_failures += 1
                if self._remote_failures >= 3:
                    self._remote_down_until = time.time() + 60
                print(f"[call-agent] llm-server stream error ({e}); "
                      "falling back to in-process", flush=True)
        for d in self._chat_stream_local(messages, max_tokens, temp, timeout):
            if d:
                yield d

    def _chat_stream_remote(self, messages, max_tokens, temp, timeout):
        """Connect EAGERLY to /chat_stream; return a delta-generator, or None
        when the daemon is absent / circuit-open / rejects us."""
        if time.time() < self._remote_down_until:
            return None
        try:
            parts = urllib.parse.urlsplit(VERA_LLM_URL.strip("/"))
            conn = http.client.HTTPConnection(
                parts.hostname or "127.0.0.1", parts.port or 9500,
                timeout=timeout)
            body = json.dumps({"messages": messages,
                               "max_tokens": max_tokens,
                               "temp": temp}).encode()
            conn.request("POST", parts.path + "/chat_stream"
                         if parts.path else "/chat_stream",
                         body=body,
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            if resp.status != 200:
                resp.read(256)
                conn.close()
                raise ConnectionError(f"HTTP {resp.status}")
        except Exception as e:  # noqa: BLE001
            self._remote_failures += 1
            if self._remote_failures >= 3:
                self._remote_down_until = time.time() + 60
            print(f"[call-agent] llm-server /chat_stream unreachable ({e})",
                  flush=True)
            return None

        def _frames():
            buf = b""
            while True:
                chunk = resp.read1(65536)
                if not chunk:
                    break
                buf += chunk
                while len(buf) >= 4:
                    n = int.from_bytes(buf[:4], "big")
                    if len(buf) < 4 + n:
                        break
                    frame = json.loads(buf[4:4 + n].decode("utf-8"))
                    buf = buf[4 + n:]
                    if frame.get("done"):
                        self._remote_failures = 0
                        self._remote_down_until = 0.0
                        conn.close()
                        return
                    if frame.get("error"):
                        conn.close()
                        raise RuntimeError(frame["error"])
                    if frame.get("delta"):
                        yield frame["delta"]
            conn.close()

        return _frames()

    def _chat_stream_local(self, messages, max_tokens=100, temp=0.65,
                           timeout=60):
        """In-process mlx streaming; batch generation as the last resort."""
        if not self._ensure_local():
            out = self._chat_local(messages, max_tokens, temp, timeout)
            if out:
                yield out
            return
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler
        try:
            prompt = self._tok.apply_chat_template(
                messages, add_generation_prompt=True, enable_thinking=False)
        except Exception:  # noqa: BLE001
            out = self._chat_local(messages, max_tokens, temp, timeout)
            if out:
                yield out
            return
        with self._gen_lock:
            try:
                for resp in stream_generate(
                        self._model, self._tok, prompt=prompt,
                        max_tokens=max_tokens,
                        sampler=make_sampler(temp=temp)):
                    if resp.text:
                        yield resp.text
            except Exception as e:  # noqa: BLE001
                print(f"[call-agent] LLM stream error: {e}", flush=True)


# ----------------------------------------------------------------------------
# Provider adapters (Architecture plan, Stage 1 + Stage 5)
# ----------------------------------------------------------------------------
# The agent layer programs against the duck-API of STTEngine / LLMClient /
# TTSClient. These adapters give the SAME surface to the cloud providers in
# moss_providers, so a vendor swap is an env change, not a code change:
#   MOSS_STT_PROVIDER=openai      (needs OPENAI_API_KEY)
#   MOSS_LLM_PROVIDER=openai      (needs OPENAI_API_KEY)
#   MOSS_TTS_PROVIDER=elevenlabs  (needs ELEVENLABS_API_KEY + voice id)
# Missing key / missing config -> loud log + automatic local fallback.

def _maybe_cloud_stt(local_engine):
    if os.environ.get("MOSS_STT_PROVIDER", "local").lower() != "openai":
        return local_engine
    from moss_providers import OpenAISTTProvider
    p = OpenAISTTProvider()
    if not p.ready():
        print("[call-agent] MOSS_STT_PROVIDER=openai but OPENAI_API_KEY is "
              "missing — using local STT", flush=True)
        return local_engine
    print("[call-agent] STT provider: openai (whisper API)", flush=True)
    return CloudSTTAdapter(p)


def _maybe_cloud_llm(local_client):
    if os.environ.get("MOSS_LLM_PROVIDER", "local").lower() != "openai":
        return local_client
    from moss_providers import OpenAILLMProvider
    p = OpenAILLMProvider()
    if not p.ready():
        print("[call-agent] MOSS_LLM_PROVIDER=openai but OPENAI_API_KEY is "
              "missing — using local LLM", flush=True)
        return local_client
    print("[call-agent] LLM provider: openai", flush=True)
    return CloudLLMAdapter(p)


def _maybe_cloud_tts(local_client):
    if os.environ.get("MOSS_TTS_PROVIDER", "local").lower() != "elevenlabs":
        return local_client
    from moss_providers import ElevenLabsTTSProvider
    p = ElevenLabsTTSProvider()
    if not p.ready():
        print("[call-agent] MOSS_TTS_PROVIDER=elevenlabs but "
              "ELEVENLABS_API_KEY/MOSS_TTS_ELEVEN_VOICE missing — using "
              "local MOSS TTS", flush=True)
        return local_client
    print("[call-agent] TTS provider: elevenlabs", flush=True)
    return CloudTTSAdapter(p)


def _maybe_session_store():
    """Stage 6: Redis-backed session store when configured, else in-memory.
    ``build_session_store`` already falls back to memory when Redis is
    unreachable, so dialogue state can never break the call path."""
    try:
        from moss_providers import build_session_store
        store = build_session_store()
        print(f"[call-agent] session store: "
              f"{type(store).__name__}", flush=True)
        return store
    except Exception as e:  # noqa: BLE001
        print(f"[call-agent] session store unavailable ({e}); "
              f"using in-memory", flush=True)
        from moss_providers import MemorySessionStore
        return MemorySessionStore()


class CloudSTTAdapter:
    """STTProvider -> STTEngine duck-API (``transcribe(wav_path)``)."""

    def __init__(self, provider):
        self.provider = provider

    def transcribe(self, wav_path):
        try:
            with open(wav_path, "rb") as f:
                wav = f.read()
            return self.provider.transcribe(wav)
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] cloud STT error: {e}", flush=True)
            return None

    def transcribe_clean(self, wav_path):
        return clean_transcript(self.transcribe(wav_path))

    def ready(self):
        try:
            return self.provider.ready()
        except Exception:  # noqa: BLE001
            return False


class CloudLLMAdapter:
    """LLMProvider -> LLMClient duck-API (``chat(messages, ...)``)."""

    def __init__(self, provider):
        self.provider = provider

    def ready(self):
        try:
            return self.provider.ready()
        except Exception:  # noqa: BLE001
            return False

    def chat(self, messages, max_tokens=100, temp=0.65, timeout=60):
        try:
            return self.provider.chat(messages, max_tokens=max_tokens,
                                      temp=temp, timeout=min(timeout, 30))
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] cloud LLM error: {e}", flush=True)
            return None


class CloudTTSAdapter:
    """TTSProvider -> TTSClient duck-API (generate/stream/cancel)."""

    # ElevenLabs pcm_44100 delivers raw 16-bit mono PCM; wrap it in a WAV so
    # wav_to_pcm / save_wav downstream keep working unchanged.
    PCM_RATE = 44100

    def __init__(self, provider):
        self.provider = provider

    def ready(self):
        try:
            return bool(self.provider.ready())
        except Exception:  # noqa: BLE001
            return False

    def generate(self, text):
        try:
            return self._ensure_wav(self.provider.synthesize(text))
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] cloud TTS error: {e}", flush=True)
            return None

    def stream(self, text, cancel_event=None, stream_id=None):
        try:
            for frame in self.provider.stream(
                    text, cancel_event=cancel_event, stream_id=stream_id):
                if cancel_event is not None and cancel_event.is_set():
                    return
                if frame.get("wav_b64"):
                    wav = self._ensure_wav(base64.b64decode(frame["wav_b64"]))
                    if wav:
                        frame = {**frame,
                                 "wav_b64": base64.b64encode(wav).decode("ascii")}
                yield frame
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] cloud TTS stream error: {e}", flush=True)
            yield {"done": True}

    def cancel_stream_by_id(self, stream_id):
        # full-clip providers have no server-side generation to abort
        pass

    @classmethod
    def _ensure_wav(cls, raw):
        if not raw:
            return None
        if raw[:4] == b"RIFF":
            return raw
        import io as _io
        import wave as _wave
        buf = _io.BytesIO()
        try:
            with _wave.open(buf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(cls.PCM_RATE)
                w.writeframes(raw)
        except Exception:  # noqa: BLE001
            return None
        return buf.getvalue()


class Agent:
    """Turn-based MVERA wellness-call agent.

    Dialogue flow (the script) is preserved for safety — the step machine
    decides WHAT to ask/record. The WORDING of each reply is now generated by
    a local LLM (VERA persona) from the full conversation history, so replies
    sound warm and show she remembers what the caller said. If the LLM is
    unavailable/failed, the original canned phrases are used.
    """

    def __init__(self, config=None, llm=None):
        self.memory = []
        self.llm_history = []          # (role, text) for the LLM dialogue
        self.step = 0          # 0 -> first reply answers greeting wellbeing q
        self.status = "unknown"  # verdict: unknown -> ok/attention/alert
        self.notes = []
        self.done = False
        self.last_intent = ""
        self.config = config or {}
        self.llm = llm

    def reset(self):
        self.memory = []
        self.llm_history = []
        self.step = 0
        self.status = "unknown"
        self.notes = []
        self.done = False
        self.config = {}

    def _classify(self, text):
        t = " " + (text or "").lower() + " "
        if any(w in t for w in DISTRESS_WORDS):
            return "alert"
        # negated health words ("не плохо", "не так уж плохо") -> OK, not bad
        if "не плохо" in t or "не плох" in t or "неплохо" in t or "неплох" in t:
            return "ok"
        if any(w in t for w in BAD_WORDS):
            return "bad"
        if any(w in t for w in OK_WORDS):
            return "ok"
        return "unknown"

    def _vera_reply(self, user_text, intent, fallback):
        """Generate a live reply via the local LLM; fall back to the canned
        phrase when the model is unavailable or produces garbage."""
        if self.llm is None or user_text is None or not user_text.strip():
            return fallback
        history = self._build_history(user_text, intent)
        out = None
        try:
            with threading.Lock():
                out = self.llm.chat(history)
        except Exception:  # noqa: BLE001
            out = None
        if not out or len(out) < 4 or len(out) > 400:
            return fallback
        return out

    def _build_history(self, user_text, intent):
        history = [{"role": "system", "content": VERA_SYSTEM_PROMPT}]
        for role, txt in self.llm_history[-8:]:
            history.append({"role": "user" if role == "user" else "assistant",
                            "content": txt})
        if user_text and user_text.strip():
            history.append({"role": "user", "content": user_text.strip()})
        if intent:
            history.append({"role": "user", "content":
                            f"(Система: цель твоего ответа — {intent})"})
        return history

    # ---- reply planning + token streaming (REALTIME FIX, Stage 4+5) -------
    # plan_reply() runs the DETERMINISTIC state machine only (fast, under the
    # per-call lock): it decides the step, the verdict notes, the intent for
    # the model and the canned fallback phrase. The actual model generation
    # happens LATER outside the lock via reply_stream(), yielding deltas so
    # the first finished sentence can be sent to TTS while the rest of the
    # reply is still being generated. commit_reply() records the final text
    # in the dialogue history once it is known.

    def plan_reply(self, caller_text):
        """Run the MVERA state machine; return a reply plan without talking
        to any model. Plan keys:
            text      user utterance
            intent    LLM objective (None -> the fallback is the FINAL reply)
            fallback  canned phrase (also the garbage/timeout fallback)
        State mutations (memory, step, status, notes, llm_history user turn)
        happen HERE — safe under the per-call lock."""
        if caller_text:
            self.memory.append(caller_text)
            self.llm_history.append(("user", caller_text))
        tag = self._classify(caller_text)
        if tag == "alert":
            self.status = "alert"
            self.done = True
            return {"text": caller_text,
                    "intent": "успокоить, попросить оставаться на месте, "
                              "уточнить нужна ли скорая",
                    "fallback": random.choice([
                        "Останьтесь на месте, позвоню близким. Вам нужна скорая?",
                        "Не вставайте один, я предупрежу родных. Вызвать врача?",
                    ])}
        if self.step == 0:
            # The greeting (MVERA_GREETING) already asked "как вы себя
            # чувствуете?" — so this first reply IS the wellbeing answer.
            # Do NOT re-ask wellbeing; record the verdict and move straight
            # to the help question.
            self.step = 1
            if tag == "bad":
                self.status = "attention"
                self.notes.append("плохое самочувствие")
            elif tag == "ok":
                self.status = "ok"
            if tag == "bad":
                intent = ("мягко поддержать (человек чувствует себя плохо) и "
                          "спросить, нужна ли ему помощь")
            else:
                intent = ("порадоваться, что всё хорошо, и спросить, нужна ли "
                          "ему помощь")
            return {"text": caller_text, "intent": intent,
                    "fallback": self._ask_help()}
        if self.step == 1:
            self.step = 2
            self.done = True
            low = " " + (caller_text or "").lower() + " "
            takes_meds = any(w in low for w in MED_WORDS)
            if takes_meds:
                self.notes.append("принимает лекарства")
            wants_help = any(w in low for w in HELP_WORDS)
            negated = any(n in low for n in ("не нужн", "не надо", "нет", "не требу", "ничего не"))
            if "помощь" in low and negated:
                wants_help = False
            if tag == "alert" or wants_help:
                self.status = "attention"
                self.notes.append("требуется помощь" if wants_help else "плохое самочувствие")
            elif tag == "bad":
                self.status = "attention"
                self.notes.append("плохое самочувствие")
            else:
                # no distress, no help needed: default GREEN only if we have
                # a positive confirmation somewhere in the call
                if self.status != "attention":
                    self.status = "ok"
            self.memory.append(caller_text)
            if tag == "alert" or wants_help:
                intent = "сказать, что всё передаст родным, и тепло попрощаться"
            else:
                intent = "сказать, что всё записала, и тепло попрощаться"
            return {"text": caller_text, "intent": intent,
                    "fallback": self._goodbye()}
        self.done = True
        # no LLM needed: the canned goodbye IS the final reply
        return {"text": caller_text, "intent": None,
                "fallback": self._goodbye()}

    def reply_stream(self, plan):
        """Yield reply-text DELTAS for a plan (LLM path). A plan with
        intent=None yields its fallback as a single chunk. All failures are
        swallowed: the caller collects chunks and falls back to
        plan['fallback'] when nothing usable arrived."""
        if plan.get("intent") is None or self.llm is None \
                or not (plan.get("text") or "").strip():
            yield plan.get("fallback") or ""
            return
        history = self._build_history(plan.get("text"), plan.get("intent"))
        streamer = getattr(self.llm, "chat_stream", None)
        if streamer is None:
            out = None
            try:
                out = self.llm.chat(history)
            except Exception:  # noqa: BLE001
                out = None
            if out:
                yield out
            return
        try:
            for delta in streamer(history):
                if delta:
                    yield delta
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] reply stream error: {e}", flush=True)

    def commit_reply(self, reply_text):
        """Record the final assistant reply in the dialogue history (call
        AFTER generation finished; never before it starts)."""
        if reply_text:
            self.llm_history.append(("assistant", reply_text))

    def _ask_help(self):
        return random.choice([
            "Нужна ли вам помощь?",
            "Помощь требуется?",
            "Могу что-нибудь передать родным?",
        ])

    def _goodbye(self):
        return random.choice([
            "Спасибо! Всё передам. До свидания!",
            "Хорошо, записал. Всего доброго!",
        ])

    def _ask(self, text):
        """One turn of the MVERA script (blocking). Backwards-compatible
        wrapper over plan_reply()/reply_stream()/commit_reply() for callers
        that still expect a single final string."""
        plan = self.plan_reply(text)
        chunks = []
        for delta in self.reply_stream(plan):
            chunks.append(delta)
        reply = _clean_llm(("".join(chunks)).strip()) if plan.get("intent") \
            else ("".join(chunks)).strip()
        if plan.get("intent") and (not reply or len(reply) < 4
                                   or len(reply) > 400):
            reply = plan["fallback"]
        self.commit_reply(reply)
        return reply

    def reply(self, caller_text):
        return self._ask(caller_text)

    @property
    def finished(self):
        return self.done

    @property
    def outcome(self):
        """Вердикт для родственника. Never leave an unknown call as GREEN."""
        status = self.status
        if status == "unknown":
            status = "attention"  # cannot confirm wellbeing -> escalate
        return {"status": status, "notes": list(self.notes)}


# ----------------------------------------------------------------------------
# Recording / summary writer
# ----------------------------------------------------------------------------
class Recorder:
    def __init__(self, dirpath):
        self.base = dirpath
        os.makedirs(dirpath, exist_ok=True)
        self.call = None

    def new_call(self, call_id=None):
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        cid = (call_id or f"call-{ts}").replace("/", "_").replace("..", "")
        # per-call subdirectory so concurrent calls never overwrite each other
        self.dir = os.path.join(self.base, cid)
        os.makedirs(self.dir, exist_ok=True)
        self.call = {"id": cid, "start": ts, "turns": []}
        return self.call

    def add_turn(self, role, text, audio_path=None):
        if self.call is None:
            self.new_call()
        self.call["turns"].append({"role": role, "text": text, "audio": audio_path})
        with open(os.path.join(self.dir, "result.json"), "w") as f:
            json.dump(self.call, f, ensure_ascii=False, indent=2)

    def summary_path(self):
        if self.call is None:
            return None
        texts = [t["text"] for t in self.call["turns"] if t.get("text")]
        lines = [f"Телефонный разговор от {self.call['start']}"]
        for t in self.call["turns"]:
            if t.get("text"):
                who = "Собеседник" if t["role"] == "user" else "Ассистент"
                lines.append(f"{who}: {t['text']}")
        p = os.path.join(self.dir, "summary.txt")
        with open(p, "w") as f:
            f.write("\n".join(lines))
        return p


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------
class QuietHTTPServer(ThreadingHTTPServer):
    """AUDIT FIX: streaming clients drop connections mid-stream on every
    barge-in/timeout. The stdlib server used to print a full traceback per
    peer reset (the ConnectionResetError spam in call_agent.log). Benign
    resets are now ignored; real handler exceptions still surface."""

    daemon_threads = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError,
                            ConnectionAbortedError, TimeoutError)):
            return
        import traceback
        traceback.print_exc(limit=5)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    # AUDIT FIX: keep-alive handler threads used to block forever in readline
    # waiting for a next request that never comes, pinning a thread per dead
    # socket. A generous but finite timeout lets them exit.
    timeout = 30

    def log_message(self, *a):
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/health"):
            ok, err = self.server.serve.tts.health()
            self._json({"ok": True, "tts": ok, "error": err})
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith("/calls"):
            if path == "/calls" or path == "/calls/":
                self.server.serve.sweep_expired()
                self._json({"ok": True, "calls": self.server.serve.list_calls()})
                return
            if path.startswith("/calls/"):
                call_id = path.split("/")[2]
                try:
                    ctx = self.server.serve.get_call(call_id)
                except KeyError:
                    self._json({"ok": False, "error": "call not found"}, 404)
                    return
                self._json({
                    "ok": True,
                    "call_id": ctx.call_id,
                    "created_at": ctx.created_at,
                    "last_seen": ctx.last_seen,
                    "finished": ctx.finished,
                    "outcome": ctx.agent.outcome,
                    "caller_id": ctx.caller_id,
                    "turns": ctx.recorder.call.get("turns", []) if ctx.recorder.call else [],
                })
                return
        self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # ---- P0-SESSION-001 API -------------------------------------------------
        if path == "/calls" or path == "/new":
            payload = self._read_json_body()
            caller_id = (payload or {}).get("caller_id")
            call_id = self.server.serve.new_call(caller_id=caller_id)
            self._json({"ok": True, "call_id": call_id})
            return
        if path.startswith("/calls/"):
            rest = path[len("/calls/"):]
            segs = rest.split("/")
            call_id = segs[0]
            if len(segs) == 1 and segs[0] == "":
                call_id = self.server.serve.new_call()
                self._json({"ok": True, "call_id": call_id})
                return
            action = segs[1] if len(segs) > 1 else None
            if action == "end":
                try:
                    result = self.server.serve.end_call(call_id)
                except KeyError:
                    self._json({"ok": False, "error": "call not found"}, 404)
                    return
                self._json(result)
                return
            if action in ("turn", None):
                result = self._handle_turn(call_id)
                if result is not None:
                    self._write_json(result)
                return
            if action == "turn_stream":
                self._handle_turn_stream(call_id)
                return
            if action == "stream-cancel":
                try:
                    ctx = self.server.serve.get_call(call_id)
                except KeyError:
                    self._json({"ok": False, "error": "call not found"}, 404)
                    return
                ctx.cancel_event.set()
                # AUDIT FIX: abort on the TTS daemon too so a barge-in stops
                # the actual model work, not just our read loop.
                sid = ctx.stream_id
                if sid:
                    self.server.serve.tts.cancel_stream_by_id(sid)
                self._json({"ok": True, "cancelled": bool(ctx.streaming)})
                return
            self._json({"ok": False, "error": "not found"}, 404)
            return

        # ---- legacy endpoints ---------------------------------------------------
        if path == "/say":
            payload = self._read_json_body()
            text = (payload.get("text") or "").strip()
            ok = bool(self.server.serve.tts.ready())
            path_ = self.server.serve.greeting_wav(None if not text else text)
            resp = {"ok": ok and path_ is not None, "wav_path": path_}
            # Docker: the caller may not share our filesystem — return the
            # greeting audio inline instead of a path.
            if payload.get("wav_b64") and path_:
                try:
                    with open(path_, "rb") as f:
                        resp["wav_b64"] = base64.b64encode(f.read()).decode("ascii")
                except OSError:
                    pass
            self._json(resp)
            return
        if path == "/turn":
            result = self._handle_turn()
            if result is not None:
                self._write_json(result)
            return
        if path == "/turn_stream":
            self._handle_turn_stream()
            return
        self._json({"ok": False, "error": "not found"}, 404)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _write_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_turn_wav(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        ctype = self.headers.get("Content-Type", "")
        return self.server.serve.save_upload(raw, ctype)

    def _get_ctx_opt(self, call_id):
        try:
            return self.server.serve.get_call(call_id)
        except KeyError:
            return None

    def _handle_turn(self, call_id=None):
        wav_path, is_temp = self._read_turn_wav()
        if wav_path is None:
            self._json({"ok": False, "error": "no wav in upload"}, 400)
            return None
        ctx = None
        try:
            try:
                ctx = self.server.serve.begin_turn(call_id)
            except CallBusyError:
                self._json({"ok": False, "error": "call busy"}, 429)
                return None
            return self.server.serve.process_turn(wav_path, call_id=ctx.call_id)
        except KeyError:
            return {"ok": False, "error": "call not found"}
        finally:
            if ctx is not None:
                self.server.serve.end_turn(ctx)
            if is_temp:
                try:
                    os.remove(wav_path)
                except OSError:
                    pass

    def _handle_turn_stream(self, call_id=None):
        wav_path, is_temp = self._read_turn_wav()
        if wav_path is None:
            self._json({"ok": False, "error": "no wav in upload"}, 400)
            return
        ctx = None
        try:
            try:
                ctx = self.server.serve.begin_turn(call_id)
            except CallBusyError:
                self._json({"ok": False, "error": "call busy"}, 429)
                return
        except KeyError:
            self._json({"ok": False, "error": "call not found"}, 404)
            return
        cancel_event = ctx.cancel_event
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def write_frame(obj):
            payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            frame = len(payload).to_bytes(4, "big") + payload
            for i in range(0, len(frame), 48 * 1024):
                part = frame[i:i + 48 * 1024]
                self.wfile.write(b"%X\r\n" % len(part))
                self.wfile.write(part)
                self.wfile.write(b"\r\n")

        try:
            for frame in self.server.serve.process_turn_stream(
                    wav_path, call_id=call_id, cancel_event=cancel_event):
                write_frame(frame)
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except KeyError:
            try:
                write_frame({"error": "call not found", "done": True})
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            try:
                write_frame({"error": str(exc), "done": True})
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except Exception:  # noqa: BLE001
                pass
        finally:
            self.server.serve.end_turn(ctx)
            if is_temp:
                try:
                    os.remove(wav_path)
                except OSError:
                    pass


def parse_multipart_wav(raw, ctype):
    m = re.search(r"boundary=([^\s;]+)", ctype or "")
    if not m:
        return None
    boundary = m.group(1).encode()
    for part in raw.split(b"--" + boundary):
        if b"filename=" not in part[:300]:
            continue
        header, _, body = part.partition(b"\r\n\r\n")
        body = body.rstrip(b"\r\n--")
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        with open(path, "wb") as f:
            f.write(body)
        return path
    return None


DEFAULT_GREETING = "Здравствуйте! Это МВЕРА. Как вы себя чувствуете?"

# When a call has been idle for this long it is garbage-collected.
SESSION_TTL_SEC = 60 * 60


@dataclass
class CallContext:
    """Everything needed to run ONE phone call independently.

    P0-SESSION-001: a call's dialogue state (Agent), conversation recording
    (Recorder) and safety/dialogue scratch state live here, not in globals.
    Two concurrent calls never share or reset each other's state.

    AUDIT FIX: ``lock`` serialises every mutation of agent/recorder state for
    this call (two overlapping /turn requests were racing and corrupting
    result.json); ``turn_in_progress`` lets a second concurrent turn be
    rejected with HTTP 429 instead of interleaving with the first one.
    """
    call_id: str
    agent: Agent = field(default_factory=Agent)
    recorder: Recorder = field(default_factory=lambda: Recorder(""))
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    caller_id: str | None = None
    finished: bool = False
    safety_state: dict = field(default_factory=dict)
    dialogue_state: dict = field(default_factory=dict)
    outcome: dict = field(default_factory=dict)
    streaming: bool = False
    cancel_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    # SHORT lock guarding only the turn-in-progress flag: begin_turn must not
    # block on `lock` (which the running turn holds for the whole turn incl.
    # TTS generation), otherwise a second request would queue behind the first
    # instead of being rejected.
    turn_lock: threading.Lock = field(default_factory=threading.Lock)
    turn_in_progress: bool = False
    # AUDIT FIX: id of the TTS stream currently generating this call's reply,
    # so /stream-cancel can abort it server-side (not just client-side).
    stream_id: str = ""


class CallBusyError(Exception):
    """A turn for this call is already being processed."""

    def __init__(self, call_id):
        super().__init__(f"call {call_id} is busy")
        self.call_id = call_id


class Serve:
    def __init__(self, args):
        self.tts = _maybe_cloud_tts(TTSClient(
            ref_paths=args.refs,
            port_file=args.tts_port_file,
            port=args.tts_port,
            inference_steps=args.inference_steps,
            style_enabled=not args.no_style,
            host=getattr(args, "tts_host", None),
        ))
        self.stt = _maybe_cloud_stt(STTEngine())
        self.outdir = args.outdir
        self.args = args
        self.outdir = getattr(args, "outdir", None) or (
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "calls"))
        self.tmpdir = getattr(args, "tmpdir", None) or "/tmp/mossvoice_turns"
        os.makedirs(self.tmpdir, exist_ok=True)
        self._greeting_cache = {}
        self._greeting_lock = threading.Lock()
        self.sessions = {}
        self._sess_lock = threading.Lock()
        self.llm = _maybe_cloud_llm(LLMClient.get())
        self.store = _maybe_session_store()
        # Load the LLM FIRST, single-threaded, BEFORE any warmup threads.
        # mlx's module-import machinery deadlocks when a model import races
        # the greeting/STT warmup threads (observed: _ModuleLock deadlock →
        # the whole daemon hangs). Preference order: the separate llm-server
        # (remote_ready) → in-process load → scripted replies only.
        self.llm.ready()
        self._warm_greeting()
        self._warm_stt()

    # ------------------------------------------------------------------ #
    # Session management (P0-SESSION-001)
    # ------------------------------------------------------------------ #
    def new_call(self, caller_id=None):
        """Create an isolated call context. Returns the call_id."""
        call_id = uuid.uuid4().hex[:12]
        ctx = CallContext(
            call_id=call_id,
            agent=Agent(llm=self.llm),
            recorder=Recorder(self.outdir),
            caller_id=caller_id,
        )
        ctx.recorder.new_call(call_id=call_id)
        with self._sess_lock:
            self.sessions[call_id] = ctx
        self._persist_session(ctx)
        return call_id

    def _persist_session(self, ctx, ttl_seconds=None):
        """Stage 6: mirror the live context into the session store (Redis or
        memory) as a small JSON doc. Never blocks the call path on failure."""
        try:
            from moss_providers import session_doc
            doc = session_doc(
                ctx.call_id,
                dialogue_step=ctx.agent.step,
                summary=" ".join(ctx.agent.notes)[-500:],
                last_intent=getattr(ctx.agent, "last_intent", "") or "",
                worker_id="",
                customer_id=ctx.caller_id or "",
            )
            self.store.put(ctx.call_id, doc, ttl_seconds=ttl_seconds)
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] session persist skipped: {e}", flush=True)

    def get_call(self, call_id):
        """Return the call context or raise KeyError.

        Legacy behaviour: callers that never create a session explicitly
        (e.g. the first Lua-script interop) still work — ``None`` now creates a
        fresh isolated call instead of matching the most recently created one.
        (SECURITY FIX: matching "the latest session" let any local client POST
        to `/turn` without a call_id and inject turns/transcripts into someone
        else's *live* phone call.)
        """
        if call_id:
            with self._sess_lock:
                ctx = self.sessions.get(call_id)
            if ctx is None:
                raise KeyError(call_id)
            ctx.last_seen = time.time()
            return ctx
        call_id = self.new_call()
        return self.get_call(call_id)

    def end_call(self, call_id):
        """Finalize a call: produce the verdict and drop the context."""
        ctx = self.get_call(call_id)
        ctx.outcome = ctx.agent.outcome
        ctx.finished = True
        self._persist_session(ctx, ttl_seconds=60 * 60 * 24)
        with self._sess_lock:
            self.sessions.pop(call_id, None)
        return {
            "ok": True,
            "call_id": call_id,
            "finished": True,
            "outcome": ctx.outcome,
            "summary_path": ctx.recorder.summary_path(),
        }

    def list_calls(self):
        with self._sess_lock:
            return [
                {
                    "call_id": c.call_id,
                    "created_at": c.created_at,
                    "last_seen": c.last_seen,
                    "finished": c.finished,
                    "outcome": c.agent.outcome,
                    "caller_id": c.caller_id,
                }
                for c in self.sessions.values()
            ]

    def sweep_expired(self):
        now = time.time()
        with self._sess_lock:
            expired = [
                cid
                for cid, c in self.sessions.items()
                if now - c.last_seen > SESSION_TTL_SEC
            ]
            for cid in expired:
                self.sessions.pop(cid, None)
        if expired:
            print(f"[call-agent] swept {len(expired)} stale session(s)", flush=True)

    # ------------------------------------------------------------------ #
    def begin_turn(self, call_id):
        """Mark a call as turn-processing. Returns the ctx, or raises
        CallBusyError when a turn is already in flight for this call.

        AUDIT FIX: a second overlapping /turn or /turn_stream request used to
        interleave with the running one (double agent.reply, corrupted
        result.json). Now it is rejected fast.

        ``cancel_event`` is cleared HERE (atomically with the busy check) so a
        stray early /stream-cancel can no longer abort a reply that has not
        started yet (the old handler-level clear raced with delayed cancels).
        """
        ctx = self.get_call(call_id)
        with ctx.turn_lock:
            if ctx.turn_in_progress:
                raise CallBusyError(call_id)
            ctx.turn_in_progress = True
            ctx.cancel_event.clear()
            ctx.streaming = True
        return ctx

    def end_turn(self, ctx):
        with ctx.turn_lock:
            ctx.turn_in_progress = False
            ctx.streaming = False

    def _warm_stt(self):
        def _warm():
            print("[call-agent] pre-warming STT...", flush=True)
            p = self._silence_wav()
            try:
                if p:
                    self.stt.transcribe_clean(p)
            finally:
                if p:
                    try:
                        os.remove(p)
                    except OSError:
                        pass
            print("[call-agent] STT ready", flush=True)
        threading.Thread(target=_warm, daemon=True).start()

    def _silence_wav(self):
        """Tiny silent clip used only to force Whisper into memory at startup."""
        import struct as _struct
        import tempfile as _tf

        pcm = _struct.pack("<%dh" % 1600, *([0] * 1600))  # 0.1s @16k
        fd, p = _tf.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            import wave as _wave

            with _wave.open(p, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(pcm)
        except Exception:  # noqa: BLE001
            try:
                os.remove(p)
            except OSError:
                pass
            return None
        return p

    def _warm_greeting(self):
        def _warm():
            print("[call-agent] pre-warming greeting...", flush=True)
            self.greeting_wav(DEFAULT_GREETING)
            print("[call-agent] greeting ready", flush=True)
        threading.Thread(target=_warm, daemon=True).start()

    def greeting_wav(self, text):
        text = (text or "").strip()
        if not text or not self.tts.ready():
            return None
        if text == DEFAULT_GREETING:
            # FIX: generate inside the lock so a concurrent warmup + first
            # request never double-generate the greeting.
            with self._greeting_lock:
                if not self._greeting_cache:
                    wav = self.tts.generate(text)
                    if wav:
                        self._greeting_cache = save_wav(self.outdir, wav)
                return self._greeting_cache or None
        wav = self.tts.generate(text)
        return save_wav(self.outdir, wav) if wav else None

    # directories whose WAV files may be referenced by {"audio": ...} JSON
    # bodies. Anything outside these prefixes is rejected — the old code
    # happily copied ~/.ssh/id_rsa into the call archive. Prefixes are
    # realpath-normalised at startup (macOS symlinks /var -> /private/var).
    # tempfile.gettempdir() is included so the whitelist follows whatever
    # TMPDIR the platform actually provides (isolated CI sandboxes ship
    # without /tmp — AUDIT fix), while staying restricted to temp space.
    UPLOAD_ALLOWED_DIRS = tuple(
        os.path.realpath(d) for d in
        ("/tmp", "/var/folders", "/private/tmp", "/private/var/folders",
         tempfile.gettempdir())
    )

    def save_upload(self, raw, ctype):
        """Return (path, is_temp). is_temp=True for files we created here
        (multipart body) so the handler only cleans up its own temp files —
        a JSON `{"audio": "/path"}` reference must never be deleted.

        SECURITY FIX: JSON audio paths are restricted to known temp dirs so a
        client cannot exfiltrate arbitrary files through the turn archive.
        """
        import shutil as _shutil

        if "multipart/form-data" in ctype:
            return parse_multipart_wav(raw, ctype), True
        # JSON body: {"audio": "/path/to.wav"} (shared filesystem) or
        # {"audio_b64": "<wav bytes base64>"} (Docker: no shared filesystem
        # between the gateway and the agent containers).
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None, False
        b64 = payload.get("audio_b64")
        if b64:
            try:
                data = base64.b64decode(b64)
            except Exception:  # noqa: BLE001
                return None, False
            if not data:
                return None, False
            tmpdir = getattr(self, "tmpdir", None) or tempfile.gettempdir()
            fd, staged = tempfile.mkstemp(suffix=".wav", dir=tmpdir)
            os.close(fd)
            with open(staged, "wb") as f:
                f.write(data)
            return staged, True
        # JSON: {"audio": "/path/to.wav"}
        try:
            path = payload.get("audio")
            if not path or not os.path.exists(path):
                return None, False
            real = os.path.realpath(path)
            allowed = any(
                real == d or real.startswith(d + os.sep)
                for d in self.UPLOAD_ALLOWED_DIRS
            )
            if not allowed:
                print(f"[call-agent] rejected audio outside allowed dirs: {real}",
                      flush=True)
                return None, False
            tmpdir = getattr(self, "tmpdir", None)
            if tmpdir:
                real_tmp = os.path.realpath(tmpdir)
                if not (real.startswith(real_tmp + os.sep) or real == real_tmp):
                    # move into our tmpdir so cleanup/tracking is local and the
                    # original is never modified.
                    fd, staged = tempfile.mkstemp(suffix=".wav", dir=tmpdir)
                    os.close(fd)
                    try:
                        _shutil.copyfile(real, staged)
                        return staged, True
                    except OSError:
                        try:
                            os.remove(staged)
                        except OSError:
                            pass
                        return None, False
            return path, False
        except Exception:
            pass
        return None, False

    def process_turn(self, wav_path, call_id=None):
        ctx = self.get_call(call_id)
        self.sweep_expired()
        with ctx.lock:
            agent, rec = ctx.agent, ctx.recorder

            transcript = self.stt.transcribe_clean(wav_path)
            if transcript is None:
                reply = "Повторите, пожалуйста."
            else:
                reply = agent.reply(transcript)
            finished = agent.finished

            # AUDIT FIX: the reply audio used to be embedded as base64 in the
            # JSON response (~1 MB per turn). No consumer reads it — the Lua
            # script plays reply_wav_path. Keeping it only wasted bandwidth.
            reply_wav = self.tts.generate(reply)
            saved = None
            user_turn_no = len(rec.call["turns"]) + 1 if transcript is not None else None
            if reply_wav:
                saved = save_wav(self.outdir, reply_wav,
                                 call_id=ctx.call_id, turn_id=user_turn_no)

            if transcript is not None:
                saved_user = save_user_wav(self.outdir, wav_path,
                                           call_id=ctx.call_id, turn_id=user_turn_no)
                rec.add_turn("user", transcript, audio_path=saved_user)
            rec.add_turn("assistant", reply, audio_path=saved)
            summary = rec.summary_path()
            ctx.last_seen = time.time()

        return {
            "ok": True,
            "call_id": ctx.call_id,
            "transcript": transcript,
            "reply": reply,
            "finished": finished,
            "reply_wav_path": saved,
            "summary_path": summary,
            "outcome": agent.outcome,
        }

    # Sentence boundary used to carve the streaming reply into TTS segments
    # (matches the punctuation class used by _clean_llm).
    _SENT_BOUND = re.compile(r"(?<=[.!?…])(?=\S|\s)")

    def _reply_segments(self, agent, plan, cancel_event=None,
                        max_segments=2, max_chars=380):
        """Streaming reply producer (REALTIME FIX, Stage 5).

        Consumes the LLM's token deltas and yields ONE COMPLETE SENTENCE at a
        time, so the first sentence is synthesised and begins playing while the
        model is still generating the rest of the reply. Output is capped to
        the same rules as ``_clean_llm`` (``max_segments`` sentences, up to
        ``max_chars`` characters). Yields nothing when the model produces no
        usable text — the caller then falls back to the canned phrase.
        ``cancel_event`` aborts between segments (barge-in).
        """
        buffer = ""
        emitted = 0            # number of sentences already yielded
        emitted_chars = 0
        prefix_stripped = False

        for delta in agent.reply_stream(plan):
            if cancel_event is not None and cancel_event.is_set():
                return
            if not delta:
                continue
            buffer = " ".join((buffer + delta).split())
            if not prefix_stripped:
                buffer = re.sub(r"^(Вера|Assistant|Ответ)\s*:\s*", "",
                                buffer, flags=re.IGNORECASE)
                prefix_stripped = True
            # carve every complete sentence that is safe to send to TTS now
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    return
                cut = None
                for sm in self._SENT_BOUND.finditer(buffer):
                    seg = buffer[:sm.end()].strip()
                    if len(seg) >= 2:
                        cut = sm.end()
                        break
                if cut is None:
                    break
                seg = buffer[:cut].strip()
                if emitted >= max_segments \
                        or emitted_chars + len(seg) > max_chars:
                    return
                emitted += 1
                emitted_chars += len(seg)
                yield seg
                buffer = buffer[cut:].strip()
                if emitted >= max_segments:
                    return

        # flush a trailing reply that has no terminal punctuation
        tail = buffer.strip()
        if tail and emitted < max_segments:
            if cancel_event is not None and cancel_event.is_set():
                return
            if len(tail) > max_chars:
                # single over-long sentence: cut it (mirrors _clean_llm) so a
                # giant reply is still spoken, just truncated.
                cut = tail[:max_chars].rfind(" ")
                tail = (tail[:cut].rstrip() if cut > 0 else tail[:max_chars]) + "."
            yield tail

    def process_turn_stream(self, wav_path, call_id=None, cancel_event=None):
        """STT -> agent reply -> TTS, yielding each audio frame as it is made.

        Yields dicts: first frame carries metadata (transcript/reply/finished),
        each audio frame has wav_b64, and the last frame has done=True.
        ``cancel_event`` (threading.Event) lets a barge-in abort TTS generation
        mid-stream (no further frames are produced).

        STT is INCREMENTAL (P0-REALTIME-CORE step 11): the recorded turn is
        transcribed hop-by-hop and each confirmed hop is emitted as an
        ``{"type": "interim", "transcript": ...}`` frame BEFORE the reply
        begins, so a compliant client can show live transcription.
        """
        ctx = self.get_call(call_id)
        self.sweep_expired()

        # LATENCY FIX: the STT pass no longer runs under the per-call lock and
        # each confirmed hop is yielded THE MOMENT it is decoded — the client
        # sees live transcription while recognition is still running, instead
        # of getting every interim frame after STT+LLM finished. Decode is
        # pure (no ctx state touched); the overlapping-turn guard
        # (begin_turn/turn_in_progress) still makes this safe per call.
        transcript = None
        try:
            with open(wav_path, "rb") as wf:
                wav_bytes = wf.read()
            pcm, sample_rate = wav_to_pcm(wav_bytes)
        except Exception:  # noqa: BLE001
            pcm, sample_rate = None, None

        if pcm:
            samples = list(struct.unpack("<%dh" % (len(pcm) // 2), pcm))
            stream_stt = StreamingSTT(self.stt, sample_rate=sample_rate or 16000)
            for i in range(0, len(samples), 160):  # 10ms cadence
                if cancel_event is not None and cancel_event.is_set():
                    break
                hop_text, _interim = stream_stt.feed(samples[i:i + 160])
                if hop_text:
                    yield {"type": "interim", "transcript": hop_text,
                           "final": False, "i": i}
            transcript = stream_stt.finish()

        # Dialogue-state mutations run under the per-call lock. Only the
        # DETERMINISTIC plan (Stage 4 state machine) is computed here; the
        # model is NEVER run under the lock. The reply itself is produced by
        # TOKEN STREAMING below: the first finished sentence goes to TTS while
        # the LLM is still generating the rest (Stage 5).
        with ctx.lock:
            agent, rec = ctx.agent, ctx.recorder

            if transcript is None:
                plan = None
                canned_reply = "Повторите, пожалуйста."
            else:
                plan = agent.plan_reply(transcript)
                agent.last_intent = plan.get("intent") or ""
                canned_reply = None if plan.get("intent") \
                    else (plan.get("fallback") or "")

            finished = agent.finished

            # copy the caller's audio into the archive while the temp upload
            # still exists
            user_turn_no = len(rec.call["turns"]) + 1 if transcript is not None else None
            saved_user = save_user_wav(self.outdir, wav_path,
                                       call_id=ctx.call_id, turn_id=user_turn_no) \
                if transcript is not None else None
            if transcript is not None:
                rec.add_turn("user", transcript, audio_path=saved_user)

        # AUDIT FIX: register this reply's generation server-side so a
        # stream-cancel can abort the real model work (not just our read loop).
        sid = f"{ctx.call_id}-{uuid.uuid4().hex[:8]}"
        ctx.stream_id = sid

        meta_base = {"call_id": ctx.call_id, "transcript": transcript,
                     "finished": finished, "outcome": agent.outcome}

        if canned_reply is not None:
            # No model involved (missing transcript / scripted step): keep the
            # simple single-shot flow.
            yield {"type": "interim", "transcript": transcript, "final": True,
                   "reply": canned_reply, "finished": finished}
            segments = [canned_reply]
        else:
            # Live meta frame: the reply text is not final yet (it keeps
            # growing while tokens stream in); the done frame carries it.
            yield {"type": "interim", "transcript": transcript, "final": True,
                   "finished": finished}
            segments = self._reply_segments(agent, plan, cancel_event)

        response_parts = []
        idx = 0
        got_audio = False
        pcm_parts = []
        sample_rate = None
        sent_done = False

        def meta_now():
            return {**meta_base, "reply": " ".join(response_parts),
                    "finished": agent.finished, "outcome": agent.outcome}

        seg_no = 0
        for segment in segments:
            if cancel_event is not None and cancel_event.is_set():
                self.tts.cancel_stream_by_id(ctx.stream_id)
                break
            if not segment:
                continue
            response_parts.append(segment)
            seg_sid = f"{sid}-{seg_no}"
            seg_no += 1
            ctx.stream_id = seg_sid
            for frame in self.tts.stream(segment, cancel_event=cancel_event,
                                         stream_id=seg_sid):
                if cancel_event is not None and cancel_event.is_set():
                    # barge-in: emit a single done frame with the aborted state
                    # so the client knows the assistant stopped talking.
                    wire = {"done": True, "aborted": True}
                    wire.update(meta_now())
                    yield wire
                    sent_done = True
                    break
                idx = frame.get("i", idx)
                wire = {"i": idx}
                if frame.get("done"):
                    wire["done"] = True
                    wire.update(meta_now())
                    yield wire
                    sent_done = True
                    break
                audio = base64.b64decode(frame.get("wav_b64") or "")
                if not audio:
                    continue
                got_audio = True
                pcm, sr = wav_to_pcm(audio)
                if pcm:
                    sample_rate = sr or sample_rate
                    pcm_parts.append(pcm)
                wire["done"] = False
                # LATENCY FIX: tell downstream (tg_server -> WebApp) the true
                # sample rate of this frame so the client never resamples blindly.
                if sr:
                    wire["sample_rate"] = sr
                # metadata on the first audible frame so the client can show
                # the transcript immediately while audio keeps streaming
                if idx == 0:
                    wire.update(meta_now())
                wire["wav_b64"] = frame["wav_b64"]
                yield wire
                idx += 1
            if sent_done and cancel_event is not None and cancel_event.is_set():
                break

        reply = " ".join(response_parts).strip()
        meta = meta_now()

        # The model produced nothing usable: speak the canned fallback so the
        # caller is never left without an answer (Stage 9 requirement).
        if not got_audio and not (cancel_event is not None and cancel_event.is_set()):
            fb = (plan or {}).get("fallback") if plan else None
            if fb and reply and reply != fb:
                reply = fb
                meta = {**meta_base, "reply": reply}
                fb_sid = f"{sid}-fallback"
                ctx.stream_id = fb_sid
                for frame in self.tts.stream(fb, cancel_event=cancel_event,
                                             stream_id=fb_sid):
                    if cancel_event is not None and cancel_event.is_set():
                        break
                    if frame.get("done"):
                        wire = {"done": True}
                        wire.update(meta)
                        yield wire
                        sent_done = True
                        break
                    audio = base64.b64decode(frame.get("wav_b64") or "")
                    if not audio:
                        continue
                    got_audio = True
                    pcm, sr = wav_to_pcm(audio)
                    if pcm:
                        sample_rate = sr or sample_rate
                        pcm_parts.append(pcm)

        if not sent_done and not (cancel_event is not None and cancel_event.is_set()):
            yield {"done": True, **meta}

        ctx.stream_id = ""

        if cancel_event is not None and cancel_event.is_set():
            return

        saved = None
        if pcm_parts:
            saved = save_wav(self.outdir, pcm_to_wav(b"".join(pcm_parts), sample_rate or 24000),
                             call_id=ctx.call_id, turn_id=user_turn_no)
        with ctx.lock:
            if plan is not None and plan.get("intent"):
                agent.commit_reply(reply)
            rec.add_turn("assistant", reply, audio_path=saved)
            ctx.last_seen = time.time()
        self._persist_session(ctx)


def save_wav(outdir, wav_bytes, call_id=None, turn_id=None):
    os.makedirs(outdir, exist_ok=True)
    if call_id:
        outdir = os.path.join(outdir, call_id)
        os.makedirs(outdir, exist_ok=True)
    stub = f"reply-{turn_id:04d}.wav" if turn_id is not None \
        else f"reply-{datetime.datetime.now().strftime('%H%M%S')}.wav"
    p = os.path.join(outdir, stub)
    with open(p, "wb") as f:
        f.write(wav_bytes)
    return p


def wav_to_pcm(wav_bytes):
    """Extract raw PCM + sample rate from a WAV file."""
    import io as _io
    import wave as _wave
    try:
        with _wave.open(_io.BytesIO(wav_bytes), "rb") as w:
            if w.getsampwidth() != 2 or w.getnchannels() != 1:
                return None, None
            return w.readframes(w.getnframes()), w.getframerate()
    except Exception:  # noqa: BLE001
        return None, None


def pcm_to_wav(pcm, sample_rate):
    import io as _io
    import wave as _wave
    buf = _io.BytesIO()
    with _wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9400)
    ap.add_argument("--host", default=os.environ.get("MOSS_BIND_HOST", "127.0.0.1"),
                    help="bind address; loopback by default, other values are "
                         "for isolated networks (Docker)")
    ap.add_argument("--tts-port", type=int, default=None, help="fixed TTS daemon port (else reads --tts-port-file)")
    ap.add_argument("--tts-port-file", default=None, help="path to TTS port file")
    ap.add_argument("--tts-host", default=None,
                    help="TTS daemon host (Docker: the 'voice' service name); "
                         "default resolves env MOSS_TTS_HOST then 127.0.0.1")
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "calls"))
    ap.add_argument("--tmpdir", default="/tmp/mossvoice_turns",
                    help="staging dir for JSON-referenced audio uploads")
    ap.add_argument("--ref", action="append", default=[], help="reference WAV path(s)")
    ap.add_argument("--reference-text", default="")
    ap.add_argument("--inference-steps", type=int, default=12, help="TTS diffusion steps (lower=faster, default 12)")
    ap.add_argument("--no-style", action="store_true", help="disable style transfer for faster TTS")
    args = ap.parse_args()
    args.refs = args.ref

    srv = Serve(args)
    httpd = QuietHTTPServer((args.host, args.port), Handler)
    httpd.serve = srv
    print(f"[call-agent] listening on {args.host}:{args.port}", flush=True)
    print(f"[call-agent] tts_ready={srv.tts.ready()}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()