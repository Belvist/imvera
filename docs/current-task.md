# Current task — Grandmother call validation (Stage B/C)

## Primary assignment

Tomorrow: live Zoiper call to **7000** — validate full wellness dialogue on real audio.  
Policy matrix: `tests/test_wellness_call_scenarios.py` (Stage B audit from `docs/verification/dialogue-current.md`, base `e0e86b0`).  
Architecture: [ADR-009](adr/009-llm-understanding-state-policy.md).

## Branch / SHA

| Field | Value |
|-------|-------|
| Branch | `feature/voice-zoiper-m5` |
| Last pushed | `e0e86b042067f1860d26f681152c036795c501a4` (Stage 1) |
| Working tree | `69edab5` + uncommitted — Stage 2 + wellness matrix |

## Tomorrow checklist — dial 7000 (Zoiper)

### Before the call

```bash
make up                    # or stack already running
make dialogue-smoke        # gateway + STT/TTS/LLM health + policy gates
make zoiper-info           # SIP credentials / extension
```

Runtime truth to note: `git rev-parse HEAD`, active profile (`config/voice-m5.yaml`), STT `:9101`, TTS `:9102`, LLM `:9103`, gateway `:9200`.

### Call script (say in order)

| Step | Vera asks (approx.) | You say | Policy intent to expect |
|------|---------------------|---------|-------------------------|
| 0 | Opening / identity / consent / can talk | «Да» (if prompted) | `opening_wellness` → `DAILY_CHECK` |
| 1 | Как себя чувствуете? | **Pick one:** «хорошо» / «нормально» / «не очень» / «плохо» | `check_mood`, wellness slot FILLED |
| 2 | Настроение? | «хорошее» (or «плохое» if step 1 was negative) | `check_sleep` |
| 3 | Сон? | «спал нормально» (or «спала плохо») | `check_plans` |
| 4 | Планы? | «дома посижу» / «дома» | `summary` |
| 5 | (optional) | «до свидания» → «да» | `goodbye_confirm` → `goodbye_final` |

**Extra probes (separate short calls or after step 1):**

| Probe | You say | Expect |
|-------|---------|--------|
| Mixed answer + side question | «Чувствую себя хорошо. А зачем вы спрашиваете?» | wellness FILLED + `explain_vera` (mentions Вера) |
| Complaint | «Голова болит с утра» | `reflect_report`, mirrors «болит», **no** «отлично», **no** `?` |
| Backchannel | «ага» (while question pending) | slot stays OPEN, `wait_for_continuation` |

### Trace events to expect (`.run/traces/<call_id>.jsonl`)

Minimum per turn (from `packages/contracts/runtime.py`):

```text
call.started
media.ready
speech.started → speech.ended
stt.final          (payload.text ≈ what you said)
interpretation.ready
renderer.phrase_ready
playback.completed   (sent_samples > 0)
call.ended
```

Optional / timing: `stage.timing`, `playback.interrupted` (barge-in), `persistence.committed`.

Inspect: `curl -s http://127.0.0.1:9200/calls/<call_id>/trace | jq '.events[].type'`

### Pass criteria (live)

- [ ] Vera speaks greeting before wellness question
- [ ] STT `stt.final` text matches utterance (± minor ASR drift)
- [ ] No 3+ identical wellness questions in one call
- [ ] Complaint mirrored without praise
- [ ] All four slots filled OR explicit UNRESOLVED close (not infinite loop)
- [ ] Goodbye terminates (`call.ended`, no repeat goodbye spam)

## Stage B scenario matrix — VERIFIED (policy, local)

```bash
python3 -m pytest tests/test_wellness_call_scenarios.py -q
# 12 passed

python3 -m pytest tests/ -q
# 216 passed, 2 skipped
```

**Coverage (`tests/test_wellness_call_scenarios.py`):**

- Parametrized wellness mood: хорошо, нормально, не очень, плохо
- Full slot completion → goodbye (×4 mood variants)
- Mixed utterance + side question
- Complaint at wellness + mid-call
- Rule-baseline short answers (хорошо/нормально/плохо)

**Audit sources reviewed:** `tests/test_e0_dialogue_integration_gaps_audit.py`, `tests/test_dialogue_acceptance_gaps.py`, `docs/verification/dialogue-current.md`.

## NOT VERIFIED (live call — tomorrow)

| Item | Why |
|------|-----|
| STT accuracy | Policy tests inject text; real ASR on elderly phone speech not measured |
| Echo / full-duplex | No SIP lab run on current SHA in this session |
| End-to-end latency (p50/p95) | No `stage.timing` baseline doc; live not timed |
| Real LLM semantic JSON | Matrix uses fixture `SemanticPayload`, not HttpLLM output |
| TTS audibility / barge-in on phone | Downlink energy not checked on Zoiper |
| PG `action_outbox` wire | metadata-only in transition_store |

## NEXT GATE

1. **Tomorrow:** one full happy-path call + one complaint call on 7000; save trace JSONL + note SHA.
2. `make test-dialogue-live` with MLX on `:9103` for real «голова болит» LLM gate.
3. Add `tests/test_wellness_call_scenarios.py` to `make test-dialogue-gates` (optional).

## Parallel track (SIP uplink — uncommitted, separate)

`scripts/voice_sip_e2e.py`, `services/asterisk_app/main.py`, `services/voice_gateway/main.py`, `tests/test_voice_stack.py`
