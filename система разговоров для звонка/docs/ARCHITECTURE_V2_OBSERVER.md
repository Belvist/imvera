# Architecture v2 — Observer Layer (Phase 1)

## Target flow

```
Caller audio → STT → TurnAnalyzer → Observer.observe_turn()
                                        ↓
                              ObserverPatch (facts, corrections,
                              unanswered_user_questions, next_directive)
                                        ↓
                    IntentResolver (priority stack) → FSM (guard)
                                        ↓
              ReplyComposer (pools) + CallMirror.reply_stream (LLM when allow_llm)
```

## Priority stack (resolver)

1. Safety (SafetyBridge → safety_events first)
2. Explicit user **QUESTION** → `E_SIDE_QUESTION` (never `E_UNHANDLED` in agenda states)
3. **Correction / contradiction** → `E_CORRECTION`
4. **Repair** → `E_REPAIR`
5. **Agenda** probes / wellness paths

## Observer v1 (deterministic)

- `ConversationState`: facts with status, `pending_question`, `unanswered_user_questions`, `corrections`, `next_directive`
- `Observer.observe_turn()` — no LLM; sets `next_directive` for main agent
- Wired in `runtime/session.py` **after** analyze, **before** resolver

## PendingQuestion

| Type | Short «да» |
|------|------------|
| YES_NO | valid |
| CHOICE | **invalid** → `E_CORRECTION`, re-ask same probe |
| OPEN | valid if substantive |

## LLM path (controlled)

- `allow_llm=True` for: side question, repair, correction ack, narrative
- **Not** for: safety, consent, record_notify (scripted pools)
- Orchestrator: `turn_plan_to_legacy` + `CallMirror.reply_stream` (3s timeout, pool fallback)
- Facade sets `meta.allow_llm`, `meta.intent` / `next_directive`

## Phase 2 — CHOICE PendingQuestion (2026-09-04)

- `infer_pending_from_prompt()` detects binary «X или Y» probes (intensity,
  timing, symptom depth) and sets `PendingQuestionType.CHOICE` with extracted
  choice labels.
- Bare «да»/«нет» on CHOICE → `validate_pending_answer` → `choice_needs_pick`
  → resolver `E_CORRECTION` (no agenda advance, no `record_notify`).
- Observer upgrades stale OPEN pending to CHOICE when the last question is
  re-parsed; composer re-asks `last_question` on `pending_invalid:choice_needs_pick`.
- `_SYMPTOM_PROBE_SHORT_WORDS` no longer treats bare «да»/«нет» as probe closure
  (YES_NO probes still accept them via `PendingQuestionType.YES_NO`).

## Phase 3 — LLM Observer + Supervisor (2026-09-04)

### LLM Observer (optional, fail-closed)

- `observer/llm_enricher.py` — `LlmObserverEnricher` calls LLM with **2.5s timeout**,
  structured JSON schema (`facts`, `corrections`, `contradictions`, `next_directive_hint`).
- `Observer.observe_turn()` runs **deterministic v1 first**, then merges LLM hints when
  a client is wired (`Observer.set_llm`, orchestrator via `conversation_v2_bridge`).
- On timeout / invalid JSON / missing LLM → **deterministic patch only** (no fake data).
- Env gate: `MOSS_OBSERVER_LLM=0` disables LLM path; default on when LLM is wired.
- **SafetyEngine unchanged** — safety stays fully deterministic.

### Supervisor

- `observer/supervisor.py` — post-observer invariant checks:
  - Rejects promise phrases in directives (`позвоню/вызову/отправлю…`)
  - Blocks agenda-skip hints when `pending_invalid` (CHOICE bare «да»)
  - Downgrades hallucinated LLM-only corrections/contradictions
- Structured log: `observer_supervisor_override call_id=… reasons=…`

### Explicit PendingQuestion at composition

- `apply_pending_to_memory()` in `domain/pending_question.py`
- **Phase 4:** only `commit_turn()` sets pending from actual spoken text (not `compose`/`plan_turn`)

### Multi-option CHOICE

- `infer_pending_from_prompt()` parses comma/or lists:
  «тяжесть, слабость или что-то другое» → `CHOICE` with ≥3 options
- Bare «да»/«нет» on CHOICE → still `choice_needs_pick` → `E_CORRECTION`

## Phase 4 — Spoken truth + corrections + non-blocking observer (2026-09-04)

### Single source of truth (spoken text)

- `commit_turn(spoken_text)` updates `last_question`, `pending_question`, and memory
  from **actual TTS/LLM output** — never from pre-generation `composed.text`.
- `plan_turn` / `ReplyComposer.compose()` no longer call `apply_pending_to_memory`.
- Flow: plan → generate/guards → actual spoken → `commit_turn` → `infer_pending_from_prompt`.

### Correction-aware symptom extraction

- `extract_correction_focus()` in `turn/analyzer.py` — «не голова … спина болит»
  yields superseded `голова` + active `спина`.
- Observer uses correction-aware logic (not naive first-match `extract_symptom_focus`).

### Unanswered question lifecycle

- `ConversationMemory.mark_question_answered()` after `ANSWER_SIDE` commit.
- Observer skips re-adding questions in `answered_user_questions`.

### Repair + ACK speech acts

- Extended `_REPAIR_RE` («что вы спросили», «повторите вопрос», …) → `SpeechAct.REPAIR`.
- `SpeechAct.ACK` for «понятно/ясно/ладно/хорошо» — exempt from `_JUNK_RE`.
- Repair composer path repeats `last_question`, not generic intro.

### LLM for normal conversation

- FSM/resolver: `ASK_TOPIC`, `SYMPTOM_FOLLOWUP`, side-resume, acks → `allow_llm=True`.
- `ResponseGoal` carries `must_do` / `forbidden` / `next_topic` constraints (not canned text).
- Scripted-only retained: safety, consent, record_notify, terminal goodbye, clarify ladder.

### Non-blocking Observer LLM

- Default `MOSS_OBSERVER_LLM_BLOCKING=0` — deterministic observer sync; LLM enricher
  does not block the turn hot path unless explicitly enabled.

### Build identity + idempotent end_call

- `/health`: `build_sha`, `build_time`, `conversation_version`, `protocol_version`.
- Call start log: `build_sha`, `scenario`, `pid`.
- `voice_runtime/agent_http.end_call` treats HTTP 404 as idempotent success.

## Phase 5 — Audit P0 fixes (2026-09-04)

Owner audit (telephony 2.zip review): stream truncation, goal arbitration, side-question
resume, slot-exact LLM directives, tone/prompts, health LLM readiness.

### P0 fixes

1. **Stream truncation** — `reply_segments()` no longer `break` after first comma segment;
   full LLM stream yields all TTS segments.
2. **Goal arbitration** — `RECORD_NOTIFY` / `CLOSING` / `SAFETY_*` / `CRITICAL_PATH` FSM
   scripted goals win over resolver `allow_llm`; `E_WELLNESS_GOOD` → `ASK_TOPIC` not `WRAP_UP`.
3. **Unconfirmed promises** — pools/guards: only «записала/сохраню для близких», no
   «уже передали/оповестила».
4. **REPAIR lifecycle** — repair acts skip `unanswered_user_questions`; stale repair
   directive cleared after repeat.
5. **Correction atomic** — directive built after semantic patch (`effective_symptom`).
6. **Side-question FSM** — `InterruptionFrame` restores `return_phase` + slot index;
   no `apply_path_after_wellness()` reset; `SIDE_ANSWER` ACK → `E_SPEECH` resume.
7. **Exact `required_slot`** — `GOOD_PROBE_SUBTOPICS` per-slot `must_do`; agenda context
   (`current_slot`, `covered_slots`, `forbidden_slots`) in `compose_turn_directive()`.
8. **Intent merge** — composed `TurnDirective` (observer + goal + agenda), not OR.
9. **Dedupe + remember_question** — `variety.remember_question()` in `commit_turn`;
   slot mismatch fallback in `resolve_spoken_reply`.
10. **semantic_close** — `_good_probe_answered` requires slot relevance, not arbitrary 2-word ack.
11. **Prompts** — removed faux-family / command tone; 0–1 optional questions, 5–8 s natural.
12. **Health** — `/health`: `conversation_mode`, `conversation_degraded`, `require_llm`
    (`MOSS_REQUIRE_LLM=1` gates `ok` on LLM availability).
13. **Harness** — `voice-lab/real_llm_conversation_eval.py` (5 scenarios, full path).

### Agenda sync invariant

FSM actions that call `mark_question_asked()` must append `agenda.sync_to_memory()` so
`plan_turn` does not overwrite `question_open` from stale memory.

### CLARIFY wellness branch

`CLARIFY` + `E_WELLNESS_GOOD|BAD|CRITICAL` → same transitions as `LISTEN` (fixes
`greeting_played=True` empty-first-turn path).

## Phase 6 — QuestionLedger + heard lifecycle (2026-09-04)

### P0

1. **QuestionLedger** (`ledger/question_ledger.py`) — PLANNED→ASKED→HEARD→ANSWERED;
   CANCELLED on barge-in before heard; no re-ask of ANSWERED slots.
2. **TurnDirective** — `required_slot`, `required_action`, facts, tone; merged via
   `compose_turn_directive()` (not OR).
3. **Semantic validator** — `resolve_spoken_reply()` slot mismatch → one regenerate
   or deterministic slot fallback.
4. **InterruptionFrame** — `return_question_id` + slot index; SIDE_ANSWER resumes
   good path without resetting probe index.
5. **Voice Gateway scaffold** — `voice_runtime/voice_gateway/` + `docs/VOICE_GATEWAY.md`.
6. **Lua** — `for i=1,6` replaced with max duration / idle guards; conditional ack
   only after ~0.8 s without first segment.
7. **MOSS_LOCAL_ONLY** — `enforce_local_only()` fail-fast on external cloud providers;
   localhost OpenAI-compatible URLs allowed.
8. **Heard ledger** — `mark_segment_played()` on seg-file write; `on_generation_cancelled()`.

### P1 foundation

- `FactLedger`, `EventLog`, `ActionSupervisor` scaffolds in `ledger/`.

## Verification

```bash
make test-fast
python3 voice-lab/adversarial_dialogue_eval.py --strict
python3 voice-lab/dialog_quality.py --strict
python3 voice-lab/real_llm_conversation_eval.py --strict
python3 -m unittest telephony.tests.test_observer_phase4
python3 -m unittest telephony.tests.test_observer_phase5
python3 -m unittest telephony.tests.test_observer_phase6
```
