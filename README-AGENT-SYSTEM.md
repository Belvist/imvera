# IMVERA VoiseUp — Agent System

Engineering process layer for the **voiseup** repository (greenfield voice + telephony for IMVERA).

## Structure

```text
AGENTS.md              ← constitution (read first)
PROJECT_CONTEXT.md     ← product + architecture context
CLAUDE.md              ← symlink-style pointer to AGENTS.md (for Claude Code)
README-AGENT-SYSTEM.md ← this file

.agents/skills/        ← repeatable workflows (SKILL.md each)
.cursor/rules/         ← Cursor scoped rules
.github/copilot-instructions.md
```

## How Agents Should Work

1. **Constitution first** — `AGENTS.md` overrides ad-hoc instructions.
2. **Skill per task** — open the matching `SKILL.md` before acting.
3. **Gates, not vibes** — every completion uses CHANGED/VERIFIED/NOT VERIFIED/REMAINING RISKS/NEXT GATE.
4. **No legacy** — this repo does not inherit code or patterns from prior voice projects.

## Skills Catalog

| Skill | When |
|-------|------|
| `codebase-recon` | Entering unfamiliar area |
| `architecture-design` | New component, boundary, ADR |
| `implementation` | Writing production code |
| `debug-root-cause` | Bugs, regressions |
| `testing-verification` | Tests, benchmarks, gates |
| `code-review` | Pre-merge review |
| `refactor-safely` | Structure change, same behavior |
| `production-readiness` | Deploy / release claims |
| `security-privacy` | PII, consent, secrets |
| `performance-realtime` | Latency, barge-in, streaming |
| `voice-dialogue-quality` | Vera dialogue semantics |
| `telephony-integration` | SIP, PSTN, RTP, codecs |
| `ai-model-evaluation` | STT/TTS/LLM selection |
| `dependency-research` | Library/provider research |
| `git-release` | Versioning, changelog |
| `incident-postmortem` | After production incidents |

## Adding a Skill

Follow Cursor skill format:

```text
.agents/skills/my-skill/
└── SKILL.md    # YAML frontmatter: name, description
```

Required frontmatter:

```yaml
---
name: my-skill
description: One sentence — what and when.
---
```

## Cursor Rules

- `00-project-core.mdc` — `alwaysApply: true`, project invariants
- Add scoped rules with `globs:` for language-specific conventions as code appears

## Planned Specialized Agents (Level 2)

Not implemented yet — future orchestration layer on top of skills:

- Principal Architect
- Realtime/Voice Engineer
- Systems Engineer
- Senior Backend
- Security Engineer
- QA/Verification Engineer
- Adversarial Code Reviewer
- Production/SRE

Each agent runs **through skills**, not with private incompatible rules.

## Version

- **v1.0** — 2026-09-06 — greenfield bootstrap for voiseup
