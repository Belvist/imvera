---
name: deep-implementation-workflow
description: End-to-end implementation workflow for MossVoice — architecture first, full production code, security audit, and verification. Use for any non-trivial feature, refactor, or bug fix in telephony, voice_runtime, or product API.
---

# Deep Implementation Workflow (MossVoice)

Follow all four stages **in order**. Do not skip to code without Stage 1.

---

## Stage 1 — Architecture & Logic (before any code)

1. Read `AGENTS.md` + relevant section of `ROADMAP.md`.
2. Apply the **engineering-architecture** skill:
   - Define invariants (pre/post conditions).
   - If stateful → declarative FSM table `(src, event, guard, action, dst)`.
   - Model failure modes: timeout, hangup, OOM, duplicate events.
3. For dialogue changes: one line in `_build_transitions()`, not new boolean flags.
4. Write down the test matrix (what must pass in `make test-fast`).

**Gate:** You can explain the design in 5 sentences without hand-waving.

---

## Stage 2 — Full Implementation (no stubs)

1. Implement complete business logic — validation, persistence, error paths.
2. Match existing project style (read surrounding files first).
3. Minimal diff: only what the task requires.
4. Run `python3 .cursor/skills/anti-stub-enforcement/scripts/verify_no_stubs.py`.

**Gate:** Scanner exit 0; no `TODO`/`pass`-only functions in production paths.

---

## Stage 3 — Security Audit

Check every change against `.cursor/rules/security-and-fail-secure.mdc`:

- [ ] SQL parameterized; no f-string queries.
- [ ] User/household/call IDs verified server-side (IDOR).
- [ ] Request bodies size-limited; secrets from env only.
- [ ] HMAC/tokens compared with `hmac.compare_digest`.
- [ ] PII paths use `0700`/`0600` permissions.
- [ ] Fail secure: errors do not open access or fake success.

---

## Stage 4 — Final Verification

1. **Tests:** `make test-fast` (or targeted `unittest` for the module).
2. **Dialogue:** if dialogue touched → `python3 voice-lab/dialog_quality.py --strict`.
3. **Lint:** `read_lints` on edited files.
4. **Honesty:** if live Zoiper / deploy not run — say so explicitly; do not claim «проверено на проде».

Update `AGENTS.md` «Текущее состояние» only after a **significant** shipped change (with date).

---

## Anti-Patterns (instant fail)

| Pattern | Why forbidden |
|---------|----------------|
| «Сделаю позже» in production code | Breaks trust and prod stability |
| Fake `return {"ok": true}` | Masks broken dependencies |
| Patching with `_flag_xyz` | FSM exists precisely to avoid this |
| Claiming «готово» without tests | User cannot verify |

---

## Quick Command Reference

```bash
make test-fast
make verify-stubs
python3 voice-lab/dialog_quality.py --strict   # if dialogue changed
python3 -m unittest discover -s voice_runtime -p "test_*.py"  # if runtime changed
```
