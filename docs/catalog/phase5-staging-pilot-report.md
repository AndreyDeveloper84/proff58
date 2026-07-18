# Phase 5 — staging-пилот catalog processing pipeline

Статус: **технически принят** (2026-07-18). Pipeline research queue → import →
moderation → apply прошёл end-to-end на staging; каталог изменён строго в
утверждённом объёме (15 значений `tool_type`).

## Идентификаторы

- Run UUID: `f7fe5b29-9e2c-4dfb-898c-22859a0dcf35`
- Idempotency key run: `phase5-staging-20260718-v1` (kind=research, mode=tool_type)
- Код: `dev@7b24aae` (PR #533 — processing foundation + research queue,
  PR #534 — fix перехода `review` → `needs_review`)
- Export checksum (SHA-256): `4ca129e595fa5ddccd3e3b979d573854fbea4221558d20985a0cb61b63e5fb29`
- Result checksum (SHA-256): `a2ec6286f8f624b5c04a00d0bf3c4da596d80edfd3873e2c77f223c2fb7d1dc8`
- Reviewer: user `id=1` (staging superuser); все решения только через
  `review_catalog_change` / `apply_catalog_change` (никаких прямых ORM-update)

## Backups (перед каждым write-блоком, pg_dump | gzip)

| Точка | Файл (`/home/taximeter/proff58-staging/backups/`) | Размер, байт | SHA-256 |
|---|---|---|---|
| pre-apply block 1 | `staging-phase5-pre-apply-block1-20260718-200202.sql.gz` | 21 367 620 | `1a553e184d3502b6a29f0400e887406fe1a04149481f625f7cce9c135a3f0506` |
| pre-apply block 2 | `staging-phase5-pre-apply-block2-20260718-201714.sql.gz` | 21 367 937 | `4f0cdd14cb0e57bdd2ac7d1080bcb7ef8c8f16f3a4daef28420897264364e12c` |
| pre-apply block 3 | `staging-phase5-pre-apply-block3-20260718-202326.sql.gz` | 21 367 664 | `4af144ea0fea35a9d62d1f48855763fbbe001b4dec94fe8f3505c2ba5a282e05` |

Backup блока 1 дополнительно проверен полным restore'ом во временную БД
(счётчики совпали с live); gzip integrity и маркер `\unrestrict` проверены у всех.

## Исходные когорты shortlist v2 и результаты

Когорты зафиксированы в исходном shortlist и не менялись после получения
результата.

| Когорта | Товары | Applied | Abstain | Доля applied |
|---|---|---|---|---|
| Clean (9) | 6682, 12957, 12959, 13936, 28891, 28901, 36377, 36713, 30870 | 8 | 1 (30870) | 88,9% |
| Medium (6) | 10537, 23255, 36304, 26863, 32407, 27250 | 3 | 3 | 50% |
| Adversarial (5) | 37594, 24523, 6681, 35076, 31109 | 4 | 1 (24523) | 80% |
| **Итого (20)** | | **15** | **5** | **75%** |

Abstention rate: **25%** (5/20). Все abstention — taxonomy gaps, ушли в
`needs_review` без создания CatalogChange (корректное поведение).

Confidence применённых: 95×5, 92×1, 90×4, 88×2, 85×2, 80×1.

## Применённые изменения (15)

| product | tool_type slug | conf | | product | tool_type slug | conf |
|---|---|---|---|---|---|---|
| 6681 | adaptery | 95 | | 23255 | krep-shaiby | 88 |
| 6682 | adaptery | 90 | | 28891 | bp-pnevmosteplery | 90 |
| 10537 | adaptery | 92 | | 28901 | bp-pnevmosteplery | 88 |
| 12957 | klyuchi-gaechnye | 85 | | 31109 | svar-reduktory | 80 |
| 12959 | klyuchi-gaechnye | 85 | | 35076 | trosorezy-kabelerezy | 95 |
| 13936 | otvertki | 95 | | 36304 | siz-ochki | 90 |
| 36377 | siz-ochki | 95 | | 36713 | sumki-poyasnye | 90 |
| 37594 | plitkorezy | 95 | | | | |

## Quality gates (все пройдены)

- 0 ошибок identity; 0 значений вне 325 allowed_options; 100% HTTPS evidence;
- 15/15 PAV совпали с approved changes (slug, source=web, confidence);
  `attrs_cache["tool_type"]` = отображаемому значению option;
- Product/PAV baseline без drift на каждом шаге (price, stock, category, name,
  прочие PAV и attrs_cache неизменны); итоговый PAV count: 60 842 → 60 857 (+15);
- идемпотентность: replay import безопасно отклонён; `idempotency_key` всех 15
  changes пересчитан и совпал;
- API spot-check (`/api/catalog/products/<slug>/`): tool_type отдаётся витриной;
- `/healthz/` HTTP 200 после каждого блока; apply-ошибок в логах нет.

## Unresolved taxonomy gaps (5)

| product | Предметная область |
|---|---|
| 24523 | Осветительные мачты |
| 32407 | Сантехнические/трубные ключи |
| 26863 | Шплинты |
| 27250 | Пусковые провода |
| 30870 | Сварочные кабели в сборе |

Options НЕ создавались. Перед созданием — read-only gap analysis по всему
каталогу (особенно: сварочный кабель vs `svar-klemmy`; трубные ключи vs
`klyuchi-gaechnye`/`spetsialnye-klyuchi`; осветительная мачта vs
`svetilniki`/`prozhektory`).

## Состояние на конец пилота

- run `f7fe5b29…` остаётся `running`: 15 items `completed`, 5 `needs_review`.
  Run через ORM не закрывался — операции финализации смешанного результата пока
  нет (см. follow-up `catalog_queue_finalize`).
- `FEATURE_CATALOG_PROCESSING=False` на staging (2026-07-18): `.env` сохранён
  (`.env.bak-20260718-phase5-disable`), web пересоздан, настройка проверена
  (`settings.FEATURES["catalog_processing"] is False`), healthz 200, каталог
  без изменений после пересоздания.

## Follow-ups

1. Regression-тест (параметризованный): `changes` при
   `identity.status ∈ {partial, unknown, mismatch}` отклоняются importer'ом.
2. `catalog_queue_finalize` / `finalize_catalog_processing_run()`:
   блокировка run/items/changes; запрет при pending/processing items и
   proposed/approved changes; `status=completed`, `finished_at`, статистика
   `outcome=completed_with_review`; идемпотентность + тест конкурентного
   вызова; без изменений Product/PAV.
3. Gap analysis по всему каталогу → решение по пяти taxonomy options.
