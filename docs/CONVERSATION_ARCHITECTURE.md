# Conversation Architecture — Ownership Contracts

Golden Path (`golden_path/`) is the canonical Stage A conversation brain. Each layer has a single responsibility and a strict boundary. Cross-layer leaks (analyzer choosing questions, LLM choosing agenda, validator rewriting planner decisions) are forbidden.

## Layer contracts

| Layer | Owns | Must NOT |
|-------|------|----------|
| **Analyzer** | **WHAT HAPPENED** — classify the user turn (`AnalysisKind`), extract facts (symptom, answered slot, safety, wait/fatigue). Token-boundary semantics; explicit topic evidence beats pending-slot polarity. | Choose assistant phrasing, pick the next question, mutate slot status, call LLM. |
| **State Reducer** | **WHAT IS TRUE NOW** — apply analysis to `ConversationState` *before* planning: slot `ANSWERED`/`DECLINED`, facts, safety/repair/wait/fatigue flags, corrections log. | Choose planner actions, generate text, validate tone. |
| **Planner** | **WHAT TO DO NEXT** — sole owner of `PlannerAction` (greet, ask slot, answer user, repair, safety, close). Reads reduced state only. | Parse raw user text for slot semantics (delegates to analyzer facts), call LLM, change validator rules. |
| **LLM** | **HOW TO SAY IT** — phrase renderer only: strict `ACTION` + `SEMANTIC RESPONSE` content plan from planner; Qwen3-4B non-thinking; short token budget. | Pick agenda, advance slots, override planner action, import `conversation_system`. |
| **Validator** | **MAY THIS BE SAID** — post-LLM checks (banned phrases, promises, re-ask blocked slots). Typed fallbacks per action; one LLM regenerate then fallback. | Change `PlannerAction`, mutate slot status, re-run analyzer. |
| **Tools** | **EXECUTE REAL ACTION** — durable side effects (incidents, family notify, schedule) with idempotency and audit. Not in Stage A text lab. | Participate in turn classification or phrasing. |
| **Realtime** | **DELIVER AUDIO** — RTP/PCM, VAD, STT ingest, TTS playback, barge-in timing. Feeds text to/from Golden Path engine. | Own dialogue policy or duplicate planner. |

## Turn pipeline (Stage A)

```
User text
  → Analyzer.analyze_turn(text, state)
  → State.reduce_user_turn(...)     # state_after_user
  → Planner.plan_turn(state, analysis)
  → LLM.generate(action, ...)
  → Validator.validate_reply(...)
  → Trace JSONL + record turns
```

**Ordering invariant:** user reduction completes before `plan_turn()`. Traces must include `state_after_user` so reviewers can prove slot closure happened pre-plan.

## Semantic priority (Analyzer)

1. Explicit topic lexical evidence (mood/sleep/plans/wellness stems on token boundaries)
2. Pending-slot contextual answer (generic polarity: «нормально», «хорошо», «плохо»)
3. Generic polarity alone never assigns a global slot without `pending_slot`

Symptom mentions in long narratives do not auto-close wellness unless wellness topic is explicit.

## Forbidden patterns

- Analyzer picks the next question or sets `pending_slot`
- LLM picks agenda or slot order (only follows `ACTION:` from planner)
- Validator changes `PlannerAction` or re-plans
- Second conversation controller alongside `GoldenPathEngine`
- `golden_path/` imports from `telephony.conversation_system`, `telephony.core.dialogue`, or legacy dialogue modules
- Masking LLM failures with generic ACK fallbacks in the text lab path (`Услышала вас, спасибо.` on timeout/503)

## Enforcement

- Automated gate: `make verify-golden-architecture` (forbidden imports + contract file presence)
- Review archive gate: `make package-review` (zip → unpack → same tests as workspace)
- LLM readiness: `make verify-llm-readiness` (requires canonical `/health` + protocol probe on `:9500`)
- Stage A default runtime: `scripts/run_llm_host.sh` → `stage_a_llm_gateway.py` (canonical `/health`) → llama-server internal OpenAI API on `:9501`
- **Runtime policy:** Stage A text lab and Golden Path use **host gateway `:9500` only**. Docker service `mossvoice-answers` must **not** bind `:9500` concurrently (OpenAI `/v1/chat/completions` vs legacy `/chat` conflict). Use `run_llm_host.sh` for Stage A; keep container LLM on a different port or stopped during text-lab work.
- Manual owner gate: `docs/GOLDEN_PATH_STATUS.md` → `OWNER_ACCEPTED` before telephony cutover

## Related docs

- [`docs/GOLDEN_PATH.md`](GOLDEN_PATH.md) — Stage A–D gates and trace schema
- [`docs/HOST_LLM_METAL.md`](HOST_LLM_METAL.md) — local LLM runtime on :9500
