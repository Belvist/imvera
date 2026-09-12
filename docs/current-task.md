# Current task — known→skip ask + text soak (no TTS)

**Outcome:** Product pack asks only unknown steps; 100 text calls soak without TTS; warm MVP close; media-bridge restarted to load code.

## Plan (done)

1. `product/known.py` — facts already known → skip step
2. Planner uses known before asking
3. Spoken close: «Спасибо… На сегодня всё. Берегите себя.»
4. `scripts/dialogue_text_soak.py` + `make dialogue-text-soak`
5. Restart host `freeswitch_media_bridge` so CallActor picks up engine

## CHANGED

- `packages/dialogue_engine/product/known.py` (new)
- `packages/dialogue_engine/product/planner.py`, `issue_plans.py`, `__init__.py`
- `packages/dialogue_engine/questions.py` (summary close)
- `scripts/dialogue_text_soak.py`, `scripts/demo_dialogue_product_pack.py`
- `tests/test_product_dialogue_pack.py`, `test_issue_first_flows.py`, `test_dialogue_must_hangup.py`
- `Makefile` (`dialogue-text-soak`)

## VERIFIED

```bash
python3 scripts/dialogue_text_soak.py --n 100
# text_soak: 100/100 passed
```

## NOT VERIFIED

- Live Zoiper phone calls with this build
- ADR-014 100 consecutive SIP/RTP calls

## NEXT GATE

10 Zoiper full calls on pack corpus after bridge restart.
