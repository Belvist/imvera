import sys, os, time, wave
sys.path.insert(0, "/app/runtime/scripts")
sys.path.insert(0, "/app/runtime/scripts/moss_runtime")
os.environ["MOSS_SILERO_SPEAKER"] = "kseniya"
from faster_whisper import WhisperModel
import numpy as np
from scipy.signal import resample_poly
from silero_tts_backend import SileroTtsBackend

b = SileroTtsBackend()
tests = [
    "Таблетки от давления приняла утром в восемь часов.",
    "Мне сейчас плохо, голова кружится.",
    "Позвоните дочери Марии, если мне станет хуже.",
]
models = {}
for name in ("tiny", "base"):
    m = WhisperModel(name, device="cpu", compute_type="float32", cpu_threads=10)
    m.transcribe("/tmp/mossvoice/test8k.wav", language="ru")
    models[name] = m
for t in tests:
    a, sr, _ = b.generate(t)
    a16 = resample_poly(a, 16000, sr)
    with wave.open("/tmp/acc.wav", "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((a16 * 32767).astype(np.int16).tobytes())
    for name in ("tiny", "base"):
        m = models[name]
        t0 = time.time()
        segs, _ = m.transcribe("/tmp/acc.wav", language="ru", vad_filter=True,
                               beam_size=1, temperature=0.0,
                               condition_on_previous_text=False)
        txt = " ".join(s.text for s in segs).strip()
        print(f"{name:5s} [{time.time()-t0:.2f}s] {txt[:70]}", flush=True)
    print()
