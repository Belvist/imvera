# Current task — finish the frozen path (ADR-014)

**Outcome:** One production path, 100 consecutive full calls. **No fourth system.**

## Live-path simplification (this change)

- **Goal:** Legacy probe/topic must not own RichUserTurn before `atomic_semantic_apply`.
- **Replay:** `fs-1f6d3000` in live corpus + product invariants.
- **ADR:** `docs/adr/016-live-rich-turn-path.md`

## Gates (local)

- `make test-semantic-kernel test-dialogue-rich test-dialogue-topic test-dialogue-runtime test-voice-perception test-live-replays lint-dialogue` — PASS
- `python3 -m pytest tests/ -q` — 987 passed, 0 failed

## NEXT

1. Push → GitHub CI SUCCESS
2. `make preflight-gates` + FreeSWITCH Zoiper redeploy
3. Verify runtime SHA == new SHA (`IMVERA_LLM_INTERPRET=0`)
4. Free live call acceptance (not verbatim `fs-1f6d3000`) + forensic
