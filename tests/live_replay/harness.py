"""Trace replay through CallActor orchestration path (no telephony)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packages.dialogue_engine.events import CallStarted
from packages.dialogue_engine.reducer import reduce
from packages.dialogue_engine.semantic_kernel.kernel import interpret
from packages.dialogue_engine.state import EngineState
from packages.dialogue_engine.turn_understanding import build_rich_turn_from_text
from packages.voice_perception.post_stt_gate import (
    PostSTTContext,
    TurnAdmissionVerdict,
    evaluate_post_stt_turn,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@dataclass
class ReplayTurn:
    bot_text: str
    stt_final: str
    answer_slot: str | None = None
    pending_episode_attribute: str | None = None
    acoustic_verdict: str | None = None
    acoustic_score: float = 0.0
    playback_active: bool = False
    milliseconds_since_playout_end: int = 2000
    expected_admission: str = "ACCEPT"
    expected_intent_prefix: str | None = None
    expected_no_intents: tuple[str, ...] = ()
    expected_partial_close: bool = False
    expected_episode_attribute: str | None = None


@dataclass
class ReplayFixture:
    call_id: str
    elder_display_name: str
    opening: bool = True
    bootstrap: dict[str, Any] = field(default_factory=dict)
    turns: list[ReplayTurn] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> ReplayFixture:
        raw = json.loads(path.read_text(encoding="utf-8"))
        turns = [ReplayTurn(**t) for t in raw.get("turns", [])]
        return cls(
            call_id=raw["call_id"],
            elder_display_name=raw.get("elder_display_name", "Даниил"),
            opening=raw.get("opening", True),
            bootstrap=raw.get("bootstrap", {}),
            turns=turns,
        )


@dataclass
class ReplayResult:
    call_id: str
    admissions: list[str]
    intents: list[str]
    partial_close: bool
    state: EngineState
    turn_intents: list[list[str]] = field(default_factory=list)


def replay_fixture(fixture: ReplayFixture) -> ReplayResult:
    state = EngineState(
        call_id=fixture.call_id,
        elder_display_name=fixture.elder_display_name,
    )
    _apply_bootstrap(state, fixture.bootstrap)
    admissions: list[str] = []
    intents: list[str] = []
    turn_intents: list[list[str]] = []

    if fixture.opening:
        state, effects = reduce(state, CallStarted(call_id=fixture.call_id))
        for effect in effects:
            if hasattr(effect, "intent"):
                intents.append(effect.intent)
        state, extra = reduce(
            state,
            _playout_completed_from_effects(effects, state.revision),
        )
        for effect in extra:
            if hasattr(effect, "intent"):
                intents.append(effect.intent)

    for idx, turn in enumerate(fixture.turns, start=1):
        turn_start = len(intents)
        utterance_id = f"u-{idx}"
        kernel = interpret(
            turn.stt_final,
            utterance_id=utterance_id,
            engine_state=state,
        )
        admission = evaluate_post_stt_turn(
            PostSTTContext(
                user_text=turn.stt_final,
                last_bot_text=turn.bot_text,
                bot_candidates=(turn.bot_text,),
                acoustic_echo_verdict=turn.acoustic_verdict,
                acoustic_echo_score=turn.acoustic_score,
                playback_active=turn.playback_active,
                milliseconds_since_playout_end=turn.milliseconds_since_playout_end,
                answer_slot=turn.answer_slot or state.answer_context_slot(),
                pending_episode_attribute=turn.pending_episode_attribute
                or state.pending_episode_attribute,
                semantic_result=kernel,
            )
        )
        admissions.append(str(admission.verdict))
        if admission.verdict == TurnAdmissionVerdict.HOLD_FRAGMENT:
            turn_intents.append([])
            continue
        if admission.verdict == TurnAdmissionVerdict.DROP_ECHO:
            turn_intents.append([])
            continue

        rich = build_rich_turn_from_text(
            turn.stt_final,
            utterance_id=utterance_id,
            engine_state=state,
        )
        from packages.dialogue_engine.events import UserTurnReceived

        state, effects = reduce(
            state,
            UserTurnReceived(
                turn_id=utterance_id,
                text=turn.stt_final,
                rich_turn=rich,
                revision=state.revision,
            ),
        )
        speak_effects = [e for e in effects if hasattr(e, "intent")]
        for effect in speak_effects:
            intents.append(effect.intent)
        if speak_effects:
            state, extra = reduce(
                state,
                _playout_completed_from_effects(speak_effects, state.revision),
            )
            for effect in extra:
                if hasattr(effect, "intent"):
                    intents.append(effect.intent)
        turn_intents.append(intents[turn_start:])

    partial_close = "partial_unresolved_close" in intents
    return ReplayResult(
        call_id=fixture.call_id,
        admissions=admissions,
        intents=intents,
        partial_close=partial_close,
        state=state,
        turn_intents=turn_intents,
    )


def _apply_bootstrap(state: EngineState, bootstrap: dict[str, Any]) -> None:
    if not bootstrap:
        return
    from packages.dialogue_engine.state import IssueEpisode

    ep_raw = bootstrap.get("episode")
    if isinstance(ep_raw, dict):
        ep = IssueEpisode(**ep_raw)
        state.issue_episodes[ep.episode_id] = ep
        state.active_episode_id = ep.episode_id
    if bootstrap.get("pending_episode_attribute"):
        state.pending_episode_attribute = bootstrap["pending_episode_attribute"]
    for slot, status in bootstrap.get("slots", {}).items():
        state.slots[slot] = status


def _playout_completed_from_effects(effects: list, revision: int):
    from packages.dialogue_engine.effects import SpeakEffect
    from packages.dialogue_engine.events import PlayoutCompleted

    for effect in reversed(effects):
        if isinstance(effect, SpeakEffect):
            return PlayoutCompleted(
                generation=effect.generation,
                question_id=effect.question_id,
                revision=revision,
            )
    raise RuntimeError("no deliverable speak effect in replay step")


def assert_fixture_invariants(fixture: ReplayFixture, result: ReplayResult) -> None:
    assert len(result.admissions) == len(fixture.turns)
    for turn, verdict, intents in zip(
        fixture.turns, result.admissions, result.turn_intents, strict=True
    ):
        assert verdict == turn.expected_admission, (
            f"{fixture.call_id}: {turn.stt_final!r} admission {verdict}"
        )
        if turn.expected_intent_prefix:
            assert any(
                i.startswith(turn.expected_intent_prefix) for i in intents
            ), f"missing intent prefix {turn.expected_intent_prefix}"
        for forbidden in turn.expected_no_intents:
            assert forbidden not in intents, f"forbidden intent {forbidden}"
    if any(t.expected_partial_close for t in fixture.turns):
        assert result.partial_close
    else:
        assert not result.partial_close
