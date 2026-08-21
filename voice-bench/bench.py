#!/usr/bin/env python3
"""Vera TTS benchmark: RTF, RAM, round-trip WER (TTS -> STT), audio stats.

Backends: silero (production), piper (installed separately).
Usage: python3 bench.py silero [N_PHRASES]
Output: out/<backend>/*.wav + results_<backend>.json + summary printed.

Round-trip WER is the objective pronunciation check: synthesize a phrase,
transcribe it back with STT (faster-whisper), compare with the source text.
A mangled word (swallowed ending, wrong stress) shows up as a WER hit.
"""
import json
import os
import resource
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "runtime", "scripts"))
sys.path.insert(0, os.path.join(HERE, "..", "runtime", "scripts", "moss_runtime"))

CORPUS = os.path.join(HERE, "vera_voice_500.txt")


def load_corpus(limit=None):
    phrases = []
    cat = ""
    for line in open(CORPUS, encoding="utf-8"):
        line = line.strip()
        if line.startswith("# === "):
            cat = line[6:-6].strip()
        elif line and not line.startswith("#"):
            phrases.append({"cat": cat, "text": line})
    return phrases[:limit] if limit else phrases


def save_wav(path, audio, sr):
    import wave
    import numpy as np
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes())


class SileroBackend:
    name = "silero"

    def __init__(self):
        os.environ.setdefault("MOSS_SILERO_SPEAKER", "kseniya")
        from silero_tts_backend import SileroTtsBackend
        self.b = SileroTtsBackend()

    def synth(self, text):
        t0 = time.time()
        audio, sr, _ = self.b.generate(text)
        return audio, sr, time.time() - t0

    def first_audio_ms(self, text):
        t0 = time.time()
        for chunk in self.b.stream_generate(text):
            _ = chunk
            return (time.time() - t0) * 1000
        return None


class PiperBackend:
    name = "piper"

    def __init__(self):
        sys.path.insert(0, os.path.expanduser("~/tts-arena/venv/lib/python3.12/site-packages"))
        from piper import PiperVoice
        base = os.path.expanduser("~/tts-arena")
        self.v = PiperVoice.load(os.path.join(base, "ru_RU-irina-medium.onnx"))
        self.sr = self.v.config.sample_rate

    def synth(self, text):
        import tempfile
        import wave as _w
        import numpy as np
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        t0 = time.time()
        with _w.open(tmp.name, "wb") as wf:
            self.v.synthesize_wav(text, wf)
        gen = time.time() - t0
        with _w.open(tmp.name) as w:
            sr = w.getframerate()
            raw = w.readframes(w.getnframes())
        os.unlink(tmp.name)
        return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32767, sr, gen

    def first_audio_ms(self, text):
        return None  # piper python API: no streaming here


def roundtrip_wer(stt_model, wav_path, ref_text):
    """TTS -> STT -> compare. Returns (wer, hyp)."""
    import re
    def norm(s):
        s = s.lower().replace("ё", "е")
        s = re.sub(r"[^а-я ]", " ", s)
        return [w for w in s.split() if w]
    ref = norm(ref_text)
    segs, _ = stt_model.transcribe(wav_path, language="ru", vad_filter=True,
                                   beam_size=1, temperature=0.0,
                                   condition_on_previous_text=False)
    hyp = norm(" ".join(s.text for s in segs))
    if not ref:
        return 0.0, " ".join(hyp)
    # Levenshtein on word level
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        nd = [i]
        for j, h in enumerate(hyp, 1):
            nd.append(min(d[j] + 1, nd[-1] + 1, d[j - 1] + (r != h)))
        d = nd
    wer = d[-1] / max(1, len(ref))
    return wer, " ".join(hyp)


def main():
    backend_name = sys.argv[1] if len(sys.argv) > 1 else "silero"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    phrases = load_corpus(limit)

    backend = {"silero": SileroBackend, "piper": PiperBackend}[backend_name]()
    out_dir = os.path.join(HERE, "out", backend.name)
    os.makedirs(out_dir, exist_ok=True)

    # STT for round-trip (in the mossvoice venv this is faster-whisper)
    from faster_whisper import WhisperModel
    stt = WhisperModel("tiny", device="cpu", compute_type="float32", cpu_threads=3)

    results = []
    ram0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    for i, p in enumerate(phrases):
        try:
            audio, sr, gen = backend.synth(p["text"])
            dur = len(audio) / sr
            wav_path = os.path.join(out_dir, f"{i:03d}_{p['cat']}.wav")
            save_wav(wav_path, audio, sr)
            wer, hyp = roundtrip_wer(stt, wav_path, p["text"])
            results.append({"i": i, "cat": p["cat"], "text": p["text"],
                            "gen_s": round(gen, 3), "audio_s": round(dur, 2),
                            "rtf": round(gen / max(dur, 0.1), 3),
                            "wer": round(wer, 3), "hyp": hyp})
            if (i + 1) % 50 == 0:
                print(f"  ... {i+1}/{len(phrases)}", flush=True)
        except Exception as e:  # noqa: BLE001
            results.append({"i": i, "cat": p["cat"], "text": p["text"],
                            "error": str(e)[:120]})
            print(f"  ERR {i}: {e}", flush=True)

    ram = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    ok = [r for r in results if "error" not in r]
    fam = [r for r in ok if r["audio_s"] > 0.2]
    summary = {
        "backend": backend.name,
        "phrases": len(results),
        "errors": len(results) - len(ok),
        "rtf_avg": round(sum(r["rtf"] for r in fam) / max(1, len(fam)), 3),
        "rtf_p95": round(sorted(r["rtf"] for r in fam)[int(len(fam) * 0.95) - 1], 3),
        "gen_s_total": round(sum(r["gen_s"] for r in ok), 1),
        "wer_avg": round(sum(r["wer"] for r in ok) / max(1, len(ok)), 4),
        "wer_p95": round(sorted(r["wer"] for r in ok)[int(len(ok) * 0.95) - 1], 3),
        "ram_mb": round(ram / 1024, 1),
    }
    # worst pronunciation hits for human review
    worst = sorted(ok, key=lambda r: -r["wer"])[:15]
    with open(os.path.join(HERE, f"results_{backend.name}.json"), "w",
              encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results, "worst": worst},
                  f, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("WORST WER (проверить ушами):")
    for r in worst[:10]:
        print(f"  [{r['cat']}] wer={r['wer']:.2f} | {r['text'][:60]} -> {r['hyp'][:50]}")


if __name__ == "__main__":
    main()
