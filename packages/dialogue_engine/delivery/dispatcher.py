"""Routes engine decisions into the typed outbox."""

from __future__ import annotations

from packages.dialogue_engine.delivery.decision import Decision
from packages.dialogue_engine.delivery.outbox import EffectOutbox
from packages.dialogue_engine.effects import EndCallEffect, SpeakEffect, TimerEffect


class EffectDispatcher:
    """Accept whole decisions — never mix effect kinds in one destructive pop."""

    def __init__(self, outbox: EffectOutbox) -> None:
        self.outbox = outbox

    def accept(self, decision: Decision) -> None:
        self.outbox.accept_decision(decision)

    def claim_speak(self) -> SpeakEffect | None:
        return self.outbox.claim_next_speak()

    def claim_timer(self) -> TimerEffect | None:
        return self.outbox.claim_next_timer()

    def claim_hangup(self) -> EndCallEffect | None:
        return self.outbox.claim_next_hangup()

    def drain_speaks(self) -> list[SpeakEffect]:
        return self.outbox.drain_speak_effects()
