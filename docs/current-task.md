# Current task — Grandmother call validation (Stage B/C)

## Primary assignment

Live Zoiper **7000** — wellness dialogue on real audio.  
**Incident 2026-09-08 00:08 (`sip-31365dee13`):** echo self-barge-in — greeting cut ~187ms; STT `Сд.`/`Сейчас`; no `playback.completed`. Cause: `8accf9a` R1 unmuted uplink during TTS. **Fix (working tree):** half-duplex mute + echo prefix discard; stack restarted. **Live redial NOT VERIFIED.**  
Policy matrix: `tests/test_wellness_call_scenarios.py`.  
**1k corpus + load harness:** `make test-corpus-1k` / `scripts/run_dialogue_corpus.py` (Session/Planner scale proof; **NOT** live SIP×1000).  
Architecture: [ADR-009](adr/009-llm-understanding-state-policy.md).

## Branch / SHA — truth table

| Field | Value |
|-------|-------|
| Branch | `fix/dialogue-stage-b` (local) |
| **HEAD (before this corpus commit)** | `fd2170b` — wellness scenario matrix |
| Telephony gate commit | `69edab5` — macOS say lab TTS + gateway `/health/ready` (**PASSED**) |
| Prior dialogue stage | `e0e86b0` — QuestionLedger / answer-wait |
| Included in corpus commit | Stage B dialogue (empathy / topic-refuse / multi-phrase / `release_question_attempt`) + `tests/corpus/` + runner |
| Last pushed (historical) | `e0e86b0` — do not assume remote has Stage B |
| Push policy | **Do not push** unless user asks |

### Dialogue behavior under corpus proof

- **«не очень» / «плохо»** → wellness FILLED + `reflect_report` empathy
- **«хорошо» / «нормально»** → wellness FILLED + `check_mood`
- Backchannel «ага»/«алло»/«угу» → never fills pending slot
- Topic refuse, pause, stop-call phrases
- **CallActor:** sequential multi-phrase TTS; reservation release on TTS fail (mock TTS load)

## Reproduce 1k proof (tomorrow / Daniil)

```bash
cd /Users/earflow/Downloads/voiseup
git rev-parse HEAD
make test-corpus-1k
# or:
python3 scripts/run_dialogue_corpus.py --workers 4 --minimum 1000
python3 -m pytest tests/corpus/ -q
python3 -m pytest tests/ -q   # full suite
```

Expect: **1000/1000** corpus pass + CallActor load green.  
Label: **CallSession dialogue scale** — not Zoiper/SIP×1000.

## Tomorrow checklist — dial 7000 (Zoiper)

### Before the call

```bash
cd /Users/earflow/Downloads/voiseup
git rev-parse HEAD
git status -sb
make voice-up
make zoiper-info
curl -s http://127.0.0.1:9200/health/ready
curl -s http://127.0.0.1:9101/health/ready
curl -s http://127.0.0.1:9102/health/ready
curl -s http://127.0.0.1:9103/health/ready
make dialogue-smoke
make test-corpus-1k          # scale proof (text Session path)
```

Runtime truth: `git rev-parse HEAD` + `git status -sb`, profile `config/voice-m5.yaml`, STT `:9101`, TTS `:9102`, LLM `:9103`, gateway `:9200`.

### Call script (say in order)

| Step | Vera asks (approx.) | You say | Expect |
|------|---------------------|---------|--------|
| 0 | Opening / identity / consent / can talk | «Да» (if prompted) | `opening_wellness` → `DAILY_CHECK` |
| 1a | Как себя чувствуете? | **«хорошо»** or **«нормально»** | wellness FILLED → mood (`check_mood`) |
| 1b | (alt) Как себя чувствуете? | **«не очень»** or **«плохо»** | wellness FILLED → **`reflect_report`** |
| 2 | Настроение? | «хорошее» (or «плохое» if 1b) | mood FILLED → sleep |
| 3 | Сон? | «спал нормально» / «спала плохо» | sleep FILLED → plans |
| 4 | Планы? | «дома посижу» / «дома» | plans FILLED → summary |
| 5 | (optional) | «до свидания» → «да» | `goodbye_confirm` → `goodbye_final` |

**Extra probes:** mixed side question; complaint «голова болит»; backchannel «ага»; soft stop «закончим разговор».

### Where traces go

```text
.run/traces/<call_id>.jsonl
curl -s http://127.0.0.1:9200/calls/<call_id>/trace | jq '.events[].type'
```

### Pass criteria (live)

- [ ] Greeting before wellness question
- [ ] STT ≈ utterance
- [ ] «хорошо» advances; «не очень»/«плохо» empathy then advance
- [ ] No 3+ identical wellness questions
- [ ] Complaint mirrored without praise
- [ ] Four slots filled OR explicit UNRESOLVED close
- [ ] Goodbye terminates

## Local verification (this session)

```bash
python3 scripts/run_dialogue_corpus.py --workers 4 --minimum 1000
# → 1000 passed / 0 failed, ~4200–4500 scenarios/sec (ProcessPool)

python3 -m pytest tests/corpus/ -q
# → corpus gate + CallActor load

python3 -m pytest tests/ -q --ignore=tests/test_llm_live_dialogue.py
# → 220 passed, 2 skipped

make dialogue-smoke   # gateway/providers ready; live LLM gates OK when stack up
```

## NOT VERIFIED

| Item | Why |
|------|-----|
| **SIP / Zoiper ×1000** | Not feasible tonight; corpus is Session/Planner text path |
| Live STT elderly speech | Corpus injects text |
| Live TTS audibility / barge-in on softphone | CallActor load uses **mock** TTS |
| End-to-end latency p50/p95 | No timed live baseline |
| Real LLM for all 1000 cases | Rule interpreter; semantic matrix is separate |
| Remote/main parity | Branch local; do not push unless asked |

## NEXT GATE

1. **Tomorrow:** Zoiper 7000 — one happy-path («хорошо») + one empathy («не очень»/«плохо»); save `.run/traces/<call_id>.jsonl` + SHA.
2. Re-run `make test-corpus-1k` after any dialogue change (regression proof).
3. Optional: `make test-dialogue-live` for real LLM complaint gate.
