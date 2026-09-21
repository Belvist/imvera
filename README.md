# VoiseUp

Greenfield **voice + telephony** stack for [IMVERA](https://imvera.ru/).

Пожилой человек отвечает на обычный звонок. Вера ведёт разговор. Семья получает статус.

```text
LLM semantic signals → POSSIBLE / YELLOW candidate only — never RED authority.
Deterministic transcript rules → RED/YELLOW candidate.
Control confirmation → CONFIRMED RED.
```

## Status (main @ `544cce4`; `feature/voice-zoiper-m5` merged — identical SHAs verified 2026-09-21)

Архитектура выбрана и заморожена ([ADR-014](./docs/adr/014-architecture-freeze-acceptance-gates.md),
путь: SIP → FreeSWITCH → CallActor → GigaAM → DialogueEngine → TTS).
**Ни одни из 7 acceptance gates не пройдены** — это не прод.

| Направление | Состояние |
|-------------|-----------|
| Dialogue engine (single-writer, fail-safe uncertainty) | работает в лабе, 1494 passed / 17 baseline-failed |
| Voice runtime (PCM integrity, utterance resume) | работает в лабе |
| STT longform (>25s fallback) | код готов, вживую не проверен |
| Local SIP lab (Zoiper ↔ FreeSWITCH ↔ Vera) | звонки идут, трассировки есть |
| TTS provider | **открыт вопрос: дефолт `mlx_customvoice` (Qwen3-TTS), `silero_lab` — NC/lab-only, freeze называет Silero — нужен license/quality gate** |
| PSTN via VoxImplant | **блокер: 403 Invalid CallerID** — нужен CallerID в панели |
| PSTN via Novofon (gateway `novofon` в контейнере) | **блокер: провайдер молча дропает SIP с нашего IP** — шаги в кабинете |
| Downstream stop/ack, barge-in | отсутствует (доказано тестом), включать запрещено |
| Core inbox / результат → статус семье | не собрано |
| Прод-сервер, GPU, мониторинг | нет |

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
