# Batch-50 — закрытие контрольного прогона catalog processing pipeline

Статус: **принят с зафиксированным risk exception** (2026-07-20). Контрольный
прогон на 50 товарах (п. 3 Phase 5 роадмапа) завершён end-to-end:
research → import → moderation → apply → finalize. Run закрыт со
`status=completed` (`outcome=completed_with_review`); каталог изменён строго в
утверждённом объёме (35 значений `tool_type`).

Risk exception: standalone tool-type precision batch-50 = **97,22% (35/36)** —
ниже gate 98% из §18 роадмапа. Combined с пилотом batch-20 = **98,04% (50/51)**,
gate формально пройден. Владелец продукта 2026-07-20 принял Phase 5 с явной
фиксацией этого риска; пересчёт как 35/35 (исключая rejected proposal)
не выполнялся и не признаётся.

## Идентификаторы

- Run UUID: `aa9b1df5-41c5-4b10-a6d8-957c2ff57aa9`
- Idempotency key run: `batch50-20260719-v1` (kind=research, mode=tool_type)
- Export checksum (SHA-256): `4104cd25d2fbaa9c1fe4c3598bf239b739dca91f931b95dfd2288f5a0cdbd115`
- Taxonomy hash (327 allowed options): `7327dfee9a56739a6e1b52c29ba824359e4e7c396d3fdb3646dbb65040e07549`
- Result checksums (SHA-256, по блокам):
  B1 `3da886bd…6825c9`, B2 `7a2e5cee…996a19`, B3 `f9ed31f6…a12ba0`
  (после QA-коррекции 35610; прежний `d6878a97…fd644` аннулирован без commit),
  B4 `24018a4f…67f3f29a`, B5 `edc9153e…1ec550`
- Finalize: 2026-07-20T15:08:57Z, `outcome=completed_with_review`; повторный
  вызов — безопасный no-op (`already_finalized=true`, состояние байт-идентично
  pre-finalize snapshot)
- Reviewer/actor: user `id=1`; все решения только через `review_catalog_change` /
  `apply_catalog_change` — никаких прямых ORM-update
- Код: staging `dev@3ea37ad` (после внешнего deploy в B4, см. инциденты);
  reject-path fix — PR #542 (`dev@cec503a`)

## Состав выборки

50 товаров, зафиксированных в shortlist до research (checksum manifest
`a2699b18…a7d7`): 30 clean / 10 medium / 10 adversarial; 39/50 is_site_v2;
27 без effective CA (отдельная readiness-метрика); frozen tags
`prior_family_exposure=true` у 9 товаров (novel 41 / family-repeatability 9).
Пять блоков по 10 (6 clean + 2 medium + 2 adversarial), состав перемешан и
зафиксирован до research.

## Итоговое состояние run

- items: **35 completed + 15 needs_review** (все 50 терминальны;
  pending/processing/failed = 0)
- changes: **35 applied + 1 rejected** (все 36 финальны; proposed/approved = 0)
- PAV: 60 861 → **60 896** (+35, ровно по числу applied; каждый — ровно один
  `tool_type` PAV с `source=web` и confidence из change)
- старые runs (`f7fe5b29…` batch-20, `9a26366e…` пилот/remediation) не изменены
- `FEATURE_CATALOG_PROCESSING=False` после каждой операции; web пересоздан;
  `/healthz/` → 200

## Метрики batch-50

| Метрика | Значение |
|---|---|
| proposal coverage | **36/50 = 72%** |
| moderator acceptance | **35/36 = 97,22%** |
| applied yield | **35/50 = 70%** |
| research abstention | **14/50 = 28%** |
| rejected proposals | **1/50 = 2%** (25954) |
| operational non-applied | **15/50 = 30%** |
| rules agreement / precision | **4/4** (B1:1, B2:0, B3: 26864, B4: 26865, B5: 27251) |
| family-repeatability | applied **7/9**, abstention 2/9 (12956, 13002) |
| novel | applied **28/41**, abstention 12/41, rejected 1/41 |
| clean | applied **27/30** |
| medium | applied **3/10** |
| adversarial | applied **5/10** |
| identity precision (все matched) | **46/46 = 100%** (partial: 302, 6009, 35610; mismatch: 29878) |
| tool-type precision (контракт) | **35/36 = 97,22%** — ниже standalone gate 98% |
| research time (50 durations) | median **162,5 c**, p90 **341 c** (nearest-rank), total 10 089 c |

## Combined batch-20 + batch-50

- proposed: **51/70**; correct/approved: **50/51 = 98,04%**
- moderator acceptance: **50/51 = 98,04%**
- applied yield: **50/70 = 71,43%**; research abstention: **19/70 = 27,14%**
- run `9a26366e` (4 applied, пилот/remediation) в combined не входит

## Оценка против gate Phase 5 (§18 роадмапа)

- identity precision ≥ 99%: **100%** по заявленным matched (46/46; ни одна
  matched identity не опровергнута; QA-коррекция 35610 понижена до partial до
  commit) — пройдено
- tool_type precision ≥ 98%: **97,22%** — **НЕ пройдено standalone; принято
  через risk exception** (combined 98,04%)
- moderator acceptance ≥ 90% на двух batch: **97,22% / 100%** — пройдено
- 0 прямых/неподтверждённых изменений: **0** — пройдено (все записи только
  через сервисы с evidence; importer создавал только pending/proposed)
- 100% baseline-конфликтов заблокировано: конфликтов **0**, все 35 apply прошли
  baseline pre-check — пройдено

## Причины review / reject

- **Taxonomy gaps (11)**: 168 (досмотровые/инспекционные зеркала), 18
  (нагрузочные вилки / тестеры АКБ), 177 (компрессометры), 35608 (воронки),
  12956 + 13002 (динамометрические ключи — системный gap, расходится с
  прецедентом Phase 5 `klyuchi-gaechnye`), 1786 (лодочные моторы), 35610
  (мерные ёмкости для техжидкостей; + identity partial), 36189 (ледоступы),
  35895 (ESD-браслеты), 36135 (клипсы FastClip)
- **Identity partial (3)**: 302 (бренд САТ недоказуем), 6009 (внутренний SKU
  РСВ498855 vs ASC2002 источников), 35610 (title F-5 vs артикул F-2)
- **Identity mismatch (1)**: 29878 (артикул C2517 фильтра CHAMPION ≠ название
  пожарной сетки СВ-80)
- **Rejected proposal (1)**: 25954 → `raskhodniki-pajki` отклонён: отсос припоя —
  многоразовый инструмент, не расходник; подходящего option нет (de-facto gap).
  Facet-gap rate: 11/50 = 22% (12/50 = 24% считая 25954)

## Source distribution

78 evidence entries у 36 changes (только HTTPS): specialized_store 57,
distributor 12, manufacturer 8, manufacturer_pdf 1 (подтип manufacturer в
рамках source policy). Source policy соблюдена: zubr-rus.ru, service-kluch.com,
stayer-stock.ru, kraftool-* — specialized_store; manufacturer только при
дословном доказанном статусе (zubr.ru, ptk-svarka.ru, magdistar.ru,
champion.ru).

## Инциденты и QA-коррекции

- **B4**: внешний staging deploy PR #546–#556 (`3ea37ad`) пересоздал web с
  `FEATURE_CATALOG_PROCESSING=False` во время окна commit; apps/catalog и
  миграции не затронуты, инварианты перепроверены, commit выполнен после
  повторного recreate.
- **Rejection-path blocker (B2)**: `review_catalog_change(rejected)` оставлял
  item в `processing` без терминального перехода. Исправлено в PR #542
  (`cec503a`): reject + item-transition в одной транзакции,
  `select_for_update`, replay лечит stranded state, regression-тесты,
  миграций нет. 25954 отклонён после deploy fix; повторный reject —
  идемпотентный no-op (проверено на staging).
- **B1 raw contract violation (1)**: товар 18 — исходный `researched` с пустым
  `changes=[]`, нормализован в `review` (`raw_contract_violation_count=1`).
- **Semantic/source-policy QA corrections**: B3 35610 (identity partial +
  отклонение широкого closest-fit `hoz-vedra`, result пересчитан до commit);
  B4 307 (source_type понижен distributor→specialized_store), 1855 (удалён
  неверифицированный факт); B5 6009 (identity partial вместо proposed),
  38350 (HTTP-источник исключён), 22650/30225 (незагружаемые источники
  исключены, confidence понижена), 27251 (канонический URL manufacturer).

## Артефакты (staging `var/catalog-processing/`, SHA-256)

- `batch50-final-report.json` — `011c3b5bb179eeab9083ef791071a1981ab23c34f6541785e800dd5ea0e3d655`
- `post-finalize-snapshot.json` — `0705c69f81ed0fa22cb3b734531b6f0b2e8f09e1dbe9f7099ab0f5fc294e4b41`
- `pre-finalize-snapshot.json` — `32b9fde6f9b24057fe6adb549d61851210e62c9407f306e1aeecccde7af18d1d`
- per-block metrics: `batch50-b1..b5-metrics.json`; backups pg_dump перед
  каждым commit/moderation/apply/finalize (sha256 в metrics-файлах)

## Follow-ups (вне scope закрытия)

- Phase 6: proposal-only/shadow план — `docs/plans/2026-07-20-PHASE6_PROPOSAL_SHADOW_PLAN.md`
- Решения по taxonomy gaps (11 типов + отсос припоя) — отдельными ADR/options,
  массового создания options без решения не было
- 15 needs_review items остаются в run для будущего разбора после taxonomy
  решений; run закрыт как `completed_with_review`
