"""Thin HTTP LLM client for Golden Path — no conversation_system imports."""
from __future__ import annotations

import http.client
import json
import logging
import re
import socket
import time
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from golden_path.analyzer import AnswerType
from golden_path.llm_config import LLMRuntimeConfig, load_llm_config
from golden_path.llm_errors import (
    LLMRuntimeError,
    TURN_FAILED_LLM_EMPTY,
    TURN_FAILED_LLM_IDENTITY,
    TURN_FAILED_LLM_PROTOCOL,
    TURN_FAILED_LLM_TIMEOUT,
    TURN_FAILED_LLM_UNAVAILABLE,
)
from golden_path.llm_identity import (
    identity_matches_config,
    parse_canonical_health,
)
from golden_path.content_plan import ContentPlan
from golden_path.generation_profile import (
    DEFAULT_MAX_TOKENS,
    GenerationProfile,
    load_generation_profile,
    max_tokens_for_action,
)
from golden_path.prompts import (
    PHRASE_RENDERER_SYSTEM,
    build_renderer_prompt,
    build_user_prompt,
    clean_llm_output,
    contains_thinking_leak,
)
from golden_path.slots import SlotName, answered_slots, declined_slots
from golden_path.state import ConversationState


_logger = logging.getLogger(__name__)

_STAGE_A_P50_TARGET_MS = 4000.0
_STAGE_A_P95_TARGET_MS = 8000.0


class LLMBackend(ABC):
    @abstractmethod
    def chat(self, messages: list[dict[str, str]], max_tokens: int = 100) -> str:
        """Generate assistant text from chat messages."""


@dataclass
class PromptBundle:
    exact_prompt: str
    messages: list[dict[str, str]]


@dataclass
class ChatMetrics:
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    ttft_ms: float | None = None
    tokens_per_sec: float | None = None


@dataclass(frozen=True)
class LLMHealthStatus:
    ready: bool
    model_id: str
    revision: str
    backend: str
    protocol: str
    device: str
    base_url: str
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        out = {
            "ready": self.ready,
            "model_id": self.model_id,
            "revision": self.revision,
            "backend": self.backend,
            "protocol": self.protocol,
            "device": self.device,
            "base_url": self.base_url,
            "raw": self.raw,
        }
        if "thinking" in self.raw:
            out["thinking"] = self.raw.get("thinking")
        if "generation_profile" in self.raw:
            out["generation_profile"] = self.raw.get("generation_profile")
        return out


class GoldenPathLLM(LLMBackend):
    """Real local LLM via OpenAI-compatible HTTP or native /chat."""

    def __init__(
        self,
        base_url: str | None = None,
        protocol: str | None = None,
        timeout: float | None = None,
        config: LLMRuntimeConfig | None = None,
    ) -> None:
        self.config = config or load_llm_config(base_url=base_url, protocol=protocol)
        self.base_url = self.config.base_url
        self.openai = self.config.protocol == "openai"
        self.timeout = timeout if timeout is not None else self.config.timeout_s
        self.profile: GenerationProfile = load_generation_profile()
        self._last_chat_metrics = ChatMetrics()

    @property
    def last_chat_metrics(self) -> ChatMetrics:
        return self._last_chat_metrics

    def health_ok(self) -> bool:
        return self.check_health().ready

    def _fetch_health_json(self) -> dict[str, Any]:
        try:
            req = urllib.request.Request(f"{self.base_url}/health")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return json.loads(resp.read().decode())
        except OSError as exc:
            return {"error": str(exc), "ready": False}

    def _openai_models_status(self) -> int:
        conn: http.client.HTTPConnection | None = None
        try:
            parts = urllib.parse.urlsplit(self.base_url)
            host = parts.hostname or "127.0.0.1"
            port = parts.port or 9500
            path = (parts.path or "").rstrip("/") + "/v1/models"
            conn = http.client.HTTPConnection(host, port, timeout=3.0)
            conn.request("GET", path)
            resp = conn.getresponse()
            resp.read()
            return resp.status
        except OSError:
            return 0
        finally:
            if conn is not None:
                try:
                    conn.close()
                except OSError:
                    pass

    def _native_chat_probe_status(self) -> int:
        try:
            body = json.dumps(
                {
                    "messages": [{"role": "user", "content": "пинг"}],
                    "max_tokens": 4,
                }
            ).encode()
            req = urllib.request.Request(
                f"{self.base_url}/chat",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=min(self.timeout, 30.0)) as resp:
                return resp.status
        except urllib.error.HTTPError as exc:
            return exc.code
        except OSError:
            return 0

    def _protocol_endpoint_ready(self) -> tuple[bool, str]:
        if self.openai:
            status = self._openai_models_status()
            if status == 200:
                return True, ""
            return False, f"/v1/models returned HTTP {status}"
        status = self._native_chat_probe_status()
        if status == 200:
            return True, ""
        return False, f"/chat probe returned HTTP {status}"

    def check_health(self) -> LLMHealthStatus:
        raw = self._fetch_health_json()
        identity = parse_canonical_health(raw)
        ready = False
        if identity is not None and identity.ready:
            mismatches = identity_matches_config(identity, self.config)
            if mismatches:
                raw = {**raw, "identity_mismatch": mismatches, "ready": False}
            else:
                proto_ok, proto_detail = self._protocol_endpoint_ready()
                if not proto_ok:
                    raw = {**raw, "protocol_probe_failed": proto_detail, "ready": False}
                else:
                    ready = True

        if identity is not None:
            return LLMHealthStatus(
                ready=ready,
                model_id=identity.model_id,
                revision=identity.revision,
                backend=identity.backend,
                protocol=identity.protocol,
                device=identity.device,
                base_url=self.base_url,
                raw=raw,
            )

        return LLMHealthStatus(
            ready=False,
            model_id="",
            revision="",
            backend="",
            protocol=self.config.protocol,
            device="",
            base_url=self.base_url,
            raw=raw,
        )

    def require_ready(self) -> LLMHealthStatus:
        raw = self._fetch_health_json()
        if raw.get("error"):
            raise LLMRuntimeError(
                TURN_FAILED_LLM_UNAVAILABLE,
                f"endpoint unreachable: {raw.get('error')}",
            )

        identity = parse_canonical_health(raw)
        if identity is None:
            raise LLMRuntimeError(
                TURN_FAILED_LLM_PROTOCOL,
                "server /health missing canonical fields "
                "(model_id, revision, backend, protocol, device)",
            )

        mismatches = identity_matches_config(identity, self.config)
        if mismatches:
            raise LLMRuntimeError(
                TURN_FAILED_LLM_IDENTITY,
                "; ".join(mismatches),
            )

        if not identity.ready:
            raise LLMRuntimeError(
                TURN_FAILED_LLM_UNAVAILABLE,
                "ready=false on server /health",
            )

        proto_ok, proto_detail = self._protocol_endpoint_ready()
        if not proto_ok:
            raise LLMRuntimeError(
                TURN_FAILED_LLM_PROTOCOL,
                proto_detail or f"protocol={self.config.protocol} not confirmed",
            )

        return LLMHealthStatus(
            ready=True,
            model_id=identity.model_id,
            revision=identity.revision,
            backend=identity.backend,
            protocol=identity.protocol,
            device=identity.device,
            base_url=self.base_url,
            raw=raw,
        )

    def build_prompt_bundle(
        self,
        action: str,
        user_message: str,
        state: ConversationState,
        slot: SlotName | None = None,
        answer_type: AnswerType | None = None,
        content_plan: ContentPlan | None = None,
        correction_hint: str = "",
    ) -> PromptBundle:
        if content_plan is not None:
            user_prompt = build_renderer_prompt(
                content_plan,
                user_message,
                correction_hint=correction_hint,
            )
        else:
            answered = answered_slots(state.slot_statuses)
            blocked = answered + declined_slots(state.slot_statuses)
            user_prompt = build_user_prompt(
                action=action,
                user_message=user_message,
                state_compact=state.compact_dict(),
                already_answered=answered,
                do_not_ask=blocked,
                slot=slot,
                last_assistant=state.last_assistant_text,
                answer_type=answer_type,
            )
        messages = [
            {"role": "system", "content": PHRASE_RENDERER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]
        return PromptBundle(exact_prompt=user_prompt, messages=messages)

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        *,
        profile: GenerationProfile | None = None,
    ) -> str:
        budget = max_tokens if max_tokens is not None else DEFAULT_MAX_TOKENS
        prof = profile or self.profile
        if self.openai:
            text, metrics = self._chat_openai(messages, budget, prof)
            self._last_chat_metrics = metrics
            return text
        text, metrics = self._chat_native(messages, budget)
        self._last_chat_metrics = metrics
        return text

    def generate(
        self,
        action: str,
        user_message: str,
        state: ConversationState,
        slot: SlotName | None = None,
        answer_type: AnswerType | None = None,
        content_plan: ContentPlan | None = None,
        correction_hint: str = "",
    ) -> tuple[str, PromptBundle]:
        bundle = self.build_prompt_bundle(
            action,
            user_message,
            state,
            slot=slot,
            answer_type=answer_type,
            content_plan=content_plan,
            correction_hint=correction_hint,
        )
        budget = max_tokens_for_action(action)
        raw = self.chat(bundle.messages, max_tokens=budget)
        cleaned = clean_llm_output(raw)
        if contains_thinking_leak(raw):
            _logger.warning("thinking leak detected in LLM output")
        return cleaned, bundle

    def verify_thinking_disabled(self) -> dict[str, Any]:
        """Self-test: one short request must not emit thinking blocks."""
        messages = [
            {"role": "system", "content": PHRASE_RENDERER_SYSTEM},
            {
                "role": "user",
                "content": (
                    "ACTION: WAIT\nSEMANTIC RESPONSE:\n- коротко подтвердить ожидание\n"
                    "OUTPUT: одна короткая фраза."
                ),
            },
        ]
        raw = self.chat(messages, max_tokens=16)
        leak = contains_thinking_leak(raw)
        return {
            "thinking_disabled": not leak,
            "sample_output": clean_llm_output(raw),
            "raw_length": len(raw or ""),
        }

    def _parse_openai_metrics(
        self, data: dict[str, Any], elapsed_ms: float
    ) -> ChatMetrics:
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        timings = data.get("timings") or {}
        ttft_ms: float | None = None
        if timings.get("prompt_ms") is not None:
            ttft_ms = float(timings["prompt_ms"])
        tokens_per_sec: float | None = None
        if completion_tokens > 0 and elapsed_ms > 0:
            gen_ms = elapsed_ms - (ttft_ms or 0.0)
            if gen_ms > 0:
                tokens_per_sec = completion_tokens / (gen_ms / 1000.0)
        return ChatMetrics(
            latency_ms=elapsed_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            ttft_ms=ttft_ms,
            tokens_per_sec=tokens_per_sec,
        )

    def _chat_openai(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
        profile: GenerationProfile,
    ) -> tuple[str, ChatMetrics]:
        conn: http.client.HTTPConnection | None = None
        started = time.perf_counter()
        try:
            parts = urllib.parse.urlsplit(self.base_url)
            host = parts.hostname or "127.0.0.1"
            port = parts.port or 9500
            path = (parts.path or "").rstrip("/") + "/v1/chat/completions"
            conn = http.client.HTTPConnection(host, port, timeout=self.timeout)
            body: dict[str, Any] = {
                "model": self.config.model_id,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": profile.temperature,
                "top_p": profile.top_p,
                "stream": False,
                "thinking": False,
                "stop": ["\n\n"],
                "chat_template_kwargs": {"enable_thinking": False},
            }
            if profile.top_k > 0:
                body["top_k"] = profile.top_k
            if profile.min_p > 0:
                body["min_p"] = profile.min_p
            if profile.repetition_penalty != 1.0:
                body["repeat_penalty"] = profile.repetition_penalty
            conn.request(
                "POST",
                path,
                body=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
            )
            resp = conn.getresponse()
            payload = resp.read()
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if resp.status == 503:
                raise LLMRuntimeError(
                    TURN_FAILED_LLM_UNAVAILABLE,
                    f"HTTP 503 from {path}",
                )
            if resp.status != 200:
                if resp.status == 404:
                    raise LLMRuntimeError(
                        TURN_FAILED_LLM_PROTOCOL,
                        f"HTTP {resp.status} on {path}",
                    )
                raise LLMRuntimeError(
                    TURN_FAILED_LLM_UNAVAILABLE,
                    f"HTTP {resp.status} from {path}",
                )
            data = json.loads(payload.decode())
            metrics = self._parse_openai_metrics(data, elapsed_ms)
            msg = data["choices"][0]["message"]
            out = msg.get("content") or ""
            reasoning = msg.get("reasoning_content") or ""
            if not out and reasoning:
                _logger.warning("model returned reasoning_content without content")
                raise LLMRuntimeError(
                    TURN_FAILED_LLM_EMPTY,
                    "thinking-only response (reasoning_content without content)",
                )
            if contains_thinking_leak(out):
                out = clean_llm_output(out)
            if not out:
                raise LLMRuntimeError(TURN_FAILED_LLM_EMPTY, "empty content from model")
            return out, metrics
        except (TimeoutError, socket.timeout) as exc:
            raise LLMRuntimeError(TURN_FAILED_LLM_TIMEOUT, str(exc)) from exc
        except LLMRuntimeError:
            raise
        except OSError as exc:
            raise LLMRuntimeError(TURN_FAILED_LLM_UNAVAILABLE, str(exc)) from exc
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            raise LLMRuntimeError(TURN_FAILED_LLM_UNAVAILABLE, str(exc)) from exc
        finally:
            if conn is not None:
                try:
                    conn.close()
                except OSError as exc:
                    _logger.debug("llm connection close failed: %s", exc)

    def _chat_native(
        self, messages: list[dict[str, str]], max_tokens: int
    ) -> tuple[str, ChatMetrics]:
        started = time.perf_counter()
        try:
            body = json.dumps(
                {"messages": messages, "max_tokens": max_tokens}
            ).encode()
            req = urllib.request.Request(
                f"{self.base_url}/chat",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                obj = json.loads(resp.read().decode())
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if obj.get("ok") and obj.get("text"):
                return str(obj["text"]), ChatMetrics(latency_ms=elapsed_ms)
            raise LLMRuntimeError(TURN_FAILED_LLM_EMPTY, "native /chat returned no text")
        except (TimeoutError, socket.timeout) as exc:
            raise LLMRuntimeError(TURN_FAILED_LLM_TIMEOUT, str(exc)) from exc
        except LLMRuntimeError:
            raise
        except OSError as exc:
            raise LLMRuntimeError(TURN_FAILED_LLM_UNAVAILABLE, str(exc)) from exc
        except (json.JSONDecodeError, KeyError) as exc:
            raise LLMRuntimeError(TURN_FAILED_LLM_UNAVAILABLE, str(exc)) from exc


class MockLLM(GoldenPathLLM):
    """Test-only deterministic backend."""

    def __init__(self, replies: dict[str, str] | None = None) -> None:
        super().__init__(
            config=LLMRuntimeConfig(
                model_id="mock",
                revision="test",
                backend="mock",
                protocol="openai",
                device="cpu",
                base_url="mock://local",
                timeout_s=1.0,
            )
        )
        self._replies = replies or {}

    def check_health(self) -> LLMHealthStatus:
        return LLMHealthStatus(
            ready=True,
            model_id="mock",
            revision="test",
            backend="mock",
            protocol="openai",
            device="cpu",
            base_url="mock://local",
            raw={
                "ready": True,
                "model_id": "mock",
                "revision": "test",
                "backend": "mock",
                "protocol": "openai",
                "device": "cpu",
            },
        )

    def require_ready(self) -> LLMHealthStatus:
        return self.check_health()

    def _openai_models_status(self) -> int:
        return 200

    def chat(self, messages: list[dict[str, str]], max_tokens: int = 100) -> str:
        user = messages[-1]["content"] if messages else ""
        for key, reply in self._replies.items():
            if key in user:
                self._last_chat_metrics = ChatMetrics(latency_ms=1.0, completion_tokens=8)
                return reply
        canned = [
            ("ACTION: ASK_SLOT(mood)", "Рада слышать. Как у вас настроение сегодня?"),
            ("ACTION: ASK_SLOT(sleep)", "Поняла. А как вы спали прошлой ночью?"),
            ("ACTION: ANSWER_USER", "Я помощник сервиса Имвера, звоню узнать, как вы себя чувствуете."),
            ("ACTION: HANDLE_CORRECTION", "Спасибо, поняла: речь о спине, не о голове."),
            ("ACTION: SAFETY", "Понимаю, это важно. Оставайтесь на линии."),
            ("ACTION: REPAIR", "Конечно, повторю: как вы себя чувствуете сегодня?"),
            ("ACTION: CLOSE", "Берегите себя, хорошего дня!"),
        ]
        for needle, reply in canned:
            if needle in user:
                self._last_chat_metrics = ChatMetrics(
                    latency_ms=1.0, completion_tokens=len(reply.split())
                )
                return reply
        self._last_chat_metrics = ChatMetrics(latency_ms=1.0, completion_tokens=4)
        return "Тестовый ответ без LLM."


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((pct / 100.0) * (len(ordered) - 1)))
    return ordered[idx]


def run_readiness_probe(
    llm: GoldenPathLLM,
    *,
    calls: int = 20,
    warmup_calls: int = 2,
) -> dict[str, Any]:
    """Run consecutive real LLM calls after warm-up; raise on any failure."""
    health = llm.require_ready()
    for i in range(warmup_calls):
        llm.chat(
            [
                {"role": "system", "content": "Ответь одним коротким русским словом."},
                {"role": "user", "content": f"разогрев {i}"},
            ],
            max_tokens=8,
        )

    latencies_ms: list[float] = []
    prompt_tokens: list[int] = []
    completion_tokens: list[int] = []
    ttft_ms: list[float] = []
    tokens_per_sec: list[float] = []

    for i in range(calls):
        text = llm.chat(
            [
                {"role": "system", "content": "Ответь одним коротким русским словом."},
                {"role": "user", "content": f"пинг {i}"},
            ],
            max_tokens=16,
        )
        metrics = llm.last_chat_metrics
        if not text.strip():
            raise LLMRuntimeError(TURN_FAILED_LLM_EMPTY, f"probe call {i + 1}")
        latencies_ms.append(metrics.latency_ms)
        prompt_tokens.append(metrics.prompt_tokens)
        completion_tokens.append(metrics.completion_tokens)
        if metrics.ttft_ms is not None:
            ttft_ms.append(metrics.ttft_ms)
        if metrics.tokens_per_sec is not None:
            tokens_per_sec.append(metrics.tokens_per_sec)

    p50 = percentile(latencies_ms, 50)
    p95 = percentile(latencies_ms, 95)
    return {
        "model_id": health.model_id,
        "revision": health.revision,
        "backend": health.backend,
        "protocol": health.protocol,
        "device": health.device,
        "calls": calls,
        "warmup_calls": warmup_calls,
        "successful_calls": calls,
        "failed_calls": 0,
        "timeouts": 0,
        "p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
        "latency_p50_ms": round(p50, 1),
        "latency_p95_ms": round(p95, 1),
        "latency_max_ms": round(max(latencies_ms), 1),
        "max_ms": round(max(latencies_ms), 1),
        "prompt_tokens_avg": round(sum(prompt_tokens) / len(prompt_tokens), 1) if prompt_tokens else 0,
        "completion_tokens_avg": round(sum(completion_tokens) / len(completion_tokens), 1)
        if completion_tokens
        else 0,
        "ttft_p50_ms": round(percentile(ttft_ms, 50), 1) if ttft_ms else None,
        "ttft_p95_ms": round(percentile(ttft_ms, 95), 1) if ttft_ms else None,
        "tokens_per_sec_avg": round(sum(tokens_per_sec) / len(tokens_per_sec), 2)
        if tokens_per_sec
        else None,
        "stage_a_latency_ok": p50 <= _STAGE_A_P50_TARGET_MS and p95 <= _STAGE_A_P95_TARGET_MS,
        "stage_a_latency_targets_ms": {
            "p50_max": _STAGE_A_P50_TARGET_MS,
            "p95_max": _STAGE_A_P95_TARGET_MS,
        },
        "latencies_ms": [round(x, 1) for x in latencies_ms],
    }
