"""Tiny-model assist — disambiguation ONLY, never state owner (ADR-009).

Two backends (IMVERA_TINYLLM_MODEL):
  route_clf (default when flag set) — sklearn linear classifier
      (~230KB, <1ms CPU) trained on our own ambiguity corpus via
      tools/voice_lab/train_route_clf.py. Recommended: measured, tiny.
  <mlx-id> — generative MLX fallback (e.g. SmolLM2-360M). MEASURED BAD on
      Russian one-word classification (echo/garbage) — kept for experiments.

Consulted exclusively when deterministic NLU cannot decide: short /
unclear / borderline turns. Temperature 0, hard timeout 3 s, fail-open.
NEVER emits issue_mentions / goal_facts / verdicts / speech. Deterministic
RED / decline / control / goodbye checks always run FIRST. Validator clamps
the answer to ROUTES, else discard.

Disabled by default: IMVERA_TINYLLM_MODEL="" (off).
"""

from __future__ import annotations

import os
import re
import time

ROUTES: tuple[str, ...] = (
    "answer",
    "reluctance",
    "repair",
    "question_back",
    "hostile",
    "garbage",
    "unclear",
)

_TIMEOUT_S = float(os.getenv("IMVERA_TINYLLM_TIMEOUT_S", "3.0") or 3.0)
_MAX_TOKENS = 16

_model_cache: dict[str, object] = {}


def _load_clf() -> object:
    if "route_clf" not in _model_cache:
        import pickle
        from pathlib import Path

        path = (
            Path(__file__).resolve().parent.parent.parent / "models" / "route_clf.pkl"
        )
        with open(path, "rb") as f:
            _model_cache["route_clf"] = pickle.load(f)
    return _model_cache["route_clf"]


def model_id() -> str:
    return (os.getenv("IMVERA_TINYLLM_MODEL", "") or "").strip()


def enabled() -> bool:
    return bool(model_id())


def _load(model: str) -> tuple[object, object]:
    if model not in _model_cache:
        from mlx_lm import load

        _model_cache[model] = load(model)
    cached = _model_cache[model]
    assert isinstance(cached, tuple)
    return cached


_PROMPT = (
    "Классифицируй реплику пожилого человека по телефону. "
    "Ответь ровно одним словом из списка: {routes}. "
    "answer=ответ на вопрос «{question}», reluctance=не хочет говорить "
    "(устал, хватит, надоело), repair=не расслышал (что, алло, повтори), "
    "question_back=вопрос в ответ (а вы кто, зачем звоните), "
    "hostile=грубость без содержания, garbage=мусор/обрывок, "
    "unclear=непонятно. Только одно слово, без объяснений.\nРеплика: {text}"
)


def classify(
    text: str,
    *,
    pending_question: str | None,
    timeout_s: float | None = None,
) -> str | None:
    """Return a route from ROUTES, or None on any failure/timeout."""
    mid = model_id()
    if not mid:
        return None
    user_text = (text or "").strip()
    if not user_text:
        return None
    if mid == "route_clf":
        # sklearn backend: microseconds, no timeout needed.
        try:
            clf = _load_clf()
            pred = clf.predict([user_text.lower()])[0]
            return pred if pred in ROUTES else None
        except Exception:  # noqa: BLE001 — fail open to deterministic
            return None
    deadline = time.monotonic() + (timeout_s or _TIMEOUT_S)
    try:
        model, tokenizer = _load(mid)
        from mlx_lm import stream_generate

        prompt = _PROMPT.format(
            routes=",".join(ROUTES),
            question=(pending_question or "—")[:120],
            text=user_text[:200],
        )
        messages = [{"role": "user", "content": prompt}]
        if hasattr(tokenizer, "apply_chat_template"):
            prompt = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        out: list[str] = []
        # NOTE: installed mlx_lm's stream_generate takes no temperature kwarg
        # (greedy default) — do not pass temp/temperature (TypeError).
        for chunk in stream_generate(
            model,
            tokenizer,
            prompt=prompt,
            max_tokens=_MAX_TOKENS,
        ):
            out.append(chunk.text)
            if time.monotonic() > deadline:
                return None
        word = re.sub(r"[^a-z_]", "", "".join(out).lower().strip())
        return word if word in ROUTES else None
    except Exception:  # noqa: BLE001 — fail open to deterministic
        return None


def bench_payload(text: str, *, pending_question: str | None) -> dict:
    """Serializable view for the ambiguity bench (no model call)."""
    return {"text": text, "pending_question": pending_question}
