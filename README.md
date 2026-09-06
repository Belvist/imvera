# VoiseUp

Greenfield **voice + telephony** stack for [IMVERA](https://imvera.ru/).

Пожилой человек отвечает на обычный звонок. Вера ведёт разговор. Семья получает статус.

```text
LLM semantic signals → POSSIBLE / YELLOW candidate only — never RED authority.
Deterministic transcript rules → RED/YELLOW candidate.
Control confirmation → CONFIRMED RED.
```

## Status

| Phase | Status |
|-------|--------|
| 0 Agent system | ✅ |
| 1 Architecture/contracts | 🟡 ADR STT/TTS updated; CI added |
| 2 Domain core | ✅ Phase 2 gate |
| 3A STT lab (Qwen3-ASR benchmark) | next |
| 4 Realtime streaming | ❌ |
| 5 Asterisk | ❌ |

## Quick start

```bash
make install && make test    # local dev
make up                      # Docker: postgres, redis, minio, api
make api-health              # http://127.0.0.1:8080/health
make down                    # stop stack
```

Copy `docker/.env.example` → `docker/.env` for custom secrets (never commit `.env`).

Full guide: **[LAUNCH.md](./LAUNCH.md)**

## Documentation

| File | Purpose |
|------|---------|
| [**LAUNCH.md**](./LAUNCH.md) | How to run Phase 1 gate and start Phase 2 |
| [**docs/PLAN.md**](./docs/PLAN.md) | Master plan v1.2 (Architecture Freeze) |
| [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) | System architecture |
| [docs/AUDIO_CONTRACT.md](./docs/AUDIO_CONTRACT.md) | Full-duplex + sample rates |
| [docs/DIALOGUE_SPEC.md](./docs/DIALOGUE_SPEC.md) | FSM, slots, 12 scenarios |
| [AGENTS.md](./AGENTS.md) | AI agent constitution |

## Principles

- Transport (SIP) does not speak — only moves audio
- STT never hears Vera's outbound TTS
- One dialogue brain, one FSM owner
- StatusEngine owns final GREEN/YELLOW/RED (not LLM)
- TTS/STT chosen by Phase 3 benchmark (see ADR-003, ADR-006)

## License

TBD
