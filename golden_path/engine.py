"""Golden Path engine — single entry point for Stage A."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from golden_path.analyzer import Analysis, AnalysisKind, AnswerType, analyze_turn
from golden_path.content_plan import build_content_plan, build_correction_hint
from golden_path.fallbacks import typed_fallback
from golden_path.llm import GoldenPathLLM, LLMBackend
from golden_path.planner import Plan, PlannerAction, plan_turn
from golden_path.prompts import GREETING_TEXT
from golden_path.slots import SlotName, SlotStatus
from golden_path.state import ConversationState
from golden_path.trace import TraceWriter
from golden_path.validator import ValidatorResult, validate_reply


@dataclass
class TurnResult:
    assistant_text: str
    plan: Plan
    analysis: Analysis
    trace_path: str
    turn_no: int
    content_plan: dict[str, Any] | None = None
    raw_llm_output: str | None = None
    validator_result: dict[str, Any] | None = None
    regen_used: bool = False
    fallback_used: bool = False
    deterministic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "assistant_text": self.assistant_text,
            "plan": self.plan.to_dict(),
            "analysis": self.analysis.to_dict(),
            "trace_path": self.trace_path,
            "turn_no": self.turn_no,
            "content_plan": self.content_plan,
            "raw_llm_output": self.raw_llm_output,
            "validator_result": self.validator_result,
            "regen_used": self.regen_used,
            "fallback_used": self.fallback_used,
            "deterministic": self.deterministic,
        }


class GoldenPathEngine:
    """State → Analyzer → Planner → LLM → Validator."""

    def __init__(
        self,
        llm: LLMBackend | None = None,
        trace_dir: str | None = None,
        session_id: str | None = None,
    ) -> None:
        self.llm: LLMBackend = llm or GoldenPathLLM()
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.state = ConversationState(session_id=self.session_id)
        self.turn_no = 0
        self._trace = TraceWriter(
            self.session_id,
            trace_dir=None if trace_dir is None else Path(trace_dir),
        )
        self._ended = False

    def begin_session(self) -> str:
        self.state = ConversationState(session_id=self.session_id)
        self.turn_no = 0
        self._ended = False
        self._trace.write_event("session_begin", {"session_id": self.session_id})
        greeting = GREETING_TEXT
        self.state.greeted = True
        self.state.record_turn("assistant", greeting)
        self.state.pending_slot = SlotName.WELLNESS
        self.state.note_assistant_question(greeting)
        self._trace.write_event(
            "greeting",
            {"assistant_text": greeting, "pending_slot": SlotName.WELLNESS.value},
        )
        return greeting

    def _action_for_llm(self, plan: Plan) -> str:
        if plan.action == PlannerAction.ASK_SLOT:
            return "ASK_SLOT"
        if plan.action == PlannerAction.ANSWER_USER:
            return "ANSWER_USER"
        return plan.action.value

    def _deterministic_phrase(
        self,
        plan: Plan,
        slot: SlotName | None,
    ) -> ValidatorResult | None:
        """Typed responses for control flows — no LLM where variation adds risk."""
        if plan.action == PlannerAction.SAFETY:
            return validate_reply(None, plan.action, self.state, slot=slot)
        control_actions = (
            PlannerAction.WAIT,
            PlannerAction.CLOSE,
            PlannerAction.HANDLE_REFUSAL,
            PlannerAction.HANDLE_CORRECTION,
            PlannerAction.REPAIR,
            PlannerAction.HANDLE_FATIGUE,
        )
        if plan.action in control_actions:
            text = typed_fallback(
                plan.action,
                self.state,
                slot=slot,
                answer_type=plan.answer_type,
            )
            return ValidatorResult(ok=True, text=text, violations=[], used_fallback=True)
        if plan.action == PlannerAction.ANSWER_USER and plan.answer_type in (
            AnswerType.IDENTITY,
            AnswerType.PRIVACY,
            AnswerType.WHY_CALLING,
        ):
            text = typed_fallback(
                plan.action,
                self.state,
                answer_type=plan.answer_type,
            )
            return ValidatorResult(ok=True, text=text, violations=[], used_fallback=True)
        return None

    def _generate_and_validate(
        self,
        plan: Plan,
        analysis: Analysis,
        user_text: str,
        slot: SlotName | None,
    ) -> tuple[str | None, str, ValidatorResult, bool]:
        action = self._action_for_llm(plan)
        content_plan = build_content_plan(plan, self.state, analysis, user_text)
        raw_llm, bundle = self.llm.generate(
            action=action,
            user_message=user_text,
            state=self.state,
            slot=slot,
            answer_type=plan.answer_type,
            content_plan=content_plan,
        )
        validated = validate_reply(
            raw_llm,
            plan.action,
            self.state,
            slot=slot,
            answer_type=plan.answer_type,
            apply_fallback=False,
        )
        if validated.ok:
            return raw_llm, bundle.exact_prompt, validated, False

        correction = build_correction_hint(validated.violations, plan, content_plan)
        raw_retry, bundle_retry = self.llm.generate(
            action=action,
            user_message=user_text,
            state=self.state,
            slot=slot,
            answer_type=plan.answer_type,
            content_plan=content_plan,
            correction_hint=correction,
        )
        validated_retry = validate_reply(
            raw_retry,
            plan.action,
            self.state,
            slot=slot,
            answer_type=plan.answer_type,
            apply_fallback=True,
        )
        return raw_retry, bundle_retry.exact_prompt, validated_retry, True

    def handle_turn(self, user_text: str) -> TurnResult:
        if self._ended:
            raise RuntimeError("session already ended")

        self.turn_no += 1
        state_before = self.state.compact_dict()

        analysis = analyze_turn(user_text, self.state)
        self.state.reduce_user_turn(
            user_text,
            analysis.kind.value,
            analysis.facts,
            refusal_slot=analysis.refusal_slot,
        )
        state_after_user = self.state.compact_dict()

        plan = plan_turn(self.state, analysis)
        content_plan = build_content_plan(plan, self.state, analysis, user_text)
        content_plan_dict = content_plan.to_dict()

        slot = plan.slot
        raw_llm: str | None = None
        exact_prompt = ""
        regen_used = False
        deterministic = False

        if plan.action == PlannerAction.GREET:
            assistant = GREETING_TEXT
            validated = validate_reply(assistant, plan.action, self.state, slot=slot)
        elif (det := self._deterministic_phrase(plan, slot)) is not None:
            validated = det
            exact_prompt = f"ACTION: {plan.action_name()} [deterministic]"
            deterministic = True
        elif plan.action == PlannerAction.SAFETY:
            assistant = None
            exact_prompt = f"ACTION: SAFETY\nUSER MESSAGE: {user_text}"
            validated = validate_reply(assistant, plan.action, self.state, slot=slot)
            deterministic = True
        else:
            raw_llm, exact_prompt, validated, regen_used = self._generate_and_validate(
                plan, analysis, user_text, slot
            )

        final_text = validated.text
        fallback_used = validated.used_fallback

        if plan.action == PlannerAction.ASK_SLOT and slot is not None:
            self.state.pending_slot = slot
            if validated.ok and not validated.used_fallback:
                self.state.current_topic = slot

        if plan.action == PlannerAction.CLOSE:
            self.state.closing = True
            self._ended = True
        elif plan.action == PlannerAction.HANDLE_FATIGUE and any(
            w in user_text.lower() for w in ("закончим", "хватит", "пока")
        ):
            self.state.closing = True
            self._ended = True

        self.state.record_turn("user", user_text)
        self.state.record_turn("assistant", final_text)
        self.state.note_assistant_question(final_text)

        state_after = self.state.compact_dict()

        self._trace.write_turn(
            turn_no=self.turn_no,
            user_text=user_text,
            state_before=state_before,
            state_after_user=state_after_user,
            analysis=analysis,
            planner_action=plan,
            content_plan=content_plan_dict,
            required_slot=slot.value if slot else None,
            exact_llm_prompt=exact_prompt,
            raw_llm_output=raw_llm,
            validator_result=validated,
            regen_used=regen_used,
            fallback_used=fallback_used,
            deterministic=deterministic,
            final_assistant_text=final_text,
            state_after=state_after,
        )

        return TurnResult(
            assistant_text=final_text,
            plan=plan,
            analysis=analysis,
            trace_path=self._trace.location,
            turn_no=self.turn_no,
            content_plan=content_plan_dict,
            raw_llm_output=raw_llm,
            validator_result=validated.to_dict(),
            regen_used=regen_used,
            fallback_used=fallback_used,
            deterministic=deterministic,
        )

    def mark_last_turn(self) -> bool:
        """Observability only — does not mutate conversation state."""
        if self.turn_no < 1:
            return False
        self._trace.write_event(
            "owner_mark",
            {"turn_no": self.turn_no, "owner_mark": "BAD"},
        )
        return True

    def end_session(self) -> dict[str, Any]:
        self._ended = True
        summary = {
            "session_id": self.session_id,
            "turns": self.turn_no,
            "facts": dict(self.state.facts),
            "slot_statuses": {
                k.value: v.value for k, v in self.state.slot_statuses.items()
            },
            "trace_path": self._trace.location,
        }
        self._trace.write_event("session_end", summary)
        return summary

    def reset(self) -> str:
        self.session_id = uuid.uuid4().hex[:12]
        self._trace = TraceWriter(self.session_id)
        return self.begin_session()

    @property
    def trace_path(self) -> str:
        return self._trace.location

    def plan_only(self, user_text: str) -> tuple[Analysis, Plan]:
        """Inspect planner without mutating state — for scenario runner."""
        analysis = analyze_turn(user_text, self.state)
        plan = plan_turn(self.state, analysis)
        return analysis, plan
