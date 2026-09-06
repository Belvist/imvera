---
name: refactor-safely
description: Restructure voiseup code without behavior change. Use for renames, package moves, and deduplication after tests exist.
---

# Refactor Safely

## Preconditions

- [ ] Existing tests cover behavior being refactored
- [ ] `make test` green before starting
- [ ] No feature additions in same PR

## Process

1. **Characterize** — list observable behaviors that must not change
2. **Freeze** — add characterization test if gap exists
3. **Small steps** — one mechanical change per commit
4. **Verify** — full test suite after each step
5. **Delete** — remove dead code only after imports gone and tests green

## Safe Refactors

- Rename with IDE/rename-symbol
- Move module → update imports, no logic change
- Extract function with identical inputs/outputs
- Split file along ownership boundaries (Planner/State/etc.)

## Unsafe Without ADR

- Merging two dialogue modules
- Changing event schema sent to Core
- Changing audio frame format
- Replacing State storage model

## Output

```text
BEHAVIORS PRESERVED: ...
STEPS: ...
VERIFIED: make test → ...
```
