# Проверка артефакта

База: Belvist/imvera, feature/voice-zoiper-m5, f71de9d8ba36609b116eb24dd63c7e88a94c05d7.

CHANGED: созданы отдельные проект, задание Cursor и проверки существующего кода. Production-код не изменялся, ничего не отправлено в репозиторий. Предлагаемый движок не выдаётся за уже реализованный.

VERIFIED:

```text
python -m pytest tests/ -q
103 passed, 2 skipped in 0.28s

IMVERA_AUDIT_REPO=/workspace/scratch/31cc57699069/imvera-audit-f71de9d \
  /workspace/scratch/31cc57699069/imvera-audit-venv/bin/python -m pytest \
  /workspace/scratch/31cc57699069/IMVERA_Dialogue_Audit/test_dialogue_acceptance_gaps.py \
  -q --tb=short
10 failed, 3 passed in 0.25s
```

Все 10 провалов — AssertionError по поведению, не ошибки импорта или окружения. Список и результаты приведены в DIALOGUE_DESIGN.md. Использованы настоящие Planner, CallSession, semantic_bridge, context_builder; async-тест проверяет CallActor с управляемыми тестовыми провайдерами. InMemoryCallRecordStore изолирует проверки семантики от PostgreSQL.

NOT VERIFIED: текущий локальный runtime Даниила, inference MLX, актуальные записи Zoiper, качество распознавания/озвучивания, p50/p95, PostgreSQL для новых сценариев, реализация предложенного проекта.

REMAINING RISKS: новый контракт требует согласованной миграции workers/runtime/state; текущие транспортные дефекты способны портить смысл до STT; целевые задержки на M5 ещё нужно измерить.

NEXT GATE: реализация единого перехода семантики и состояния с исправлением приложенных провалов, затем продолжение всей приёмки по CURSOR_TASK.md. Закрытие этих модульных проверок отдельно не закрывает задание полноценного разговора.

Для повторения на другой машине: установить зависимости проекта с API/dev extras, запускать тест из корня репозитория или задать IMVERA_AUDIT_REPO. Для новой версии контрактов адаптировать вызовы в тесте, сохранив проверяемые пользовательские инварианты.
