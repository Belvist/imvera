# Asterisk forensic lab (ADR-001 historical)

**NOT production.** FreeSWITCH is production telephony per ADR-013.

## Contents

- `docker/` — Asterisk image + configs
- `services/asterisk_app/` — Stasis ARI app (lab)
- `packages/asterisk.py` — ARI helpers
- `docker-compose.voice.yml` — lab overlay (port 5062)

## Run (lab only)

```bash
docker compose -f lab/asterisk/docker-compose.voice.yml up -d
```

Production voice gateway does **not** import or start Asterisk.
