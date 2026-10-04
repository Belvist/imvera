# One semantic need, one speech owner (2026-10-04)

Branch: `feature/voice-zoiper-m5`; baseline3957f625e17204e0d11ef698b53045046fd5b047.
This is a narrow correctness cut in the existing SDK, not a new conversational
brain or proof of natural phone quality.

## Reproduced failures

After food and medication replies, coverage emitted:
`Как настроение? Ничего не беспокоит?` or
`А настроение сегодня как — ничего не тревожит?`.
These combine a mood description with a negated anxiety/health screen. A bare
yes/no cannot unambiguously answer both. The coverage planner also maintained
its own mood phrasing instead of using the existing slot renderer.

Direct execution of the existing SDK replay imported an editable package from
another checkout when PYTHONPATH was absent. Local reproduction imported the
old main EngineState, which lacks `thread_last_statement`. Importing the current
checkout explicitly succeeded. A subprocess trap with a foreign SDK on PYTHONPATH
reproduces the same boundary independently of local installation layout.

All13 new cases failed before correction (12 mood variants +1 import boundary).
An initial bank reduction additionally failed2 existing canonical/depth tests.
Those assertions stay unchanged: retain the existing six entries and rotation,
replace the two ambiguous entries with single-need mood questions. Bank size
does not increase; the duplicate coverage mood bank is removed.

## Owners and correction

- Existing coverage chooses the domain/intent; existing `questions.slot_question`
  owns mood phrasing. No new scheduler, phrase bank, state writer or model call.
- One mood move asks mood; the unrelated negated screen is not appended.
  Safety and user-volunteered health evidence keep their existing owners.
- Replay binds imports to the checkout containing its file, even from another
  working directory/PYTHONPATH. Genuine model/readiness requirements remain.

[Actual before/after](before-after.json) captures canonical SDK speech and state.
Unknown/negative medication disposition is retained, next intent remains mood,
and the question is now `А какое у вас сегодня настроение?`.
The replay regression also verifies story→invite→two listening acknowledgments
→unfinished nutrition question, and explicit stop. This is not audio delivery.

## Verification / acceptance boundary

Focused single-need/variety/grounding/conversation tests121 PASS,9.44s;
full rich gate679 PASS,10.20s. Ruff and whitespace PASS. Exact source CI with
genuine LFS artifacts is recorded in current-task after publication.

No live generator is enabled; no model/provider choice changes. Existing SDK
delivery invariants, clinical/control/consent, canonical text and Core ownership
remain authoritative. Real warmth/prosody, audible interruption and target
latency/capacity still need accepted M5/server access, genuine STT/TTS and
CallActor/FreeSWITCH audio+trace. No source replay can complete that acceptance.
