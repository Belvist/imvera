"""VeraSpeechFrontend: LLM text -> Silero SSML (pauses, rate, normalization).

Human-likeness levers that do NOT require a new TTS engine:
  * natural inter-sentence pauses (<break>) — dead-flat concatenation is
    what makes synthetic speech feel robotic;
  * configurable speech rate for elderly listeners (<prosody rate>);
  * numbers/dates/time spelled out the way a human would say them.

Dependency-free (regex only), side-effect free: returns a string.
"""
import os
import re

_SENT_BREAK_MS = int(os.environ.get("MOSS_TTS_BREAK_MS", "280"))
# elderly-friendly rate: "" (default) | "slow" | "x-slow" (Silero discrete)
_PROSODY_RATE = os.environ.get("MOSS_TTS_RATE", "")

# --- number/date/time normalization ------------------------------------- #
_ONES = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь",
         "восемь", "девять", "десять", "одиннадцать", "двенадцать",
         "тринадцать", "четырнадцать", "пятнадцать", "шестнадцать",
         "семнадцать", "восемнадцать", "девятнадцать"]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят",
         "семьдесят", "восемьдесят", "девяносто"]
_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот",
             "шестьсот", "семьсот", "восемьсот", "девятьсот"]
_MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня",
               "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def num_to_words(n: int) -> str:
    """Cardinal, nominative. Short numbers only (replies never go big)."""
    if n < 0:
        return "минус " + num_to_words(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        t, o = divmod(n, 10)
        return _TENS[t] + ((" " + _ONES[o]) if o else "")
    if n < 1000:
        h, rest = divmod(n, 100)
        return _HUNDREDS[h] + ((" " + num_to_words(rest)) if rest else "")
    return str(n)


_ORDINALS = ["", "первое", "второе", "третье", "четвёртое", "пятое",
             "шестое", "седьмое", "восьмое", "девятое", "десятое",
             "одиннадцатое", "двенадцатое", "тринадцатое", "четырнадцатое",
             "пятнадцатое", "шестнадцатое", "семнадцатое", "восемнадцатое",
             "девятнадцатое", "двадцатое", "двадцать первое",
             "двадцать второе", "двадцать третье", "двадцать четвёртое",
             "двадцать пятое", "двадцать шестое", "двадцать седьмое",
             "двадцать восьмое", "двадцать девятое", "тридцатое",
             "тридцать первое"]


def _dd_mm(m):
    d, mo = int(m.group(1)), int(m.group(2))
    if 1 <= d <= 31 and 1 <= mo <= 12:
        return f"{_ORDINALS[d]} {_MONTHS_GEN[mo - 1]}"
    return m.group(0)


def _hh_mm(m):
    h, mi = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return m.group(0)
    if mi == 0:
        return f"{num_to_words(h)} часов"
    return f"{num_to_words(h)} {num_to_words(mi)}"


def normalize_text(text: str) -> str:
    """Dates (21.08), times (18:30), plain integers -> speakable words."""
    text = re.sub(r"\b(\d{1,2})\.(\d{1,2})\.(?:\d{2,4})\b", _dd_mm, text)
    text = re.sub(r"\b(\d{1,2})\.(\d{1,2})\.?(?!\d)", _dd_mm, text)
    text = re.sub(r"\b(\d{1,2}):(\d{2})\b", _hh_mm, text)
    text = re.sub(r"\b\d+\b", lambda m: num_to_words(int(m.group(0)))
                  if int(m.group(0)) <= 9999 else m.group(0), text)
    return text


# --- SSML shaping -------------------------------------------------------- #
_SENT_END = re.compile(r"([.!?…]+)\s+")


def _split_sentences(text):
    parts = _SENT_END.split(text)
    out = []
    if not parts:
        return out
    cur = parts[0]
    for i in range(1, len(parts), 2):
        cur = (cur + parts[i]).strip()
        if cur:
            out.append(cur)
        if i + 1 < len(parts):
            cur = parts[i + 1]
    if cur.strip():
        out.append(cur.strip())
    return [s for s in out if s]


def to_ssml(text: str):
    """Plain reply text -> Silero SSML string. Returns None when there is
    nothing to add (caller uses plain text with put_accent/put_yo)."""
    text = normalize_text(text).strip()
    if not text:
        return None
    sentences = _split_sentences(text)
    if not sentences:
        return None
    inner = f'<break time="{_SENT_BREAK_MS}ms"/>'.join(sentences)
    if _PROSODY_RATE:
        inner = f'<prosody rate="{_PROSODY_RATE}">{inner}</prosody>'
    return f"<speak>{inner}</speak>"


def build_tts_trace(original: str) -> dict:
    """Full Silero input trace: pronunciation → normalization → SSML."""
    from pronunciation import apply_pronunciation_with_trace

    pron = apply_pronunciation_with_trace(original)
    normalized = pron.normalized
    ssml = to_ssml(normalized)
    ssml_input = normalize_text(normalized).strip() if ssml else normalized
    return {
        "TTS_INPUT_ORIGINAL": original,
        "TTS_INPUT_NORMALIZED": normalized,
        "TTS_SSML_INPUT": ssml_input,
        "TTS_SSML": ssml,
        "PRONUNCIATION_OVERRIDES": [o.to_dict() for o in pron.overrides],
        "MOSS_TTS_SSML": os.environ.get("MOSS_TTS_SSML", "1"),
    }


def format_tts_trace_lines(trace: dict) -> str:
    lines = [
        f'TTS_INPUT_ORIGINAL: "{trace.get("TTS_INPUT_ORIGINAL", "")}"',
        f'TTS_INPUT_NORMALIZED: "{trace.get("TTS_INPUT_NORMALIZED", "")}"',
        f"PRONUNCIATION_OVERRIDES: {trace.get('PRONUNCIATION_OVERRIDES', [])}",
    ]
    if trace.get("TTS_SSML"):
        lines.append(f'TTS_SSML: "{trace["TTS_SSML"]}"')
    return "\n".join(lines)
