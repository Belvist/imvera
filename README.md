# VoiseUp

Greenfield **voice + telephony** stack for [IMVERA](https://imvera.ru/).

Пожилой человек отвечает на обычный звонок. Вера ведёт разговор. Семья получает статус.

```text
LLM semantic signals → POSSIBLE / YELLOW candidate only — never RED authority.
Deterministic transcript rules → RED/YELLOW candidate.
Control confirmation → CONFIRMED RED.
```

## Status (`feature/voice-zoiper-m5`, проверка 2026-10-08)

Рабочая ветка — **feature/voice-zoiper-m5**. На исходном `361972eb` она
на 198 коммитов впереди main; прежняя запись об одинаковых ветках устарела.
Путь: SIP → FreeSWITCH → CallActor → GigaAM → DialogueEngine → TTS.
Техническая приёмка исходников и приёмка живого продукта различаются:
[актуальный аудит и проверяемые ограничения](docs/evaluation/technical-audit-2026-10-08/README.md),
[журнал](docs/current-task.md), [передача runtime-агенту](docs/production-dialogue-handoff.md).
Сквозная промышленная приёмка на целевом сервере не подтверждена.
Source4274a451 (2026-10-09): [CI11/11 SUCCESS,3647 PASS/0 FAIL/3 SKIP](https://github.com/Belvist/imvera/actions/runs/37979468470),
[grounded revisions / unknown / длинная речь](docs/evaluation/grounded-revisions-2026-10-09/README.md).
Полный медицинский режим сохраняет все пять базовых тем; target audio/Core/load
по-прежнему требуют отдельной приёмки.

| Направление | Состояние |
|-------------|-----------|
| Dialogue engine (single-writer, grounded facts) | SDK/regression CI проходит; личные темы — ActionPolicy v11, обычный check-in преимущественно legacy |
| Voice runtime | streaming PCM, generation cancellation, playback ledger реализованы; live stop/latency gate открыт |
| STT | GigaAM final; prefix_batch opt-in, не stateful streaming; Linux CPU service curve измерена отдельно |
| Local SIP lab | есть исторические звонки/trace; текущий source требует нового аудио gate |
| TTS provider | Mac profile MLX Qwen; portable profile Qwen HTTP resident; actual target backend/revision требует сверки |
| Silero TTS | explicit lab backend; license/provenance конкретного артефакта требуется проверить |
| PSTN | прежние ограничения операторов не перепроверены; актуальная доступность неизвестна |
| Barge-in | механизм есть, default OFF; echo-reference gate не является полноценным AEC |
| Core / семья | Postgres + transactional outbox есть; Core ack / уведомление получателю сквозным тестом не подтверждены |
| Capacity | profile admission 1; 100 полных телефонных разговоров не принято |

## Quick start (lab, Mac)

```bash
make install && python3 -B -m pytest tests/ -q -p no:cacheprovider
make freeswitch-zoiper-voice-up   # full lab: FS + bridge + STT/TTS
```

Bridge: `http://127.0.0.1:9210/health/ready`. STT `:9101`, TTS `:9102`.
Секреты — только в окружении/контейнере, никогда в git.
Детали запуска: **[LAUNCH.md](./LAUNCH.md)**. Текущая работа: **`docs/current-task.md`**.

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
