# Current task — finish the frozen path (ADR-014)

**Outcome:** One production path, 100 consecutive full calls. **No fourth system.**

```text
SIP operator → FreeSWITCH → mod_imvera_audio → CallActor
→ VAD → GigaAM → DialogueEngine → local LLM only when needed
→ Silero TTS → FreeSWITCH → caller
```

## Active residual (this session)

**Calls:** `fs-c83012aa` (mood → bare summary), `fs-f534c2e6` (soft «нет» → «Расскажите коротко» → bare «Спасибо за разговор.»).

**Local fix (NOT committed / NOT deployed):**

- ITS: «Спасибо за разговор. Хотите ещё что-то добавить?»
- Soft decline («да вроде бы нет», «сказал уже») → warm close
- Share content → `observations["important_to_share"]` + «Хорошо, записала.» + warm close
- Summary: «Всё, спасибо, {name}. Всего вам хорошего. До свидания.»
- Optional schedule line via `prior_call_context["next_call_spoken"]` (not wired from CallActor yet)
- Plans harvest: «планов толком тоже нет»

Offline reproduce `fs-f534c2e6` → ITS then named farewell. `pytest tests/` green.

**NEXT GATE:** commit + push + CI + lab redeploy; Zoiper re-test; CALL_ID ≠ `a76ab4d`.

## Forbidden

New features / fourth system (ADR-014). Closing copy fix = residual spoken-surface on frozen path.
