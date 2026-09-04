# Cursor Agent Configuration (MossVoice)

Инструкции для AI-агентов в этом репозитории. Читается автоматически Cursor'ом.

## Rules (всегда активны)

| Файл | Назначение |
|------|------------|
| `rules/zero-stubs-production-code.mdc` | Запрет заглушек, псевдокода, fake success |
| `rules/engineering-architecture-first.mdc` | Сначала модель и FSM, потом код |
| `rules/security-and-fail-secure.mdc` | Безопасность, IDOR, fail-closed |
| `rules/staff-engineer-verification-loop.mdc` | OBSERVE→REVERIFY; DoD; не «готово» без proof |

## Skills (подключаются по задаче)

| Skill | Когда использовать |
|-------|-------------------|
| `skills/engineering-architecture/` | Новый модуль, рефакторинг, state machine |
| `skills/anti-stub-enforcement/` | Проверка полноты реализации |
| `skills/deep-implementation-workflow/` | Любая нетривиальная фича end-to-end |
| `skills/staff-engineer-verification-loop/` | Task contract, матрица проверок, финальный отчёт |

## Проверка перед коммитом

```bash
make verify-stubs    # новые заглушки (legacy в baseline.txt)
make test-fast       # офлайн-тесты
```

Сканер: `baseline.txt` — 35 известных legacy-нарушений; падает только на **новые**.

## Связь с AGENTS.md

`AGENTS.md` — долгосрочная память проекта (стек, инциденты, гейты).
`.cursor/` — **как** агент должен писать код (инженерный стандарт).

Оба обязательны перед задачей.
