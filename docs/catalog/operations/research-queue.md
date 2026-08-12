# Research queue runbook — файловый обмен export/result

Операционные правила обмена JSON-артефактами research queue
(`catalog_queue_export` → `$catalog-research` → `catalog_queue_import`)
между хостом staging и web-контейнером. Workflow самой очереди —
в `$catalog-research` skill и [плане V2](../../plans/2026-07-17-CATALOG_RESEARCH_QUEUE_ROADMAP_V2.md).

## `./var:/app/var` — постоянный bind mount

`docker-compose.prod.yml` монтирует `./var` проекта в `/app/var` web-контейнера
(с PR #254, коммит `a4dc971`). Это **основной и единственный штатный путь**
обмена файлами:

- export, написанный командой в контейнере в `/app/var/catalog-processing/outbox/`,
  уже находится на хосте в `./var/catalog-processing/outbox/` — копировать не нужно;
- result JSON кладётся на хосте в `./var/catalog-processing/inbox/` —
  контейнер видит его как `/app/var/catalog-processing/inbox/` без копирования;
- mount переживает `docker compose up -d --no-deps --force-recreate web`
  (проверено в Phase 5 remediation, 2026-07-19). Файлы, записанные мимо mount
  (в слой контейнера), при recreate пропадают — поэтому писать только по mount-пути.

## Проверка mount перед операциями

```bash
docker inspect proff58_staging-web-1 --format '{{json .Mounts}}'
# ожидание: {"Type":"bind","Source":"/home/taximeter/proff58-staging/var",
#            "Destination":"/app/var",...}
```

Если bind `./var → /app/var` отсутствует — это инфраструктурный дефект:
остановиться до write-операций и разобраться с compose. **Не** заменять
mount ручным копированием в штатной процедуре.

## Права на артефакты

- каталоги `var/catalog-processing/{,inbox,outbox}` — `0700`;
- JSON-файлы export/result/snapshot — `0600`, владелец `taximeter`.

## Контроль checksum

- После export: `sha256sum` файла на хосте; значение фиксируется в отчёте.
- Перед import: `docker exec proff58_staging-web-1 sha256sum /app/var/catalog-processing/inbox/<run>.result.json`
  — обязан совпасть с хостовым.
- Importer выводит `result_checksum`/`export_checksum` — сверять с зафиксированными.

## docker cp — только аварийная диагностика

`docker cp` не входит в штатный контур. Допустим единственно как разовая
диагностика, если mount действительно отсутствует или сломан (см. выше —
это stop-condition, а не рабочий шаг).

## Feature flag protocol

`docker compose restart web` **не перечитывает** `.env`. Изменение
`FEATURE_CATALOG_PROCESSING` применяется только пересозданием:

```bash
docker compose -f docker-compose.prod.yml up -d --no-deps --force-recreate web
```

После пересоздания проверить значение внутри контейнера
(`settings.FEATURES["catalog_processing"]`) и `/healthz/` → 200.

## Инцидент 2026-07-19 (закрыт как ошибка наблюдения)

В Phase 5 сложилось ошибочное убеждение, что `./var` не смонтирован, и export/result
копировались через `docker cp`. Проверка `docker inspect` показала действующий
bind mount; расхождение закрыто как ошибка наблюдения, дефекта инфраструктуры нет.
Этот runbook фиксирует правильную процедуру.
