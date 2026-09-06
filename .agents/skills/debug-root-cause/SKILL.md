---
name: debug-root-cause
description: Find root cause of bugs using runtime truth and evidence chain. Use for regressions, live call failures, and mysterious dialogue behavior.
---

# Debug Root Cause

## Anti-pattern (forbidden)

```text
не работает → regexp → ещё regexp → prompt fix → ещё fallback
```

## Required Chain

```text
SYMPTOM
  ↓
REAL FAILING ARTIFACT (log, recording, trace, test name)
  ↓
RUNTIME PATH (which code, which SHA, which endpoint)
  ↓
FIRST WRONG DECISION (exact branch / state transition)
  ↓
OWNER (which layer violated its contract)
  ↓
ROOT CAUSE (one sentence, falsifiable)
  ↓
REGRESSION (test that would have caught it)
  ↓
FIX (minimal)
  ↓
PROOF (command + live trace if applicable)
```

## Step 0: Runtime Truth

Before analysis, record:

```text
git SHA, branch, image SHA
active engine, STT/TTS/LLM endpoints
feature flags
call_id, turn_no, generation_id (if live)
```

If unknown → establish first. **Do not patch blind.**

## Evidence Priority

1. Call trace JSONL (turn-level state before/after)
2. Audio recording + STT transcript with confidence
3. `canonical_assistant_text` vs actual playback log
4. Unit test that reproduces minimal case
5. Code read (last resort without 1–4)

## Common VoiseUp Failure Classes

| Class | Check |
|-------|-------|
| Wrong owner | Did transport/renderer change State? |
| Stale generation | playback after barge-in without generation_id check |
| False slot close | «ага» closed wellness slot |
| Verdict leak | voiseup set GREEN locally |
| Provider mismatch | dev STT endpoint in prod container |
| Text ≠ speech | renderer output ≠ TTS input |

## Output

```text
ROOT CAUSE: ...
OWNER: ...
FIX: ...
REGRESSION TEST: ...
PROOF: ...
NOT VERIFIED: ...
```
