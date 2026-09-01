"""Streaming events: incremental STT + streaming reply segmentation.

Holds the incremental StreamingSTT pipeline that feeds the dialogue engine
live transcripts (P0-REALTIME-CORE step 11), the sentence-boundary splitter
used to carve an LLM token stream into TTS-ready segments (Stage 5), and the
frame SHAPES the /turn_stream endpoint emits.
"""

import os
import re
import struct
import tempfile

from core.dialogue import clean_transcript
from adapters.audio import pcm_to_wav


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
        self.confidence = None                 # best available (tail/full decode)

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

    def _decode_with_confidence(self, samples):
        """Decode one window -> (clean_text_or_None, confidence_or_None).

        Uses ``transcribe_with_confidence`` when the engine offers it (U9),
        else falls back to the plain ``transcribe`` path (confidence None).
        """
        if not samples:
            return None, None
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            with open(path, "wb") as f:
                f.write(_pcm_to_wav_bytes(samples, self._rate))
            tci = getattr(self._engine, "transcribe_with_confidence", None)
            if tci is not None:
                try:
                    res = tci(path)
                    return res.text, res.confidence
                except Exception:  # noqa: BLE001
                    pass
            text = self._engine.transcribe(path) or ""
            return clean_transcript(text.strip()) or None, None
        except Exception as e:  # noqa: BLE001
            print(f"[call-agent] streaming STT decode error: {e}", flush=True)
            return None, None
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
            text, conf = self._decode_with_confidence(self._pending)
            if text:
                self.confidence = conf
                primary = clean_transcript(
                    (primary + " " if primary else "") + text)
        self._pending = []
        self._final = primary
        if self._final:
            return self._final
        # nothing usable from hops: decode the whole turn once as a safety net
        if self._all:
            text, conf = self._decode_with_confidence(self._all)
            self.confidence = conf
            self._final = text or None
        return self._final


# Sentence boundary used to carve the streaming reply into TTS segments
# (matches the punctuation class used by _clean_llm).
_SENT_BOUND = re.compile(r"(?<=[.!?…])(?=\S|\s)")


def reply_segments(agent, plan, cancel_event=None,
                    max_segments=2, max_chars=380):
    """Streaming reply producer (REALTIME FIX, Stage 5).

    Consumes the LLM's token deltas and yields ONE COMPLETE SENTENCE at a
    time, so the first sentence is synthesised and begins playing while the
    model is still generating the rest of the reply. Output is capped to
    the same rules as ``_clean_llm`` (``max_segments`` sentences, up to
    ``max_chars`` characters). If the LLM produces no usable text at all
    (empty stream / exception), falls back to the canned phrase from the
    plan so the caller never produces silence (D6).
    ``cancel_event`` aborts between segments (barge-in).

    DUPLICATE-SEGMENT GUARD (2026-08-29): Qwen sometimes repeats the SAME
    sentence («Записать это для близких? Записать это для близких?» —
    live call d0220bac0967). A near-identical repeat is dropped so the
    caller never hears the same sentence twice in one reply.
    """
    buffer = ""
    emitted = 0            # number of sentences already yielded
    emitted_chars = 0
    prefix_stripped = False
    _prev = ""

    def _is_dup(seg):
        nonlocal _prev
        if not _prev:
            _prev = seg
            return False
        norm = lambda s: re.sub(r"[^\w]", "", s.lower())
        dup = norm(seg) and norm(seg) == norm(_prev)
        _prev = seg
        return dup

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
            for sm in _SENT_BOUND.finditer(buffer):
                seg = buffer[:sm.end()].strip()
                if len(seg) >= 2:
                    cut = sm.end()
                    break
            if cut is None:
                break
            seg = buffer[:cut].strip()
            if _is_dup(seg):
                # drop the repeated sentence, keep streaming the rest
                buffer = buffer[cut:].strip()
                continue
            if emitted >= max_segments \
                    or emitted_chars + len(seg) > max_chars:
                return
            emitted += 1
            emitted_chars += len(seg)
            yield seg
            buffer = buffer[cut:].strip()
            if emitted >= max_segments:
                return
        # EARLY-FIRST-SOUND (2026-08-30): the cloud LLM (DeepSeek/OpenRouter)
        # takes ~1-1.2s for the first token, and waiting for a full sentence
        # pushes first_audio past 3s (live call feedback). As soon as a
        # usable fragment has streamed with no sentence break yet, ship it
        # as the first segment — TTS starts speaking it while the model
        # finishes the sentence. The trailing tail flushes the rest.
        # Cut conservatively: only at a comma or a word boundary AFTER at
        # least 6 words, so we never splice mid-word or on a dangling
        # preposition ("Ой, как неприятно, что | голова").
        if emitted == 0:
            words = buffer.split()
            if len(words) >= 8:
                cut = -1
                for marker in (". ", "! ", "? ", ", "):
                    i = buffer.find(marker)
                    if 0 < i < len(buffer) - len(marker):
                        head = buffer[:i].strip()
                        hw = head.split()
                        if len(hw) >= 6 and cut < i:
                            cut = i + len(marker) - 1
                if cut > 0:
                    seg = buffer[:cut].strip()
                    if not _is_dup(seg):
                        emitted += 1
                        emitted_chars += len(seg)
                        yield seg
                        buffer = buffer[cut:].strip()
                        break

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