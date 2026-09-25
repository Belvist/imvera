# Deploy runbook (P0 plan 5)

## Topology: what runs where

| Piece | Lab (now) | Prod (future) |
|---|---|---|
| STT/TTS/LLM workers | Mac launchd, :9101–9103 (+replicas :9111/:9112) | GPU servers, same HTTP contract |
| Media bridge :9210 | Mac launchd | container (`infra/freeswitch/docker-compose.yml` → media-bridge) |
| FreeSWITCH | docker, `imvera-freeswitch` | same image + trunk + SBC |
| Postgres/Redis/MinIO/API | docker dev stack | managed / separate hosts |
| Zoiper | Mac app (lab softphone) | real phones via trunk |

Hard constraint: inference workers are Apple-Silicon-only (MLX/MPS).
They CANNOT move into linux/amd64 containers — prod needs GPU hosts
speaking the same `/v1/*` HTTP contract. ReplicaPool makes the move
transparent (comma-separated URLs).

## Env separation

- Lab: `IMVERA_LLM_INTERPRET=0`, `IMVERA_ELDER_DISPLAY_NAME=Тамара Юрьевна`,
  `IMVERA_PERSIST_SPOOL_DIR=.run/spool`, Mac paths. See `docker/.env.example`.
- Prod: no lab ack, no Mac paths, secrets from vault (never committed).
- Dev defaults in repo (`imvera_dev_change_me`, `ClueCon`, `gate`) are
  LAB ONLY. Rotate before any prod traffic (checklist below).

## Deploy a new bridge version (lab)

```sh
git pull && git rev-parse --short HEAD   # note SHA
python3 tools/voice_lab/policy_diff_v8_v9.py 2>&1 | grep GATE
python3 scripts/dialogue_corpus_gate.py 2>&1 | tail -1
launchctl unload ~/Library/LaunchAgents/ai.imvera.bridge.plist
sleep 3
launchctl load ~/Library/LaunchAgents/ai.imvera.bridge.plist
sleep 60
python3 scripts/version_watch.py --once --expect <SHA>
curl -s http://127.0.0.1:9210/health/ready
```

## Rollback (one command + verify)

```sh
git log --oneline -3                      # pick previous SHA
git checkout <PREV_SHA> -- . 2>/dev/null || git reset --hard <PREV_SHA>
launchctl unload ~/Library/LaunchAgents/ai.imvera.bridge.plist; sleep 3
launchctl load ~/Library/LaunchAgents/ai.imvera.bridge.plist; sleep 60
python3 scripts/version_watch.py --once --expect <PREV_SHA>
```

DB migrations are additive (`IF NOT EXISTS`); rollback never needs
a DB downgrade. If data is suspect: restore from `.run/backups/` via
`docs/runbooks/postgres-backup.md`, then `scripts/replay_spool.py`.

## Backups (scheduled)

Daily launchd job `ai.imvera.pg-backup` (03:00 local), installed by:

```sh
cp scripts/launchd/ai.imvera.pg-backup.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/ai.imvera.pg-backup.plist
```

Freshness rule: no backup newer than 26h = page. Check:
`ls -lat .run/backups/ | head -3`.

## Pre-prod checklist (owner actions — no API for these)

- [ ] Branch protection on `main` (+ required CI checks)
- [ ] Rotate ALL dev defaults (PG, ESL, SIP gate users) for prod
- [ ] Trunk contract + inbound numbers (Novofon TRYING is still open)
- [ ] 100-family profiles + elder consents + escalation channels
- [ ] Audio soak-100 gate green on prod-like hardware
- [ ] Alerting: version_watch loop + backup freshness + queue depth
