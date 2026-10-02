# Listening exchange: reply ownership, rather than a repeated invitation

Owner heard no noticeable dialogue improvement. Base `030e262` on
`feature/voice-zoiper-m5` includes the peer Qwen voice changes. They change the
voice adapter, not the DialogueEngine's words. This is an offline defect
reproduction and candidate correction, not a diagnosis of the owner's recording.
Actual M5 SHA, providers, flags, audio and current call trace remain unknown here.

Published correction: `5abc23697b3994c705cc01359044d071da5ad46b` on m5.
GitHub [run36988690466](https://github.com/Belvist/imvera/actions/runs/36988690466)
passes all nine specialized jobs; full suite has2487 passes and the same eight
missing-model failures (three skips). This is source publication, not target
deployment or an audible-quality acceptance.

Followup preserves peer `2314092` clone voice and `d4be4f4` model revision fix;
the health revision is promoted after successful selected-provider warmup.
Registration/model mocks keep the original synth failure cases exercising their
actual boundary. Two added cases verify the base model's reported revision and
missing clone registration's actual Silero fallback. Local integrated suite:
2485 passes/eight inherited missing-model failures/nine skips; runtime239/239.
Peer deployment reports are not independent heard-quality evidence here.

## Reproduced decisions

1. Each substantive personal reply replaced an already consumed `open_hook`
   and reset `open_hook_used=False`. Topic age zero was treated as permission
   to start another invitation; it was not a listening budget.
2. `thread_followup` had `marks_question=False`. Its playback left the old
   opening wellness question delivered. The next answer was therefore bound
   to a question the person had not just heard.
3. Actual SDK mission understanding accepted activity evaluation
   `хорошо посидели` as a wellness answer. Plain ScenarioRunner did not invoke
   this provider, so its green narrative checks did not catch that false fill.
4. The new Qwen adapter could append Silero from sequence zero after already
   emitting Qwen PCM, and warmup could claim Qwen readiness using fallback
   audio. These failures were reproduced with controlled providers through the
   worker route, not with the owner's models or call.

## Existing owners and changed speech

Discourse keeps the original evidenced hook through the exchange and identifies
the accepted reply to the actual delivered invitation. Scheduler permits the
first invitation and one different continuation question, then resumes the real
unanswered wellness goal or the existing ladder. Clinical/safety/control paths
still preempt listening. This is a bounded caring check-in, not freeform chat.

The first grounded quotation is retained. After `Чай пили, разговаривали.`:

- Before: `Вы говорили: «чай пили, разговаривали». Я вас слушаю.
  Хотите рассказать чуть подробнее?`
- Candidate: `Как вам сейчас, когда вы об этом рассказываете?`

After a further reply, the still unanswered health question returns explicitly:
`Спасибо, что поделились. А как ваше самочувствие сегодня?`
No positive emotion, family relationship, improvement or health answer is
invented from the story. This is a flow correction; it does not demonstrate
Newo-level language, empathy, prosody or latency.

The listening questions have actual question IDs and delivery records, without
an artificial health goal. A `thread-{question_id}` timer starts after delivery,
including repair/backchannel playback. Stale timers cannot interrupt another
question. Silence and `Не помню` about a story do not discharge wellness.
Undelivered invitations refund the planned budget; duplicate reply IDs do not
advance it again. SDK understanding and the reducer reject bare story valence
as a health fill while keeping explicit volunteered health reports.

## Evidence and integration handoff

Run `PYTHONPATH=. python scripts/replay_story_dialogues.py` at both revisions
using the same Python environment. Call IDs, four input sequences, time and
copy rotation are fixed. The [paired JSON](listening-exchange-2026-10-02.json)
records exact SDK text, goal answer proposals, intents, wellness
status and source hashes. STT/TTS/audio and perceived warmth are `NOT_RUN`.
Normal positive check-in and clinical complaint replies are displayed alongside
the changed narratives, so unchanged cases remain visible.

Regression commands and final results are recorded at the top of
[current task](../current-task.md). New cases cover actual SDK delivery and
canonical text integrity, not only direct reducer scenarios. No old assertions
or missing-model checks are removed.

Qwen partial failure now ends the NDJSON stream with an error; the HTTP adapter
raises instead of repeating the phrase with Silero. Before-first-PCM fallback
remains the peer's declared behavior and records requested/actual engine with
call/generation/phrase identity. Warmup synthesizes directly with Qwen and waits
for successful producer completion, including errors after its sentinel. Cold
startup fallback reports actual Silero revision; it cannot prove Qwen ready.
This verifies mocked provider delivery truth, not real model quality.

For the agent on M5:

1. Preserve the peer voice work and pull the published m5 candidate; verify
   loaded bridge SHA and the actual TTS engine/revision of every replica.
2. Keep canonical text through TTS. Do not add a second composer, replace
   the engine's words, infer wellness from social evaluation or count a story
   as a completed clinical question. The no-generative-live-LLM order persists.
3. Feed playout completion/cancellation with the actual question ID. Deliver
   the existing SDK followup timer after audio completion; do not invent a
   `wellness` timer for a listening question with no clinical slot.
4. Capture one complete 7000 call with a personal story, continuation, explicit
   health answer and goodbye; collect audio and JSONL, including question IDs,
   canonical/TTS words and the source of actual PCM. Then test clinical
   interruption, refusal, repetition and silence with the same loaded source.
5. Follow the existing [production handoff](../production-dialogue-handoff.md)
   for runtime truth, model readiness, latency and rollback. Do not equate
   canonical text replay or mock PCM with heard warmth or production acceptance.

Competitors have not been executed for this correction. No comparative score
or human listening rating is assigned. The next acceptance gate is a recording
and trace on the actual M5 candidate, assessed by listeners.
