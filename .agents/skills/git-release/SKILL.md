---
name: git-release
description: Version, tag, and document voiseup releases. Use when preparing deployable artifacts or changelog entries.
---

# Git Release

## Versioning

Semantic versioning: `MAJOR.MINOR.PATCH`

- MAJOR: breaking contract with Core or audio format
- MINOR: new feature, backward compatible
- PATCH: bugfix only

Pre-1.0: `0.x.y` — pilot phase, contracts may still move with ADR.

## Release Checklist

- [ ] `make test` + voice gates green
- [ ] `CHANGELOG.md` entry
- [ ] Image tagged with git SHA
- [ ] `production-readiness` skill gates documented
- [ ] Migration notes if env vars changed
- [ ] Rollback tag noted

## Commit Messages

Imperative, concise, explain why:

```text
fix(dialogue): do not close wellness on backchannel «ага»

Slot stayed OPEN when answer_judgement=BACKCHANNEL.
Regression: test_wellness_backchannel.py
```

## Tags

```bash
git tag -a v0.1.0 -m "First SIP lab gate"
```

Tag only after user requests release (or CI release job).

## Changelog Format

```markdown
## [0.1.0] - 2026-09-06
### Added
- ...
### Fixed
- ...
### Security
- ...
```

## Forbidden

- Force push to main without explicit user request
- Tag without VERIFIED gates
- Commit secrets (rotate if accidental)
