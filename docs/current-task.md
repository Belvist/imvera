# Current task — finish the frozen path (ADR-014)

**Outcome:** One production path, 100 consecutive full calls. **No fourth system.**

## Deployed now

- **SHA:** `95162a2` (pushed `feature/voice-zoiper-m5`)
- **GitHub CI:** run `34484342054` SUCCESS
- **Lab:** `make preflight-gates` + `make freeswitch-zoiper-voice-up` OK
- **runtime SHA verified:** `95162a2`
- Opening: «Здравствуйте. Это сервис Амвера. Даниил, Как вы себя чувствуете?»
- Live path: filter → `atomic_semantic_apply` → scheduler (ADR-016)
- Replay: `fs-1f6d3000` in `make test-live-replays`

## NEXT

Free live Zoiper call (not verbatim `fs-1f6d3000`) → forensic; do not claim live acceptance until call passes.
