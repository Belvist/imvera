"""LLM MLX worker — interpret + render on port 9103."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.inference.common import (
    InferenceExecutor,
    WorkerState,
    check_deadline,
    mount_health,
    new_request_id,
)
from services.llm.prompts import INTERPRETER_SYSTEM, RENDERER_SYSTEM

SEMANTIC_SCHEMA_HINT = """Верни ТОЛЬКО JSON SemanticPayload (без call_id и прочих полей контекста):
{
  "dialogue_act": "answer|question|correction|repeat|backchannel|unclear",
  "control": "none|stop_call|revoke_consent|defer|wrong_person",
  "consent_answer": "yes|no|unclear|not_applicable",
  "facts": [{
    "field":"mood","value":"...","subject":"speaker",
    "temporal_scope":"today","negated":false,
    "evidence":{"start":0,"end":6,"quote":"хорошо"}
  }],
  "risk_candidates": [],
  "answers_pending_question": true,
  "needs_clarification": false,
  "user_question": null
}"""

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "voice-m5.yaml"
_model = None
_tokenizer = None
_cancelled: set[str] = set()


def _load_config() -> dict[str, Any]:
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])


def _generate_sync(messages: list[dict[str, str]], max_tokens: int) -> str:
    from mlx_lm import stream_generate

    cfg = _load_config()
    prompt = _tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=cfg["models"]["llm"].get("enable_thinking", False),
    )
    parts: list[str] = []
    for item in stream_generate(_model, _tokenizer, prompt=prompt, max_tokens=max_tokens):
        parts.append(item.text)
    return "".join(parts)


class InterpretRequest(BaseModel):
    request_id: str = Field(default_factory=new_request_id)
    context: dict[str, Any]
    deadline: float | None = None


class RenderRequest(BaseModel):
    request_id: str = Field(default_factory=new_request_id)
    action: dict[str, Any]
    facts: list[dict[str, Any]] = Field(default_factory=list)
    capabilities: dict[str, bool] = Field(default_factory=dict)
    deadline: float | None = None


app = FastAPI(title="IMVERA LLM Worker", version="0.1.0")
state = WorkerState()
executor = InferenceExecutor(max_queue=4)


@app.on_event("startup")
def warmup() -> None:
    global _model, _tokenizer
    cfg = _load_config()
    model_id = cfg["models"]["llm"]["id"]
    try:
        from mlx_lm import load

        _model, _tokenizer = load(model_id)
        state.model_revision = model_id
        state.ready = True
        _generate_sync(
            [
                {"role": "system", "content": "Ответь одним словом: готово"},
                {"role": "user", "content": "проверка"},
            ],
            max_tokens=8,
        )
    except Exception as exc:
        state.warmup_error = str(exc)
        state.ready = False


mount_health(app, state, "llm")


@app.post("/v1/interpret")
async def interpret(req: InterpretRequest) -> dict[str, Any]:
    if not state.ready:
        raise HTTPException(503, detail=state.warmup_error or "not ready")
    if req.request_id in _cancelled:
        raise HTTPException(499, detail="cancelled")
    check_deadline(req.deadline)
    cfg = _load_config()
    ctx = req.context
    user_content = (
        f"Контекст звонка:\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
        f"Текущая реплика: {ctx.get('raw_text', '')}\n\n"
        f"{SEMANTIC_SCHEMA_HINT}"
    )
    messages = [
        {"role": "system", "content": INTERPRETER_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    raw = ""
    payload: dict[str, Any] | None = None
    for attempt in range(2):
        raw = await executor.run(
            lambda: _generate_sync(messages, cfg["models"]["llm"]["max_tokens_interpret"])
        )
        try:
            from packages.contracts.semantic import SemanticPayload

            candidate = _extract_json(raw)
            payload = SemanticPayload.model_validate(candidate).model_dump(mode="json")
            break
        except (json.JSONDecodeError, ValueError, Exception):
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": "Ответ невалиден. Верни только JSON SemanticPayload по схеме.",
                }
            )
    if payload is None:
        raise HTTPException(422, detail=f"invalid SemanticPayload after retry: {raw[:400]}")
    return {
        "request_id": req.request_id,
        "provider_request_id": req.request_id,
        "payload": payload,
        "model_revision": state.model_revision,
    }


@app.post("/v1/render")
async def render(req: RenderRequest) -> StreamingResponse:
    if not state.ready:
        raise HTTPException(503, detail=state.warmup_error or "not ready")
    if req.request_id in _cancelled:
        raise HTTPException(499, detail="cancelled")
    check_deadline(req.deadline)

    async def stream():
        cfg = _load_config()
        body = json.dumps(
            {
                "action": req.action,
                "facts": req.facts,
                "capabilities": req.capabilities,
            },
            ensure_ascii=False,
        )
        messages = [
            {"role": "system", "content": RENDERER_SYSTEM},
            {"role": "user", "content": body},
        ]
        from mlx_lm import stream_generate

        prompt = _tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=cfg["models"]["llm"].get("enable_thinking", False),
        )

        def _iter():
            for item in stream_generate(
                _model,
                _tokenizer,
                prompt=prompt,
                max_tokens=cfg["models"]["llm"]["max_tokens_render"],
            ):
                if req.request_id in _cancelled:
                    break
                yield item.text

        text = await executor.run(lambda: "".join(_iter()))
        yield json.dumps({"text": text.strip(), "done": True}, ensure_ascii=False) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.post("/v1/cancel")
def cancel(body: dict[str, Any]) -> dict[str, str]:
    rid = body.get("request_id")
    if rid:
        _cancelled.add(rid)
    return {"status": "accepted"}


def main() -> None:
    cfg = _load_config()
    port = int(os.environ.get("IMVERA_LLM_PORT", cfg["ports"]["llm"]))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
