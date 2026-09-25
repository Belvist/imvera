# PostgreSQL backup runbook (Stage 0)

## Что и где

- Скрипт: `scripts/pg_backup.py` (только pg_dump/pg_restore, кода продукта не касается).
- Куда: `IMVERA_BACKUP_DIR` (дефолт `.run/backups/`), файлы `imvera-<UTC>.dump`.
- Сколько хранить: `--keep N` (дефолт 14), старые удаляются автоматически.
- Проверка: каждый бэкап верифицируется через `pg_restore --list`; пустой —
  удаляется, скрипт падает с ненулевым кодом (молчаливого «бэкапа нет» не бывает).

## Ручной запуск

```sh
python3 scripts/pg_backup.py --keep 14
# backup ok: .run/backups/imvera-....dump (X MB, N entries)
```

## Восстановление (проверка)

```sh
pg_restore --list .run/backups/imvera-<stamp>.dump | head
# полный restore — только в пустую БД:
createdb imvera_restore && pg_restore -d imvera_restore .run/backups/imvera-<stamp>.dump
```

## Расписание (следующий шаг среза 0)

- launchd/cron ежедневно ночью + алерт, если свежего бэкапа нет >26 часов.
- Пока НЕ настроено — бэкапы делаются вручную перед каждым срезом стадии 0.
