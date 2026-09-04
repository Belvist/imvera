# Vera Golden Path — Status

STATUS=WAITING_OWNER_ACCEPTANCE

PRE_OWNER_STATUS=P0_FIXED_AWAITING_OWNER_TEXT_TEST

P0 fixes (2026-09-04, owner audit):

1. **CLOSE lifecycle** — any `PlannerAction.CLOSE` sets `closing=True` and `_ended=True`; further `handle_turn` raises `RuntimeError`.
2. **Unconfirmed action claims removed** — `SAFETY_FALLBACK` and `WHY_CALLING` no longer promise «записала / близкие увидят / передать близким»; `spoken_quality` + validator catch regressions.
3. **Phrase-quality correction fixture** — prior symptom `head`/`leg`/`head` (not pre-baked `knee` for pressure case); bench runs `analyze_turn` + `reduce_user_turn` before correction fallback.

Automated gate (post-P0, local):

- `python3 -m unittest discover -s golden_path/tests` — **81 OK**
- Re-run `generate_phrase_quality_review.py` + `run_wave2_integration.py --strict` before owner session (prior 50/50 claim was inflated by fixture bug)

Automated FINAL spoken gate (pre-P0 claims — do not trust without re-run):

- `run_wave2_integration.py --strict` — was **10/10** planner + **10/10** spoken FINAL
- `generate_phrase_quality_review.py` — claimed **50/50**; correction_3 fixture was wrong

## Wave 2 (Planner + dialogue behaviour)

WAVE_2_STATUS=READY_FOR_REVIEW

Wave 2 scope: Text Golden Path only (`golden_path/`). Legacy `conversation_system` untouched.

**Phrase renderer:** Qwen3-4B = renderer for conversational ASK_SLOT/ACK/ANSWER_USER only.

Verified in this session (unit tests, no live LLM required for control-flow regressions):

- `golden_path/tests/test_spoken_quality.py` — known BAD finals + validator
- `golden_path/tests/test_wave2_spoken_regressions.py` — Wave 2 control turns FINAL

## Realtime streaming (Wave RT-1, 2026-09-04)

STREAMING_STATUS=STREAMING_INGRESS_PROVEN

Canonical plan: [`docs/STREAMING_HOT_PATH.md`](STREAMING_HOT_PATH.md).

- `golden_path/realtime_adapter.py` — thin `RealtimeTurn` → `GoldenPathEngine` (not wired to phone yet)
- `VERA_GOLDEN_PATH=0` default; phone remains legacy until RT-2 gate
- Proof: `python3 scripts/prove_streaming_ingress.py` → exit 0

## Owner gate (Stage A)

Automated structural pass (49/50) does **not** replace spoken-quality review.

### To accept Stage A

1. `make golden-dev-up`
2. `python3 scripts/generate_phrase_quality_review.py` — review all FINAL OUTPUTs
3. `python3 scripts/run_wave2_integration.py --strict` — 10/10 actions + spoken PASS
4. `python3 scripts/run_vera_text_lab.py` — 10+ minutes live dialogue
5. Set `STATUS=OWNER_ACCEPTED` if acceptable

### Notes

- (owner fills after text lab session)
