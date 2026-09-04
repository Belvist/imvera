# LATENCY — бюджет задержки разговорной системы

> Статус: design target (2026-09-03). Owner pain: ~20 s wait — **недопустимо**.

## Целевые SLA (per-turn, одиночный звонок)

| Путь | First audio | Полная реплика | LLM |
|------|-------------|----------------|-----|
| **Greeting** (turn 0) | **<500 ms** | <1.2 s | **запрещён** |
| **Short ack** («да», «хорошо») | **<800 ms** | <1.5 s | **запрещён** |
| **Good/Bad probe** (scripted Q) | **<800 ms** | <1.5 s | **запрещён** |
| **Record notify** | **<800 ms** | <1.5 s | **запрещён** |
| **Closing** (all bands) | **<800 ms** | <2.0 s | **запрещён** |
| **Critical fast close** | **<500 ms** | <1.0 s | **запрещён** |
| Narrative / side-question | <2.0 s | <4.0 s | опционально (фаза 3) |
| Safety confirm | <1.0 s | <2.0 s | **запрещён** |

## Архитектурные правила

### Scripted fast path (фаза 1–2)

1. `reply/pools.py` — все greeting, probe, notify, goodbye
2. `AgendaManager.spoken_prompt_for_current()` — детерминированный выбор из пула
3. `pick_from_pool()` — O(1), без сети

### Когда LLM **разрешён** (фаза 3+)

- Длинный off-topic narrative (≥6 слов, не матчит тему) — **опционально**
- Side-question («Кто ты?») — короткий scripted ответ preferred; LLM fallback
- **Никогда:** greeting, closing, record_notify, safety confirm, symptom first probe

### Когда LLM **запрещён** (`scripted_only=True`)

- `ResponseGoalKind.GREET`
- `ResponseGoalKind.CLOSE`
- `ResponseGoalKind.SYMPTOM_FOLLOWUP` (первые N ходов)
- `ResponseGoalKind.ACKNOWLEDGE` (короткие ответы)
- RECORD_NOTIFY phase

## Разбивка бюджета (greeting turn 0)

```text
Lua answer + HTTP create_call     ~100–300 ms
Pool pick GREETING_POOL           <1 ms
TTS first segment (warm cache)    ~150–400 ms
─────────────────────────────────────────────
Target first_audio                <500 ms
```

## Разбивка бюджета (scripted ack turn)

```text
TurnAnalyzer (deterministic)      <5 ms
AgendaManager.spoken_prompt       <1 ms
TTS first segment                 ~150–400 ms
─────────────────────────────────────────────
Target first_audio                <800 ms
```

## Anti-patterns (не повторять)

| Паттерн | Проблема |
|---------|----------|
| LLM на каждый ход | +1.5–9 s prefill+gen |
| `plan_reply` monolith | state+compose+LLM в одном вызове |
| Ждать полный LLM stream для first audio | first_audio = gen time |
| Двойной compose (pool + LLM) | duplicate TTS |

## Phase 2 implementation notes

- `CallPhaseMachine` должен выставлять `ResponseGoal.scripted_only=True` на hot path
- `ReplyComposer` (фаза 3): pool-first, LLM только если `allow_llm=True`
- Pre-warm TTS для `GREETING_POOL[0]` при `begin_call`
- LATENCY trace: `greeting= pool= tts= first_audio=` (отдельно от LLM)

## Verification

```bash
make test-fast
python3 -m unittest telephony.tests.test_conversation_system_phase1.PoolsTests -v
# Live: loopback first_audio <800ms на scripted turns (owner Zoiper gate)
```
