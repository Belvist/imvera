---
name: anti-stub-enforcement
description: Enforces zero-stub production code policy. Detects pseudocode, placeholders, hollow functions, and silent exception swallowing. Use before committing code, when reviewing agent output, or when the user asks to verify implementation completeness.
---

# Anti-Stub Enforcement

This skill ensures every delivered change is **complete, runnable, and honest** — no stubs that pretend to work.

---

## When to Apply

- Before marking any implementation task as done.
- After generating or editing production code in `telephony/`, `voice_runtime/`, `scripts/`.
- When the user says: «без заглушек», «полная реализация», «не обманывай».

---

## Mandatory Verification

Run the static scanner from the repository root:

```bash
python3 .cursor/skills/anti-stub-enforcement/scripts/verify_no_stubs.py
```

Or via Makefile:

```bash
make verify-stubs
```

**Exit 0 = clean** (no NEW violations beyond legacy baseline). Any non-zero exit means fix violations before claiming completion.

Legacy codebase has 35 known `except: pass` sites in `baseline.txt` — scanner fails only on **new** stubs beyond that list. Use `--no-baseline` to see all violations.

---

## What the Scanner Detects

| Code | Meaning |
|------|---------|
| `HOLLOW_FUNCTION` | `pass`, `...`, or only `raise NotImplementedError` in a concrete method |
| `NOT_IMPLEMENTED` | `NotImplementedError` outside abstract/protocol classes |
| `SWALLOWED_EXCEPTION` | `except ...: pass` without logging or re-raise |
| `DEFERRED_MARKER` | `# TODO`, `# FIXME`, `# STUB`, `# PLACEHOLDER` in production files |
| `HANDWAVE` | Comments like «implement later», «rest of implementation» |

**Allowed exceptions:** `@abstractmethod`, `ABC` subclasses, informal ABC classes where every method raises `NotImplementedError` (e.g. `ProductStore` protocol).

---

## Agent Self-Check Before «Готово»

1. Every new function has real logic — not `pass` or fake `return True`.
2. External calls (DB, HTTP, STT, LLM) either work or **fail closed** with a typed error.
3. No deferred markers left in production paths.
4. Tests exist for new behavior (or user explicitly waived tests).
5. `verify_no_stubs.py` passes on changed directories.

---

## If a Violation Is Intentional

Do not silence the scanner. Either:
- Implement the real logic, or
- Move the skeleton to a clearly named abstract base with docstring `Abstract ...` and all methods raising `NotImplementedError`.

Never ship partial logic with a comment «доделаем потом».
