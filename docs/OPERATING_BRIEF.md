# OPERATING BRIEF — ImVera / VoiseUp
*(закон для людей и агентов.)*

## 0. Цель этапа (не «миллиарды»)

**Pilot-ready на frozen path**, не Instagram-scale.

Честная лестница:
- lab: 1 concurrent, `IMVERA_OBS_MODE=debug`
- pilot: 5–10 бабушек, obs=`pilot`, PSTN
- одна GPU-коробка: ~15–30 comfort
- 100+ только после measured probe + отдельный ADR

«Миллионы пользователей» = Core/семья в приложении, **не** миллионы
одновременных голосовых сессий на одном bridge.

## 1. Одна фраза

Вера — **протокол ухода по телефону** с доказуемыми гарантиями, не чат-бот
и не LLM-собеседник.

## 2. Frozen path (не менять без ADR, который явно supersedes ADR-014)

```text
SIP → FreeSWITCH → mod_imvera_audio → CallActor
→ VAD → GigaAM → DialogueEngine (CDK)
→ PhraseSelect/banks → Silero TTS → FreeSWITCH → caller
```

Prod speech: **без LLM-авторинга речи Веры** (ADR-020/021).
SYSTEM_DESIGN с Composer в hot path = устаревший чертёж; CDK побеждает.

## 3. Forbidden (нарушение = откат PR)

- Четвёртая система / новый telephony / dual dialogue brain
- LLM пишет spoken text Веры в проде
- Cloud STT/TTS как тихий fallback
- Поднять `max_active_calls` без capacity probe
- Always-forensic JSONL в pilot/prod
- Фичи/новые сценарии пока ADR-014 gates 1–3 не VERIFIED (кроме residual
  bugfix на daily-check path)
- «Тесты зелёные = готово» без live `call_id` / метрик где нужен live
- Заодно «улучшить характер/копирайт» в том же PR, что инфраструктура

## 4. Владельцы слоёв

| Слой | Владелец | Нельзя |
|---|---|---|
| Protocol (required slots) | одна таблица данных (цель) | tri-truth: mission + FILLER + Status |
| Dialogue | `dialogue_engine` reducer | второй scheduler |
| Speech | PhraseSelect / banks | LLM речь |
| Realtime | CallActor | решать ЧТО сказать |
| Media | FreeSWITCH + prod module | lab `mod_audio_stream` как prod WRITE |
| STT/TTS | replica pools | смена провайдера в freeze |
| Status | StatusEngine → Core | TG demo = «финальный закон» |
| Obs | `IMVERA_OBS_MODE` tiers | silent drops |
| Capacity | probe → then N workers | надежда вместо графика |

## 5. P0 очередь (строго по порядку, один PR = одна тема)

### P0a — OBS tiers (этот PR)
В `packages/voice_runtime/trace.py`: `obs_mode`, `keep_event`, budget,
`write_call_summary`, `trace_stats`.

Definition of Done:
1. `/health` (ready) отдаёт `obs_mode` + `trace_stats`.
2. На finalize звонка один раз `write_call_summary(call_id)`.
3. Unit-тесты tiers (debug=всё; pilot=без `stage.timing`; prod=errors+lifecycle).
4. Этот документ + ADR-022 verification notes.
5. Default mode остаётся `debug`.

### P0b — Protocol as data (следующий PR, НЕ этот)
Один YAML: short/full/complaint → required slots → status impact.

### P0c — Capacity probe (следующий, НЕ этот)
concurrent → p95 → GPU → drops. `max_active_calls` = 1 до evidence.

## 6. Stop-rule для агентов

1. Читай этот бриф + ADR-014/021/022 перед кодом.
2. Одна тема на PR.
3. Сначала докажи gap (grep/health/test), потом правь.
4. Не «почини все дыры».
5. Definition of Done в PR checklist.
6. Если задача шире P0a — остановись и спроси.
