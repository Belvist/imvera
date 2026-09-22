"""Cut-0 conversation-model benchmark: TTFT / tok-s / first-phrase / RAM.

Realistic Vera turn: system prompt + 6-turn history + verified state +
current user utterance. Short output (40 tokens). One LLM call per turn.
Compares Qwen3 4B (live) vs 1.7B vs 0.6B MLX quants on this Mac.
"""

import re
import time

SYSTEM = (
    "Ты Вера, заботливая собеседница. Ты разговариваешь с пожилым человеком по телефону. "
    "Отвечай по-русски, тепло и коротко: 1-2 фразы. Не задавай больше одного "
    "вопроса. Не обещай действий. Не повторяй уже заданные вопросы."
)
HISTORY = (
    "Вера: Здравствуйте. Это сервис Амвера. Даниил, как вы себя чувствуете?\n"
    "Человек: Нормально, только спал плохо, до двух детектив читал.\n"
    "Вера: Зачитались допоздна. Детектив хоть интересный оказался?\n"
    "Человек: Да, новый роман, не мог оторваться.\n"
    "Вера: Понятно. Сегодня тогда день спокойно проходит?\n"
    "Человек: Да, дома буду, дочь вечером обещала заехать.\n"
)
STATE = (
    "Известно: самочувствие хорошее, спал плохо. "
    "Открыто: лекарства, визит дочери. Не спрашивать про сон."
)
USER = "Человек: Ну да, одна не буду вечером."
SENT_END = re.compile(r"[.!?…]\s")


def build_prompt() -> str:
    return f"{SYSTEM}\n\nРазговор:\n{HISTORY}{USER}\n\n{STATE}\n\nВера:"


def bench(model_id: str) -> dict:
    from mlx_lm import load, stream_generate

    model, tokenizer = load(model_id)
    messages = [
        {"role": "system", "content": SYSTEM},
        {
            "role": "assistant",
            "content": "Здравствуйте. Это сервис Амвера. Как вы себя чувствуете?",
        },
        {"role": "user", "content": "Нормально, только спал плохо, до двух детектив читал."},
        {"role": "assistant", "content": "Зачитались допоздна. Детектив хоть интересный оказался?"},
        {"role": "user", "content": "Да, новый роман, не мог оторваться."},
        {"role": "assistant", "content": "Понятно. Сегодня тогда день спокойно проходит?"},
        {"role": "user", "content": "Да, дома буду, дочь вечером обещала заехать. " + STATE},
    ]
    prompt = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, enable_thinking=False
    )
    # warmup (compile + cache), discard
    for _ in stream_generate(model, tokenizer, prompt=prompt, max_tokens=8):
        pass
    # measured
    t0 = time.monotonic()
    first_tok_ms = 0.0
    first_phrase_ms = 0.0
    text = ""
    n_tok = 0
    for chunk in stream_generate(model, tokenizer, prompt=prompt, max_tokens=40):
        now = (time.monotonic() - t0) * 1000.0
        piece = chunk.text if hasattr(chunk, "text") else str(chunk)
        if piece and first_tok_ms == 0.0:
            first_tok_ms = now
        text += piece
        n_tok += 1
        if first_phrase_ms == 0.0 and SENT_END.search(text):
            first_phrase_ms = now
    total_ms = (time.monotonic() - t0) * 1000.0
    return {
        "model": model_id,
        "prompt_chars": len(prompt),
        "ttft_ms": round(first_tok_ms, 1),
        "first_phrase_ms": round(first_phrase_ms or total_ms, 1),
        "total_ms": round(total_ms, 1),
        "tok_s": round(n_tok / max(total_ms / 1000.0, 1e-6), 1),
        "text": text.strip()[:200],
    }


if __name__ == "__main__":
    import sys

    for mid in sys.argv[1:]:
        r = bench(mid)
        print(
            f"{r['model']}: TTFT={r['ttft_ms']} first_phrase={r['first_phrase_ms']} "
            f"total={r['total_ms']} tok/s={r['tok_s']}"
        )
        print(f"  out: {r['text']}")
