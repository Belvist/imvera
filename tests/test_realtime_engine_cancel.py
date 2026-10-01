"""Real SDK cancellation must release its question without claiming delivery."""

import asyncio
from types import SimpleNamespace

import pytest

from packages.contracts.outbox import ActionOutboxStatus
from packages.core.memory_store import InMemoryCallRecordStore
from packages.dialogue.session import CallSession
from packages.dialogue_engine.delivery.outbox import EffectStatus
from packages.voice_runtime.call_actor import CallActor, MediaCallbacks
from packages.voice_runtime.playback import PlaybackQueue

pytestmark = pytest.mark.dialogue_engine


async def noop(*args, **kwargs):
    return None


@pytest.mark.parametrize("sent_samples", [0, 320])
def test_runtime_cancel_releases_sdk_playout_and_rejects_a_late_completion(sent_samples):
    async def scenario():
        session = CallSession(call_id="sdk-barge", family_id="family",
                              store=InMemoryCallRecordStore())
        initial = session.start()
        fx = initial.speak_effect
        assert fx is not None and fx.question_id
        engine = session._engine
        assert engine is not None and engine.state.playing_question is not None
        before_delivered = engine.state.delivered_question
        actor = CallActor(
            call_id=session.state.call_id, family_id="family", session=session,
            stt=SimpleNamespace(), tts=SimpleNamespace(cancel=noop),
            llm=SimpleNamespace(cancel_request=noop),
            media=MediaCallbacks(noop, noop, noop, noop),
        )
        actor._playback = PlaybackQueue(actor.call_id, sample_rate=16000)
        actor._playback.begin_phrase("runtime-gen", "p", fx.text)
        actor._playback._ledger.sent_samples = sent_samples
        actor._active_generation = "runtime-gen"
        actor._pending_mark_render_gen = "runtime-gen"
        actor._pending_mark_spoken_id = fx.generation_id
        actor._pending_speak_effect_id = fx.effect_id
        actor._outbox_action_id = fx.generation_id
        engine.outbox.mark_started(fx.effect_id)

        await actor._interrupt_playback(flush=True)
        assert engine.outbox.get_record(fx.effect_id).status == EffectStatus.CANCELLED
        assert engine.state.playing_question is None and engine.state.planned_question is None
        assert engine.state.active_playout is None
        assert engine.state.delivered_question == before_delivered
        assert actor._pending_mark_spoken_id is None and actor._pending_speak_effect_id is None
        assert fx.generation_id not in session._playout_meta
        record = session.transitions.get_outbox_record(session.state.call_id, fx.generation_id)
        expected = (
            ActionOutboxStatus.DELIVERY_UNKNOWN if sent_samples else ActionOutboxStatus.CANCELLED
        )
        assert record.status == expected

        revision = engine.revision
        session.cancel_playout_action(fx.generation_id)  # duplicate notification
        session.mark_spoken_action(fx.generation_id)  # late transport callback
        assert engine.revision == revision
        assert engine.state.delivered_question == before_delivered
        assert session.transitions.get_outbox_record(
            session.state.call_id, fx.generation_id,
        ).status == expected

        rich = engine.build_rich_turn("Голова болит.", utterance_id="u-1")
        followup = session.handle_user_text("Голова болит.", utterance_id="u-1", rich_turn=rich)
        assert followup.speak_effect is not None
        assert followup.speak_effect.generation_id != fx.generation_id
        assert any(
            "голов" in ep.primary_label.lower() for ep in engine.state.issue_episodes.values()
        )
        assert not session._engine.state.call_closed

    asyncio.run(scenario())
