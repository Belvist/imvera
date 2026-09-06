# VoiseUp

Greenfield **voice + telephony** stack for [IMVERA](https://imvera.ru/).

Пожилой человек отвечает на обычный звонок. Вера ведёт разговор. Семья получает статус.

## Status

| Phase | Status |
|-------|--------|
| 0 Agent system | ✅ |
| 1 Contracts + ADR | ✅ |
| 2 Domain core (FSM, Safety, Status) | ✅ |
| 3 Speech lab (Silero STT/TTS) | next |

## Launch (start here)

```bash
make install && make test
```

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
- Silero `v5_5_ru` phrase-chunked TTS @ 8k or 24k

## License

TBD
