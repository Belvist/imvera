---
name: code-review
description: Review voiseup changes for architecture ownership, state safety, cancellation, and deployment truth. Use before merge or after implementation.
---

# Code Review

## Review Order

1. **Architecture ownership** — one brain, one FSM owner?
2. **State mutations** — only State module writes facts/slots?
3. **Transport purity** — SIP layer free of dialogue/verdict logic?
4. **Cancellation** — generation_id checked before playback/TTS commit?
5. **Text integrity** — single canonical path to TTS?
6. **Verdict boundary** — observations only, no local GREEN/RED?
7. **Error semantics** — TECHNICAL ≠ NO_CONTACT ≠ GREEN?
8. **Tests** — behavior asserted, not implementation details only?
9. **Secrets** — no keys in diff?
10. **Deploy truth** — env vars documented; no hardcoded endpoints?

## Red Flags (block merge)

```text
❌ new fallback dialogue path
❌ Renderer mutates slot status directly
❌ Lua/dialplan generates user-facing text
❌ silent provider switch on error
❌ verdict in telephony package
❌ sync postgres in speech_end → tts hot path
❌ test removed or weakened without justification
```

## Questions to Ask

- What happens on barge-in mid-TTS?
- What happens on STT timeout?
- What trace proves spoken == generated?
- Which gate verifies this change live?

## Output

```text
VERDICT: approve | approve with notes | block

BLOCKERS:
- ...

NOTES:
- ...

MISSING VERIFICATION:
- ...
```
