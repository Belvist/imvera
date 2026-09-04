# Vera Golden Path

Independent conversation brain for IMVERA — **not** part of `telephony/conversation_system/`.

## Why Golden Path

Live calls showed LLM phrasing can work while legacy FSM/agenda (~8k LOC) still produces poor conversations (premature slot close, ignored symptoms, weak repair). Golden Path isolates:

**State → Analyzer → Planner → LLM → Validator**

with JSONL trace per turn and an explicit **owner gate** before telephony integration.

## Stages

| Stage | Scope | Gate |
|-------|--------|------|
| **A — Text lab** | `golden_path/` engine, `run_vera_text_lab.py`, 20 automated scenarios | **Owner** 10+ min text chat + trace review |
| **B — Audio lab skeleton** | `run_vera_audio_lab.py`, `stt_protocol.py` stubs (Qwen3/GigaAM `NotImplementedError`) | `OWNER_ACCEPTED` in `GOLDEN_PATH_STATUS.md` |
| **C — Realtime** (spec only) | PCM → Silero VAD → Smart Turn (8→16 kHz resample) → streaming STT → Golden Engine → streaming TTS; barge-in p95 &lt;250 ms; `actual_heard` only | Owner listens |
| **D — Phone** (spec only) | `VERA_GOLDEN_PATH=1` thin hook in `telephony/core/orchestrator.py` **beside** legacy, not inside `conversation_system` | 10 live Zoiper calls |

Legacy Lua/file-polling path remains available as `LEGACY_FALLBACK=1` only — not used for Golden acceptance.

## Architecture (Stage A)

```
User text → GoldenPathEngine.handle_turn()
  → Analyzer (classify + facts, no phrasing)
  → Planner (sole action choice)
  → LLM (MOSS_LLM_URL, OpenAI protocol)
  → Validator (tone, slot rules, safety fallback)
  → Trace JSONL
```

### Modules (`golden_path/`)

| Module | Role |
|--------|------|
| `state.py` | `ConversationState`: facts, slots, turns, question budget |
| `slots.py` | `wellness/mood/sleep/plans` + `OPEN/ANSWERED/DECLINED` |
| `analyzer.py` | `DIRECT_USER_QUESTION`, `CORRECTION`, `REPAIR`, `TOPIC_REFUSAL`, `NORMAL_RESPONSE`, `SAFETY` |
| `planner.py` | `ANSWER_USER`, `ACK_ONLY`, `ASK_SLOT`, `REPAIR`, `HANDLE_CORRECTION`, `HANDLE_REFUSAL`, `SAFETY`, `CLOSE`, `GREET` |
| `llm.py` | Thin HTTP client — **no** `conversation_system` imports |
| `validator.py` | Banned phrases, re-ask guard, safety deterministic fallback |
| `engine.py` | `begin_session` / `handle_turn` / `end_session` |
| `trace.py` | JSONL per turn |
| `prompts.py` | Tone contract + `ACTION:` prompt format |
| `status.py` | `WAITING_OWNER_ACCEPTANCE` / `OWNER_ACCEPTED` |

### Planner rules

- Slots advance: wellness → mood → sleep → plans.
- `ANSWERED` / `DECLINED` slots are never re-asked.
- User question → `ANSWER_USER` before next `ASK_SLOT`.
- Correction → update facts + `HANDLE_CORRECTION`.
- Question budget: ≤1 question per 2 assistant turns (tracked in state).
- No phrase pools except safety fallback in `validator.py`.

### LLM prompt shape

```
ACTION: ASK_SLOT(sleep)
ALREADY ANSWERED: wellness, mood
DO NOT ASK: wellness, mood
USER MESSAGE: ...
STATE: {"session_id":"...","facts":{...},...}
```

Env: `MOSS_LLM_URL` (default `http://127.0.0.1:9500`), `MOSS_LLM_PROTOCOL=openai`. See also `docs/HOST_LLM_METAL.md`.

## Trace JSONL (required fields per turn)

Each line in `golden_path/traces/<session_id>.jsonl`:

- `user_text`
- `state_before`
- `analysis`
- `planner_action`
- `required_slot`
- `exact_llm_prompt`
- `raw_llm_output`
- `final_assistant_text`
- `state_after`

Plus metadata: `ts`, `session_id`, `turn_no`, `validator_result`.

## Commands

```bash
# Interactive text lab (real LLM)
python3 scripts/run_vera_text_lab.py

# Automated scenarios (MockLLM if LLM down)
python3 scripts/run_golden_path_scenarios.py --strict

# Stage B skeleton (blocked until owner accepts A)
python3 scripts/run_vera_audio_lab.py

# Unit tests
python3 -m unittest discover -s golden_path/tests -p "test_*.py"
```

## Definition of Done (Stage A)

**Only** owner acceptance counts:

1. `STATUS=OWNER_ACCEPTED` in `docs/GOLDEN_PATH_STATUS.md` after 10+ min `run_vera_text_lab.py`.
2. Owner reviewed traces for planner/LLM failures.

Automated PASS does **not** mean production-ready dialogue.

## Legacy freeze

Until `OWNER_ACCEPTED`:

- **Do not** patch `telephony/conversation_system/` (FSM, agenda, pools, observer policy).
- Golden Path is the **quality canon** for new conversation work.
- `make test-fast` / `synthetic_caller` remain legacy regression only.

## Future phone hook (Stage D — not implemented)

```python
# telephony/core/orchestrator.py (future)
if os.environ.get("VERA_GOLDEN_PATH") == "1":
    from golden_path.integration import handle_phone_turn  # thin adapter
else:
    plan_turn_for_call(...)  # legacy unchanged
```

## Rationale (Vapi / Newo)

- Separate **planner** from **phrasing** (planner picks action; LLM only speaks).
- Trace-first debugging: one JSON line explains a bad turn.
- Continuous audio and barge-in belong in Stage C/D, not in legacy FSM patches.

## Feature flags

| Env | Meaning |
|-----|---------|
| — | Stage A text lab only |
| `OWNER_ACCEPTED=true` | Unblocks Stage B skeleton work |
| `VERA_GOLDEN_PATH=1` | Stage D phone routing (future) |
| `LEGACY_FALLBACK=1` | Emergency legacy Lua path (future) |

Current status: see [`GOLDEN_PATH_STATUS.md`](GOLDEN_PATH_STATUS.md).
