"""Offline audio-pipeline diagnostic for the "не слышит" complaint.

Runs the REAL production gates over recorded live user turns and reports
which one is rejecting them:
  1. audio energy (adapters.stt.audio_energy  < 0.004 => silence gate)
  2. Silero VAD speech seconds (tts_common.vad_speech_seconds)
  3. whisper confidence (transcribe_with_confidence)

Usage: python voice-lab/audio_diag.py <dir> [<dir2> ...]
  Each dir should contain user-NNNN.wav (the caller's turns archived by
  the telephony container under /tmp/mossvoice/<call_id>/).
"""
import glob
import os
import sys


def main():
    raw = sys.argv[1:]
    if raw and all(os.path.isdir(a) for a in raw):
        dirs = sorted(raw)
    elif raw and all(glob.has_magic(a) or os.path.isfile(a) for a in raw):
        dirs = sorted({os.path.dirname(p) for p in glob.glob(
            raw[0]) if os.path.dirname(p)})
    else:
        dirs = sorted({os.path.dirname(p)
                       for p in glob.glob("/tmp/mossvoice/*/user-*.wav")})
    if not dirs:
        print("no dirs given and none found under /tmp/mossvoice/*/user-*.wav")
        return 1

    from adapters.stt import audio_energy
    import sys as _s

    # … handle VAD / STT lazily — they pull torch/whisper and are heavy.
    try_vad = try_stt = not os.environ.get("MOSS_DIAG_QUICK")
    vad = stt = None
    if try_vad:
        try:
            import tts_common
            vad = tts_common.vad_speech_seconds
        except Exception as e:
            print(f"(VAD unavailable: {e})")
            vad = None
        try:
            from adapters.stt import STTEngine
            stt = STTEngine()
        except Exception as e:
            print(f"(STT unavailable: {e})")
            stt = None

    print(f"{'dir':<14} {'file':<12} {'energy':>7}  "
          f"{'vad_s':>6} {'conf':>5}  cut?")
    dropped = total = 0
    for d in dirs:
        files = sorted(glob.glob(os.path.join(d, "user-*.wav")))
        for f in files:
            total += 1
            e = audio_energy(f)
            vs = None
            if vad:
                try:
                    vs = vad(f)
                except Exception:
                    vs = None
            conf = None
            if stt is not None:
                try:
                    r = stt.transcribe_with_confidence(f)
                    conf = round(r.confidence, 3) if r.confidence is not None else None
                    txt = r.text or ""
                    # gate mirror
                    cut = (
                        e < 0.004
                        or (txt and conf is not None and conf < 0.55)
                    )
                except Exception:
                    txt, cut = "", False
            else:
                txt, cut = "", False
            flag = "CUT" if cut else ""
            if cut:
                print(f"{os.path.basename(d):<14} {os.path.basename(f):<12} "
                      f"{e:7.4f} {str(vs):>6} {str(conf):>28}  {flag}")
            else:
                print(f"{os.path.basename(d):<14} {os.path.basename(f):<12} "
                      f"{e:7.4f} {str(vs):>6} {str(conf):>28}  {flag}  {txt[:50]!r}")
            if cut:
                # dropped
                pass
    print(f"\nscanned {total} turn(s)")

    return 0


if __name__ == "__main__":
    sys.exit(main())