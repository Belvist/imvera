---
name: staff-engineer-verification-loop
description: Senior/Staff autonomous verification — task contract, MossVoice verification matrix, OBSERVE→REVERIFY loop, final report. Use for every non-trivial change. Extends deep-implementation-workflow; does not replace it.
---

# Staff Engineer Verification Loop (MossVoice)

**Relationship to other skills**

| Skill | Role |
|-------|------|
| `engineering-architecture/` | Stage 1 — design, FSM, invariants |
| `deep-implementation-workflow/` | Stages 1–4 skeleton (architecture → code → security → tests) |
| **This skill** | Verification loop, task contract, matrix by change type, final report |
| `anti-stub-enforcement/` | Stub scanner (`verify_no_stubs.py`) |

Use **deep-implementation-workflow** for stage order; use **this skill** for what to run, how to loop, and how to report.

Rule (always on): `.cursor/rules/staff-engineer-verification-loop.mdc`.

---

## 1. Task Contract (fill before OBSERVE)

```markdown
## Task Contract

**Goal:** One sentence — user-visible outcome.

**Acceptance:** Observable checks (e.g. "bad_symptom + «сильно» advances agenda", "401 without key").

**Constraints:** Scope limits, frozen areas (ROADMAP gates), no live FS, etc.

**Verification:** Commands you will run; expected exit 0 / PASS counts.
```

If acceptance is vague, clarify or propose testable criteria before coding.

---

## 2. Verification Loop

```
OBSERVE → CHANGE → VERIFY → INSPECT → CORRECT → REVERIFY
```

- **OBSERVE:** reproduce bug or baseline; grep logs/tests; read AGENTS.md + affected modules.
- **CHANGE:** minimal diff; match project style; no stubs (Stage 2 of deep-implementation-workflow).
- **VERIFY:** run matrix rows for change type (§3); save command + exit code.
- **INSPECT:** read failures — do outputs match acceptance, not just green?
- **CORRECT:** fix root cause; do not weaken tests.
- **REVERIFY:** re-run failed checks + regression suite.

Loop until acceptance met or blocker documented with evidence.

---

## 3. MossVoice Verification Matrix

| Change type | Required checks |
|-------------|-----------------|
| **Any prod code touched** | `python3 .cursor/skills/anti-stub-enforcement/scripts/verify_no_stubs.py` on changed files (or `make verify-stubs`) |
| **dialogue / `conversation_system`** | `make test-fast` · `python3 voice-lab/dialog_quality.py --strict` · `python3 scripts/synthetic_caller.py --strict` · `python3 -m unittest telephony.tests.test_auto_call_scenarios` |
| **telephony integration** (orchestrator, Lua, ESL, HTTP turn path) | Above dialogue row **+** `python3 scripts/live_vera_conversation.py --strict` when FreeSWITCH/agent stack available |
| **security / API / product** | `make test-fast` · checklist from `deep-implementation-workflow` Stage 3 (SQL param, IDOR, body limits, `hmac.compare_digest`, fail-closed) · targeted tests e.g. `telephony.tests.test_product_api`, `test_telephony_hardening` |
| **voice_runtime** | `python3 -m unittest discover -s voice_runtime -p "test_*.py"` · `make test-fast` if telephony touched |
| **Doc-only** | Link/format check; skip test matrix unless behavior docs must match code |

**Always:** `read_lints` on edited files before claiming done.

**Optional depth (significant dialogue release):** `python3 voice-lab/e2e_live_calls.py --strict`.

---

## 4. Mental Roles (before final report)

| Role | Question |
|------|----------|
| Architect | Are invariants and FSM transitions correct? |
| Builder | Is every path implemented (no stubs/TODO in prod)? |
| Tester | Did matrix checks run and pass? |
| Reviewer | Security, races, degraded deps — fail-closed? |

---

## 5. Final Report Template

Copy into completion message for non-trivial work:

```markdown
## Summary
<1–2 sentences for the user>

**Implemented**
- …

**Verified**
- `make test-fast` → N OK, M skip
- `dialog_quality --strict` → 18/18 PASS
- (other commands + outcomes)

**Tests**
- Added/modified: …
- Not run: … (with reason)

**Not verified**
- Live Zoiper / RTP: …
- Deploy / `make up`: …
- (anything else skipped)

**Remaining risks**
- …
```

---

## 6. Honesty Defaults (MossVoice)

Common gaps — **always** list under "Not verified" if true:

- Live Zoiper (SIP/RTP/mic) — HTTP harness ≠ phone path (AGENTS.md owner gate).
- Container rebuild after code change.
- FreeSWITCH dialplan / ESL when FS not running.
- Cloud LLM key absent → NullLLM / script fallback only.

Never equate `synthetic_caller --strict` with owner Zoiper gate.

---

## 7. Anti-Patterns

| Pattern | Fix |
|---------|-----|
| "Should work" without command output | Run matrix row or say not run |
| Weakened test assertions | Restore spec; fix product |
| Huge diff, one VERIFY | Split loops; smaller CHANGE steps |
| Duplicate architecture essay | Link `engineering-architecture-first.mdc` |
| "Готово" with failing test | CORRECT → REVERIFY or report blocker |

---

## 8. Quick Commands

```bash
make verify-stubs
make test-fast
python3 voice-lab/dialog_quality.py --strict
python3 scripts/synthetic_caller.py --strict
python3 -m unittest telephony.tests.test_auto_call_scenarios
python3 scripts/live_vera_conversation.py --strict   # FS stack up
python3 voice-lab/e2e_live_calls.py --strict         # optional depth
```

Update `AGENTS.md` «Текущее состояние» only after **significant** shipped change (with date) — per deep-implementation-workflow Stage 4.
