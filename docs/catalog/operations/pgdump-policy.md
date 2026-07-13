# pg_dump policy — бэкап перед каждым write

**Свежий pg_dump обязателен перед КАЖДЫМ write** (enrich / recategorize / new option /
new leaf). Не переиспользовать старый дамп «этого дня».

## Команда (staging)
```bash
ssh taximeter@dev.proff58.ru 'cd ~/proff58-staging && \
  BACKUP_DIR=/home/taximeter/backups/staging bash scripts/backup.sh' 
# → db-YYYY-MM-DD-HHMM.sql.gz  (+ media-...tgz)
```

## Правила
- Путь дампа **фиксируется в post-audit и в roadmap-доке** (напр. `db-2026-07-13-2136.sql.gz`).
- Дамп снимается **после** отдельного ОК на write, **до** открытия транзакции.
- Volume БД staging непрерывен (не пересоздаётся) → дампы = реальные точки восстановления.
- Дампы лежат на стенде в `/home/taximeter/backups/staging/`.

## Зачем каждый раз
Между операциями состояние БД меняется (предыдущий write, чужие изменения). Дамп «до
именно этой операции» гарантирует корректную точку отката вместе с
[rollback-map](rollback.md).
