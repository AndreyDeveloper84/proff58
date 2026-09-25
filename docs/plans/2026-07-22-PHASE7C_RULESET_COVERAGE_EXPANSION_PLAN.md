# Phase 7C: Ruleset Coverage Expansion (tool_type.v2) — план на утверждение

> Статус: PROPOSED v2 (rework по ревью пользователя: 6 замечаний закрыты). Исполнение НЕ авторизовано — go/no-go checkpoint.
> Прецеденты процесса: Phase 7A (corpus + candidate rules), 7A.2 (DEVIATION-2 remediation, PR #584), 7B (shadow gate → COMPLETED AS OBSERVATIONAL BASELINE).
> Входные условия: Phase 7B CLOSED 2026-07-22; ruleset `tool_type.v1` и corpus v1 frozen; staging-инварианты на момент закрытия 7B зелёные; «Phase 7B больше не должна переоткрываться ради расширения правил» (решение пользователя 2026-07-22).

## 0. Что изменилось со времён Phase 7B и почему 7C нужна

Phase 7B доказала работоспособность matcher-контура (0 collisions, overlap-check чист, replay-детерминизм, drift отсутствует), но официальный precision gate не состоялся: predictions=19 на пуле in-stock и predictions=63 на максимальном пуле all при MIN_ROWS_GATE=100 (`apps/catalog/management/commands/catalog_rules_gate_validate.py:24-25`). Причина — покрытие ruleset: 63/1593 = 3.95% eligible каталога. Качество ruleset не подтверждено и не опровергнуто; ruleset остаётся candidate-tier.

Цель Phase 7C (формулировка пользователя 2026-07-22): «вывести число новых независимых predictions минимум к 120–150, чтобы после overlap-фильтрации, коллизий и возможных исключений гарантированно осталось не менее 100 строк для официального gate». Цель — **коридор 120–150, а не бинарный порог**: при недостижении 120 решающим является доказанность исчерпания устойчивых кластеров (см. F-7).

7C производит ruleset `tool_type.v2` с доказанным покрытием. Сам официальный gate (разметка ≥100 строк + `catalog_rules_gate_validate`) — **следующая фаза (7D), вне scope 7C**.

## 1. Точный scope

Phase 7C — **наблюдательная + derivation** фаза. Записей в БД нет ни на одном шаге.

Входит:

1. Read-only экспорт no_match-товаров пула all (1530 по baseline 7B) через канонический engine (D-1(a), временный инструмент — см. Stage 1).
2. Локальный derivation-анализ: кластеры no_match → кандидатные правила.
3. Per-rule human review кандидатов (как Stage 7 в Phase 7A).
4. Сборка `data/catalog_processing_rules/tool_type.v2.json` (v1 правила verbatim + утверждённые новые + новые negative fixtures).
5. Полная локальная валидация v2 (schema/semantics, fixtures, taxonomy, corpus regression, взаимный overlap новых правил).
6. Re-pinning v2 (byte sha256 LF/Git + canonical `ruleset_hash`) и заморозка.
7. Staging shadow-прогон v2 на pool=all (read-only) + replay-детерминизм (sample **и** per-rule счётчики) + регрессия v1-предсказаний.
8. Coverage verdict: число новых независимых predictions vs целевой коридор 120–150 (при недостижении — с доказательством исчерпания кластеров, см. F-7).
9. Протокол исполнения + Human Decision Log (`scratchpad/phase7c/phase7c-report.md`).

НЕ входит (явный non-scope):

- официальный precision gate, разметка, `catalog_rules_gate_validate` как вердикт — Phase 7D, отдельная авторизация;
- промоушен ruleset (candidate → production tier — такого tier нет в коде; отдельная фаза ПОСЛЕ gate-вердикта);
- создание/изменение `Attribute`, `AttributeOption` и любой таксономии (см. F-3);
- изменение corpus v1 и `expected_recall=0.59` (re-approval flow — отдельно, по 7A §6.4);
- изменение matcher, `rules_engine.py`, JSON-схем, `MATCHER_VERSION` (остаётся `"1.0"`);
- изменение `tool_type.v1.json` и 7A pinned taxonomy export;
- превращение D-1(a) скрипта в постоянный интерфейс (см. Stage 1);
- применение predictions к каталогу;
- изменение пула, deploy, миграции, feature flags;
- коммиты без явной авторизации на checkpoint (см. Stage 4).

## 2. Входные артефакты

| Артефакт | Путь | Pinned hash / версия |
|---|---|---|
| Ruleset v1 (frozen, только чтение) | `data/catalog_processing_rules/tool_type.v1.json` | byte sha256 (LF/Git) `b476199afaf83e7f305d335d7ed2c77d855469f59fd73dbfe357c9183d7d1e6e`; canonical `ruleset_hash` `51b3bbad7c65565637711e5bf9ee74eb7b477ff71b9e25183095ede9cb1044bd` |
| Corpus v1 (frozen, только чтение) | `data/catalog_processing_rules/applied_corpus_tool_type.v1.json` | byte sha256 (LF/Git) `6663a6fe48c2c2656604a179c1f70338a08a9d3e2a364a5ec2f663600b85d6e3`; `corpus_id` `staging-tool-type-6ebb8ac9d856`; `expected_recall` 0.59 |
| 7A pinned taxonomy export | `data/catalog_processing_rules/tool_type_taxonomy_export.v1.json` | **Исторический артефакт, НЕ вход для валидации** (см. §6): содержит pre-7A.2 дубль `steplery`; `_taxonomy_hash` = `1100482c4c074499cf3950d902de84e1afe70c0e80b6ee363c777a4b7c1f5a9f` ≠ staging |
| Staging taxonomy (авторитетная) | живой staging, read-only | `_taxonomy_hash` = `b357be604801197e33182b84fde1755361e29653d98bd49429623b3ba604326b` (подтверждён в 7B дважды; re-check в Stage 0) |
| 7B baseline (pool=all) | `scratchpad/phase7b/phase7b-shadow-report-pool-all.json` | sha256 `ba60e2d9b9a23353a2c5d9d713a3d3e4692b35f21f98cd898a3f4045df1ee0a9`; content_hash `b9e31a65…`; pool=1593, predictions=63, no_match=1530, excluded=18123, `input_universe_hash` `82536a4698688c927f6decd35787d1bb0d3deb8f3c298f698f9bf6387b749db8` |
| 7B gate sample (pool=all) | `scratchpad/phase7b/phase7b-gate-sample-pool-all.json` | sha256 `c4d2bcc8818c1ce0c58227f334033353f1cc26fbac12ab3eb5926919c18c3526`; canonical_hash `2e1a684c…`; 63 строки = полный список v1-предсказаний |
| Staging code | контейнер `proff58_staging-web-1` | ветка dev post-#584; изменений кода в 7C нет |

Gate-константы из кода (не из плана), для контекста 7D: `PRECISION_GATE = 0.99`, `MIN_ROWS_GATE = 100` (`catalog_rules_gate_validate.py:24-25`).

Ключевые свойства engine, на которые опирается план (проверено по коду):

- `apps/catalog/schemas/tool_type_ruleset_v1.json`: `version` = const 1; `ruleset_id` pattern `^tool_type\.v[0-9]+$` → файл `tool_type.v2.json` с `"version": 1, "ruleset_id": "tool_type.v2"` валиден под **существующей** схемой (schema version ≠ ruleset version, doctrine 7A §6.1). Изменений схемы и кода не требуется.
- Семантические проверки `load_ruleset` (обязательны для новых правил): candidate tier → ≥2 непустых измерения; ≥2 уникальных положительных `derived_from`; каждое candidate-правило покрыто ≥1 negative fixture; ключи ≥3 символов после normalize; уникальность значений в измерении; запрет дублирующих предикатов между правилами; fixtures ссылаются на существующие `rule_refs`.
- `validate_against_taxonomy(ruleset, allowed_slugs)` — чистая функция без БД (`rules_engine.py:336`).
- Экспорта no_match в `catalog_rules_shadow` **не существует** → Stage 1 использует отдельный read-only скрипт через канонические code paths (D-1).

## 3. Разрешённые операции

- Read-only SELECT и read-only shell на staging (`REPEATABLE READ READ ONLY` / `transaction_read_only=on`).
- `docker cp` **новых** файлов в `/app/logs/` контейнера (скрипт анализа, копия v2 ruleset); создание выходных файлов `/app/logs/phase7c-*`. Существующие файлы контейнера (в т.ч. `/app/data/*`) не изменяются.
- Локальное создание/редактирование: этот план, `docs/catalog/phase7c-ruleset-v2-derivation.md`, `data/catalog_processing_rules/tool_type.v2.json`, `scratchpad/phase7c/*`.
- Локальный запуск pytest и python-валидаций.
- `git commit` — **только после явной авторизации** на checkpoint Stage 4.

Запрещено: любые INSERT/UPDATE/DELETE на staging; миграции; изменение кода, схем, matcher, corpus, v1 ruleset, 7A export, таксономии; deploy; feature flags; pool=all для каких-либо иных целей, кроме заявленных shadow-прогонов; повторное использование D-1(a) скрипта вне Phase 7C; коммиты/PR без авторизации.

## 4. Ожидаемые изменения данных

В БД — **никаких**.

Canonical deliverables:

| Файл | Где | Содержимое |
|---|---|---|
| `tool_type.v2.json` | repo `data/catalog_processing_rules/` | v1 правила + fixtures verbatim + новые утверждённые правила и fixtures; `"version": 1`, `"ruleset_id": "tool_type.v2"` |
| `phase7c-ruleset-v2-derivation.md` | repo `docs/catalog/` | derivation doc v2: метод, per-rule обоснования, pin table, Human review history |
| `phase7c-report.md` | `scratchpad/phase7c/` | протокол исполнения + Human Decision Log |
| `phase7c-nomatch-pool.json` | `scratchpad/phase7c/` | read-only dataset no_match пула all (Stage 1) |
| `phase7c-taxonomy-snapshot.json` | `scratchpad/phase7c/` | read-only снимок staging taxonomy (Stage 0), референс валидации |
| `phase7c-shadow-report-v2-pool-all.json` | `scratchpad/phase7c/` | shadow v2 report (Stage 5) |
| `phase7c-gate-sample-v2-pool-all.json` | `scratchpad/phase7c/` | gate sample v2 (evidence; официальный sample — в 7D) |

Temporary verification artifacts (не deliverables; удаляются при rollback/завершении):

- `scratchpad/phase7c/phase7c-shadow-report-v2-pool-all-replay.json`, `phase7c-gate-sample-v2-pool-all-replay.json` (Stage 5 replay);
- `scratchpad/phase7c/tool_type.v2.lf.json` (LF-копия для docker cp, Stage 5.1);
- `scratchpad/phase7c/extract_nomatch.py` (D-1(a), временный инструмент — см. Stage 1), `scratchpad/phase7c/replay_v2_vs_corpus.py`, `scratchpad/phase7c/dryrun_v2_overlap.py`, скрипты сводок Stage 2;
- контейнерные `/app/logs/phase7c-*` (копия скрипта, копия v2 ruleset, снимок таксономии, выходные JSON).

## 5. Dry-run и rollback contract

Все staging-операции read-only; записей в БД нет — восстанавливать нечего.

Rollback = удаление артефактов по инвентарю §4 (repo-файлы `tool_type.v2.json`, derivation doc; `scratchpad/phase7c/*` — включая `extract_nomatch.py`, который по D-1(a) является временным инструментом и не переживает фазу; контейнерные `/app/logs/phase7c-*`). `tool_type.v1.json` остаётся default `RULESET_PATH` (`rules_engine.py:30`) и не изменяется — после rollback система байт-в-байт в состоянии post-7B.

Fail-closed свойства сохраняются: `--out`/`--gate-sample-out` без `--force` падают при существующем файле; `load_ruleset` отклоняет невалидный v2; `check_negative_fixtures` непустой → `CommandError`.

## 6. Подтверждение: 7C не изменяет v1-контур и не требует изменений кода

1. Default `RULESET_PATH` → v1 (`rules_engine.py:30`); v2 потребляется только явным `--ruleset` флагом shadow-команды.
2. JSON-схема `tool_type_ruleset_v1.json` допускает `ruleset_id="tool_type.v2"` при `version: 1` — схема и `MATCHER_VERSION="1.0"` не меняются; gate-артефакты v2 совместимы по `matcher_version` с контрактом labels.
3. Corpus v1 и `expected_recall=0.59` не изменяются; существующий replay-тест (`test_rules_corpus_replay.py:37-48`) ссылается на v1 пути явно и обязан остаться зелёным (Stage 3.6).
4. 7A pinned taxonomy export — **не референс валидации**: он зафиксировал pre-7A.2 таксономию (328 строк / 327 уникальных slug, обе записи `steplery` — строки 961–967 файла) и его `_taxonomy_hash` `1100482c…` ≠ staging `b357be60…`. Референс 7C — свежий read-only снимок staging taxonomy (Stage 0), сверенный по `b357be60…`.
5. v1-правила в v2 копируются verbatim (включая `derived_from` corpus-ID) — регрессия v1-предсказаний проверяется в Stage 3.5 (corpus) и Stage 5.5 (shadow).

Следовательно: 7C добавляет ровно один data-артефакт + документацию; код, схема, corpus, таксономия, v1 ruleset вне изменений.

## 7. Stages и команды

### Stage 0 — pre-checks (staging, read-only)

- [ ] **0.1** Инвариант дублей (psql, `BEGIN TRANSACTION READ ONLY`): `SELECT attribute_id, slug, COUNT(*) FROM catalog_attributeoption WHERE slug <> '' GROUP BY 1,2 HAVING COUNT(*)>1;` → 0 rows (иначе F-1).
- [ ] **0.2** id=16 = `steplery-i-zaklepochniki`, id=73 = `steplery` (иначе F-1).
- [ ] **0.3** Counters: PAV=60896; tt_options=328; CatalogChange total=57 / tool_type applied=56; CatalogProcessingRun=4. Отклонение → F-1 (STOP; пересмотр baseline — только решением пользователя).
- [ ] **0.4** Staging taxonomy_hash: `docker exec proff58_staging-web-1 python manage.py shell -c "from apps.catalog.queue_contract import _allowed_tool_type_options, _taxonomy_hash; print(_taxonomy_hash(_allowed_tool_type_options()))"` → `b357be60…` (иначе F-1).
- [ ] **0.5** Снимок таксономии (read-only, новый файл в `/app/logs`):

```bash
docker exec proff58_staging-web-1 python manage.py shell -c "
import json
from apps.catalog.queue_contract import _allowed_tool_type_options, _taxonomy_hash
opts = _allowed_tool_type_options()
payload = json.dumps({'count': len(opts), 'options': opts}, ensure_ascii=False)
open('/app/logs/phase7c-taxonomy-snapshot.json', 'w', encoding='utf-8', newline='').write(payload)
print(len(opts), _taxonomy_hash(opts))
"
```

Ожидание: `328 b357be60…` (иначе F-1). Забрать файл локально в `scratchpad/phase7c/phase7c-taxonomy-snapshot.json`; локальный `_taxonomy_hash` снимка == `b357be60…`. Этот снимок (формат `{"count", "options":[{"slug","value"}]}`) — референс валидации Stage 3.
- [ ] **0.6** Контейнерные входные артефакты: `sha256sum /app/data/catalog_processing_rules/tool_type.v1.json` == `b476199a…`, `…/applied_corpus_tool_type.v1.json` == `6663a6fe…` (иначе F-1).
- [ ] **0.7** Code-level: `docker exec proff58_staging-web-1 git rev-parse HEAD` == deployed dev post-#584 (зафиксировать в протоколе; drift → F-1).

STOP-условие Stage 0: любой drift инвариантов/хэшей → фаза не начинается, отчёт пользователю.

### Stage 1 — no_match extraction (staging, read-only, snapshot tx)

Метод — D-1(a): отдельный скрипт в контейнере через **канонические** code paths shadow-команды (`_pool_queryset`, `SNAPSHOT_SQL`, `ProductFacts`, `evaluate_product`, `load_ruleset`) — расхождения с matcher нет по построению. Альтернативы отклонены: (b) новый `--no-match-out` флаг — изменение кода + deploy; (c) переиспользование ORM без engine — риск расхождения matcher.

**Ограничение D-1(a): скрипт — временный исследовательский инструмент Phase 7C, а не интерфейс.** Он сознательно импортирует приватные функции management-команды; это скрытая связность, допустимая только на время фазы. Запрещено: использовать скрипт как постоянный интерфейс; повторно использовать его вне Phase 7C. После окончания 7C скрипт удаляется (rollback §5). Если такой экспорт понадобится ещё хотя бы один раз — проектирование публичного API / management command выносится в отдельную архитектурную фазу.

- [ ] **1.1** Создать локально `scratchpad/phase7c/extract_nomatch.py`:

```python
"""Phase 7C Stage 1: экспорт no_match товаров pool=all (read-only, snapshot tx).

ВРЕМЕННЫЙ инструмент Phase 7C (D-1(a)): не постоянный интерфейс;
после завершения фазы удаляется. Повторное использование вне 7C —
только через отдельную архитектурную фазу (публичный API/command).

Запуск только в staging-контейнере: python /app/logs/phase7c-extract-nomatch.py
DJANGO_SETTINGS_MODULE берётся из окружения контейнера.
"""
import hashlib
import json

import django

django.setup()

from django.db import connection, transaction

from apps.catalog.management.commands.catalog_rules_shadow import (
    SNAPSHOT_SQL,
    _pool_queryset,
)
from apps.catalog.rules_engine import ProductFacts, evaluate_product, load_ruleset

RULESET = "/app/data/catalog_processing_rules/tool_type.v1.json"
OUT = "/app/logs/phase7c-nomatch-pool.json"

rs = load_ruleset(RULESET)
rules = [r for r in rs.rules if r.tier == "candidate"]
rows = []
with transaction.atomic():
    with connection.cursor() as cur:
        cur.execute(SNAPSHOT_SQL)
    qs = _pool_queryset("all")
    pool_size = qs.count()
    for product in qs.iterator(chunk_size=500):
        facts = ProductFacts(
            product_id=product.pk,
            name=product.name or "",
            original_name=product.original_name or "",
            brand=product.brand or "",
            source_group=product.source_group or "",
            article=product.article or "",
            has_tool_type=getattr(product, "_has_tt", False),
        )
        verdict = evaluate_product(rules, facts)
        if verdict.status == "no_match":
            rows.append({
                "product_id": product.pk,
                "name": facts.name,
                "original_name": facts.original_name,
                "brand": facts.brand,
                "source_group": facts.source_group,
                "article": facts.article,
            })

payload = json.dumps(
    {
        "artifact": "phase7c_nomatch_pool",
        "pool": "all",
        "ruleset_id": rs.ruleset_id,
        "ruleset_hash": rs.ruleset_hash,
        "pool_size": pool_size,
        "count": len(rows),
        "rows": rows,
    },
    ensure_ascii=False,
    sort_keys=True,
)
with open(OUT, "w", encoding="utf-8", newline="") as fh:
    fh.write(payload)
print("no_match=%d pool_size=%d sha256=%s"
      % (len(rows), pool_size, hashlib.sha256(payload.encode("utf-8")).hexdigest()))
```

- [ ] **1.2** `docker cp scratchpad/phase7c/extract_nomatch.py proff58_staging-web-1:/app/logs/phase7c-extract-nomatch.py` (через ssh; новый файл, `/app/data` не затрагивается).
- [ ] **1.3** `docker exec proff58_staging-web-1 python /app/logs/phase7c-extract-nomatch.py` → ожидание `no_match=1530 pool_size=1593` (расхождение → F-2).
- [ ] **1.4** Забрать `/app/logs/phase7c-nomatch-pool.json` локально (`docker exec … cat` → `scratchpad/phase7c/phase7c-nomatch-pool.json`); локальный sha256 == stdout шага 1.3; `ruleset_hash` в файле == `51b3bbad…`; `count == len(rows)`.

### Stage 2 — derivation analysis (локально) + human checkpoint

Метод — analyst-curated (как v1, НЕ auto-mining): доктрина precision > recall; узкие правила допустимы; singleton без второго подтверждённого примера правила не получает (P0.2 сохраняется).

**Ограничение сложности новых правил** (защита от нагона coverage любой ценой):

- не более 3 измерений на правило (норма v1 = 2; третье — только с явным обоснованием в карточке правила);
- только существующие типы измерений engine (`brand_any`, `original_name_keywords_any`, `name_keywords_any`, `source_group_any`, `article_prefix_any`); экзотические признаки и новые механизмы запрещены;
- минимальное число keywords: каждый keyword обязан поднимать precision, а не recall; избыточные условия удаляются — правило должно быть **минимальной сложности, достаточной для целевой precision**;
- правило обязано быть объяснимым человеку одной фразой в «Почему slug»; необъяснимое правило отклоняется на review без анализа hits.

- [ ] **2.1** Группировка dataset по `source_group` → таблица counts в `scratchpad/phase7c/phase7c-nomatch-by-group.md`.
- [ ] **2.2** Частотный анализ токенов/биграмм `original_name` внутри групп (нормализация = `apps/catalog/tool_type.py:26` normalize: lowercase + ё→е) → список кандидатных кластеров (группа × устойчивый паттерн).
- [ ] **2.3** Маппинг кластеров на существующие slug'и снимка Stage 0.5 (328 options). Кластер без подходящего slug → список `taxonomy_gap` в derivation doc; **создавать options запрещено** (F-3).
- [ ] **2.4** Per-кандидат карточка (шаблон v1 derivation doc): Группа (≥2 product_id из dataset → `derived_from`); Измерения (≥2, с соблюдением ограничения сложности выше; по образцу v1: `source_group_any` + `original_name_keywords_any`); Почему slug; Риски (соседние товары группы с иной семантикой); draft negative fixture (реальный товар смежной группы с другой меткой или из corpus, `expected: "no_match"`); оценка hits.
- [ ] **2.5** Оформление proposals в `docs/catalog/phase7c-ruleset-v2-derivation.md` (per-rule секции `### N. <rule_ref> → <slug>` со статусом PROPOSED).
- [ ] **2.6** Оценка суммарного yield кандидатов vs коридор 120–150. Если оценка < 120 → сначала per-cluster разбор причин (какие сегменты остались singleton'ами, какие в taxonomy_gap, почему устойчивых паттернов больше нет); STOP по F-7 только при недоказанном исчерпании.
- [ ] **2.7** STOP → **per-rule human review** (APPROVED / APPROVED with monitoring / REJECTED с рецептом rework — как Stage 7 в 7A). Только APPROVED-правила идут в Stage 3.

### Stage 3 — v2 assembly + полная локальная валидация

- [ ] **3.1** Создать `data/catalog_processing_rules/tool_type.v2.json`: `"version": 1`, `"ruleset_id": "tool_type.v2"`, `"note": "draft, Phase 7C"`, v1 правила и fixtures **verbatim**, далее APPROVED-правила и их fixtures.
- [ ] **3.2** Schema+semantics (`DJANGO_SETTINGS_MODULE=config.settings.dev`, локальный venv): `load_ruleset('data/catalog_processing_rules/tool_type.v2.json')` → без исключений; напечатать `ruleset_hash` (ошибка → F-4, доработка и повтор).
- [ ] **3.3** `check_negative_fixtures(rs) == []` (иначе F-4).
- [ ] **3.4** `validate_against_taxonomy(rs, {o['slug'] for o in phase7c_taxonomy_snapshot['options']}) == []` (иначе F-4/F-3).
- [ ] **3.5** Corpus regression — `scratchpad/phase7c/replay_v2_vs_corpus.py` (паттерн `_replay` из `catalog_rules_shadow.py:525-560`):

```python
import django

django.setup()  # DJANGO_SETTINGS_MODULE=config.settings.dev

from apps.catalog.rules_engine import (
    TIER_CANDIDATE,
    ProductFacts,
    evaluate_product,
    load_corpus,
    load_ruleset,
)

rs = load_ruleset("data/catalog_processing_rules/tool_type.v2.json")
corpus = load_corpus("data/catalog_processing_rules/applied_corpus_tool_type.v1.json")
rules = [r for r in rs.rules if r.tier == TIER_CANDIDATE]
correct, wrong_slug, collisions = 0, [], []
for item in corpus.items:
    facts = ProductFacts(
        product_id=item.product_id,
        name=item.name,
        original_name=item.original_name,
        brand=item.brand,
        source_group=item.source_group,
        article=item.article,
    )
    verdict = evaluate_product(rules, facts)
    if verdict.status == "collision":
        collisions.append(item.product_id)
    predicted = verdict.option_slug if verdict.status == "prediction" else ""
    if predicted == item.applied_option_slug:
        correct += 1
    elif predicted:
        wrong_slug.append({
            "product_id": item.product_id,
            "expected": item.applied_option_slug,
            "predicted": predicted,
        })
print("correct=%d/%d collisions=%d wrong_slug=%d"
      % (correct, len(corpus.items), len(collisions), len(wrong_slug)))
if collisions or wrong_slug:
    raise SystemExit(1)
```

Критерий: `collisions == 0` и `wrong_slug == []` (любое попадание нового правила в corpus-товар с чужим slug — STOP F-5: правило слишком широкое); `correct >= 32` (baseline v1; рост за счёт новых правил допустим и фиксируется, но `expected_recall=0.59` в corpus-артефакте **не пересматривается** — re-approval flow вне scope).
- [ ] **3.6** Существующая rules-ветка тестов зелёная (v1 не тронут): `./.venv/Scripts/python.exe -m pytest apps/catalog/tests/test_rules_engine.py apps/catalog/tests/test_rules_corpus.py apps/catalog/tests/test_rules_corpus_replay.py apps/catalog/tests/test_rules_gate_validate.py apps/catalog/tests/test_rules_shadow_command.py apps/catalog/tests/test_rules_snapshot.py -q` → все PASS.
- [ ] **3.7** Взаимный overlap новых правил (pre-shadow, локально на dataset Stage 1) — `scratchpad/phase7c/dryrun_v2_overlap.py`. Так как dataset содержит только no_match-под-v1 товары, любое попадание здесь — попадание нового правила; критерий `new_rule_overlap == 0`: каждый prediction объясняется ровно одним candidate-правилом, collision отсутствует. Побочный выход: локальная оценка `predicted` = ожидаемому `new_independent` (cross-check для Stage 6.1).

```python
"""Phase 7C Stage 3.7: dry-run v2 на no_match dataset (overlap новых правил)."""
import django

django.setup()  # DJANGO_SETTINGS_MODULE=config.settings.dev

import json

from apps.catalog.rules_engine import (
    TIER_CANDIDATE,
    ProductFacts,
    evaluate_product,
    load_ruleset,
)

rs = load_ruleset("data/catalog_processing_rules/tool_type.v2.json")
data = json.load(open("scratchpad/phase7c/phase7c-nomatch-pool.json", encoding="utf-8"))
rules = [r for r in rs.rules if r.tier == TIER_CANDIDATE]
predicted = 0
per_rule: dict[str, int] = {}
overlap = []
for row in data["rows"]:
    facts = ProductFacts(
        product_id=row["product_id"],
        name=row["name"],
        original_name=row["original_name"],
        brand=row["brand"],
        source_group=row["source_group"],
        article=row["article"],
    )
    verdict = evaluate_product(rules, facts)
    if verdict.status == "prediction":
        predicted += 1
        for ref in verdict.rule_refs:
            per_rule[ref] = per_rule.get(ref, 0) + 1
        if len(verdict.rule_refs) > 1:
            overlap.append({"product_id": row["product_id"], "rule_refs": list(verdict.rule_refs)})
    elif verdict.status == "collision":
        overlap.append({
            "product_id": row["product_id"],
            "rule_refs": list(verdict.rule_refs),
            "status": "collision",
        })
print("dataset_rows=%d predicted=%d new_rule_overlap=%d"
      % (len(data["rows"]), predicted, len(overlap)))
for ref in sorted(per_rule):
    print("  %s: %d" % (ref, per_rule[ref]))
if overlap:
    print("OVERLAP:", overlap)
    raise SystemExit(1)
```

Критерий: exit 0 (`new_rule_overlap=0`); иначе F-4 — rework пересекающихся правил (разведение измерений) и повтор.

### Stage 4 — re-pinning, freeze, commit checkpoint

- [ ] **4.1** Финализация `note` в v2: `"approved YYYY-MM-DD, Phase 7C Stage 2.7 per-rule review (N/N rules); base tool_type.v1 + K new rules"` (note входит в canonical hash — сначала note, потом хэши; прецедент v1 draft→approved).
- [ ] **4.2** Pinning: canonical `ruleset_hash` (из шага 3.2 после финализации note) + byte sha256 **LF**: `sed 's/\r$//' data/catalog_processing_rules/tool_type.v2.json | sha256sum` (урок F-1 фазы 7B: Windows/CRLF-хэш рабочей копии не является cross-platform референсом; канонический byte-референс — LF/Git-представление). Оба значения — в pin table derivation doc.
- [ ] **4.3** Freeze: derivation doc дополняется статусами APPROVED по каждому правилу и pin table; протокол `phase7c-report.md` актуализируется.
- [ ] **4.4** STOP → checkpoint: пользователь авторизует commit.
- [ ] **4.5** Commit (только после авторизации 4.4):

```bash
git add data/catalog_processing_rules/tool_type.v2.json \
        docs/catalog/phase7c-ruleset-v2-derivation.md \
        docs/plans/2026-07-22-PHASE7C_RULESET_COVERAGE_EXPANSION_PLAN.md \
        .superpowers/sdd/progress.md
git commit -m "feat(catalog): tool_type.v2 ruleset — coverage expansion (Phase 7C)"
```

(в `.superpowers/sdd/progress.md` — строка о статусе 7C по образцу 7A.2 Task 6.)

- [ ] **4.6** Post-commit scope-контроль: `git diff --name-only HEAD^ HEAD` → ровно 4 разрешённых файла (`tool_type.v2.json`, derivation doc, план, `progress.md`). Любой посторонний файл — инцидент: STOP, отчёт пользователю (без самостоятельного отката).
- [ ] **4.7** Post-commit сверка: `git show HEAD:data/catalog_processing_rules/tool_type.v2.json | sha256sum` == pinned LF-хэшу из 4.2 (Git blob = LF-референс; расхождение → зафиксировать как F-1-инцидент pinning, не продолжать).

### Stage 5 — staging shadow v2 (read-only) + replay + регрессия v1

- [ ] **5.1** Подготовить LF-копию для контейнера: `sed 's/\r$//' data/catalog_processing_rules/tool_type.v2.json > scratchpad/phase7c/tool_type.v2.lf.json`; `sha256sum scratchpad/phase7c/tool_type.v2.lf.json` == pinned LF-хэшу из 4.2 (обязательно: рабочая копия на Windows — CRLF, контейнеру нужны LF-байты). Затем `docker cp scratchpad/phase7c/tool_type.v2.lf.json proff58_staging-web-1:/app/logs/phase7c-tool_type.v2.json`; в контейнере `sha256sum /app/logs/phase7c-tool_type.v2.json` == pinned LF-хэшу (иначе F-1).
- [ ] **5.2** Shadow-прогон:

```bash
docker exec proff58_staging-web-1 python manage.py catalog_rules_shadow \
  --ruleset /app/logs/phase7c-tool_type.v2.json \
  --pool all --sample-size 100 --seed 20260721 \
  --out /app/logs/phase7c-shadow-report-v2-pool-all.json \
  --gate-sample-out /app/logs/phase7c-gate-sample-v2-pool-all.json \
  --corpus /app/data/catalog_processing_rules/applied_corpus_tool_type.v1.json
```

exit 0; `collisions=0` (иначе F-6); `corpus_overlap_checked=true` (иначе F-6); `rewrite_attempts=0`.
- [ ] **5.3** Контроли report: `input_universe_hash` == `82536a46…` (тот же пул, что 7B; расхождение → F-2); `taxonomy_hash` == `b357be60…`; `ruleset_hash` == pinned v2 (иначе F-1).
- [ ] **5.4** Replay теми же параметрами в `-replay` пути. Критерии детерминизма: (a) gate sample байт-идентичен основному (sha256 совпадает) и `canonical_hash(sample)` равен; (b) **полный diff двух reports пуст** за вычетом volatile keys (`generated_at`, `started_at`, `finished_at`, `duration_seconds`) и `command.args.out`/`gate_sample_out` — это включает равенство `per_rule` счётчиков (`raw_hits`, `prediction_hits`, `collision_hits`, `same_slug_multi_hits`), `counts`, хэшей и списка predictions (иначе F-8).
- [ ] **5.5** Регрессия v1: множество `product_id → predicted_option_slug` из 7B report (`scratchpad/phase7b/phase7b-shadow-report-pool-all.json`, 63 предсказания) ⊆ v2 report с теми же slug (расхождение → F-5).
- [ ] **5.6** Per-rule таблица всех правил (включая новые) + строки правил №6/№7 (мониторинг по решению 7A) + performance summary (duration, memory snapshot `docker stats`, не peak).
- [ ] **5.7** Артефакты локально в `scratchpad/phase7c/` (report, gate sample, replay-оба); sha256 staging == local.

### Stage 6 — coverage verdict + финальный отчёт + STOP

- [ ] **6.1** `new_independent = |v2_prediction_ids \ v1_prediction_ids|` (по спискам predictions двух reports) и `total_v2 = |v2_prediction_ids|`; cross-check с локальной оценкой Stage 3.7 (расхождение объясняется drift пула либо является F-8-сигналом). Цель — коридор 120–150+. Если `new_independent < 120` → обязательный per-cluster разбор остатка no_match (какие сегменты остались singleton'ами, какие в `taxonomy_gap`, почему устойчивых паттернов больше нет); F-7 — только при недоказанном исчерпании.
- [ ] **6.2** Протокол `scratchpad/phase7c/phase7c-report.md`: полное evidence всех стадий + Human Decision Log + coverage verdict + финальная сверка pinned-хэшей §2 (drift отсутствует).
- [ ] **6.3** STOP → отчёт пользователю. Решение пользователя: переход к Phase 7D (официальный gate: свежий sample, разметка ≥100, `catalog_rules_gate_validate`) отдельной авторизацией / доработка правил / приёмка доказанного исчерпания / иное.

## 8. Acceptance criteria

1. Stage 0: все инварианты зелёные; taxonomy snapshot сверен по `b357be60…`.
2. Stage 1: dataset `phase7c-nomatch-pool.json` получен каноническим engine в snapshot tx; count соответствует baseline (1530) либо расхождение объяснено и зафиксировано; D-1(a) скрипт использован только как временный инструмент.
3. Stage 2: derivation doc v2 с per-rule обоснованиями; соблюдено ограничение сложности (≤3 измерений, только существующие типы, человеко-объяснимость); human review пройден; taxonomy_gap зафиксированы без создания options.
4. Stage 3: v2 проходит `load_ruleset`, fixtures, taxonomy; corpus regression `collisions=0`, `wrong_slug=[]`, `correct>=32`; `new_rule_overlap=0` на dataset; rules-ветка тестов зелёная.
5. Stage 4: v2 заморожен с pin table (canonical + LF byte sha256); commit — только по авторизации; post-commit diff содержит ровно 4 разрешённых файла; Git blob == pinned LF-хэш.
6. Stage 5: shadow v2 `collisions=0`, overlap-check true; replay-детерминизм подтверждён полным diff (sample **и** per-rule счётчики); регрессия 63 v1-предсказаний полная.
7. Stage 6: `new_independent` в коридоре 120–150+, **либо** исчерпание устойчивых кластеров документально доказано и вынесено на checkpoint, либо F-7 с полным отчётом.
8. Drift отсутствует: записей в БД нет; v1 ruleset/corpus/схема/код не изменены (финальная сверка pinned-хэшей §2 в Stage 6.2).

## 9. F-условия (остановка и отчёт, без самостоятельных обходов)

- **F-1.** Drift инвариантов/хэшей/кода staging на любом шаге → STOP, фаза не продолжается, отчёт пользователю.
- **F-2.** `no_match`/`pool_size`/`input_universe_hash` расходятся с baseline 7B → STOP; пересмотр baseline — только решением пользователя.
- **F-3.** Кандидатный кластер требует несуществующего taxonomy slug → options НЕ создавать; фиксация в `taxonomy_gap`; если из-за этого цель недостижима → STOP, решение пользователя (taxonomy change — отдельная фаза).
- **F-4.** v2 не проходит `load_ruleset`/fixtures/taxonomy/взаимный-overlap валидацию → локальная доработка и повтор; систематическая неудача → STOP с отчётом.
- **F-5.** Регрессия: corpus replay даёт `collisions>0` или `wrong_slug≠[]`, либо v2 shadow теряет/перемещает хотя бы одно v1-предсказание → STOP, rework правил; молча не дорабатывать.
- **F-6.** v2 shadow: `collision_count > 0` или `corpus_overlap_checked ≠ true` → STOP, разбор, решение пользователя.
- **F-7.** Новые независимые predictions < 120 **и** аналитик не может доказать исчерпание новых устойчивых кластеров → STOP, отчёт; решение пользователя: ещё итерация derivation / приёмка меньшего запаса / иное. Если predictions < 120, но исчерпание доказано (per-cluster разбор остатка: singleton'ы, отсутствие устойчивого паттерна, `taxonomy_gap`) — это documented outcome, а не провал: фиксация в протоколе, вопрос о достаточности запаса выносится на checkpoint Stage 6.3.
- **F-8.** Replay-недетерминизм (различается sample или per-rule счётчики) → STOP, разбор matcher/данных.
- **F-9.** Обнаружена любая запись в БД или изменение вне §3 → STOP, инцидент-отчёт.

## 10. Human Decision Log (заполняется по ходу фазы)

| Decision | Reason | Timestamp (UTC) |
|---|---|---|
| Phase 7B — COMPLETED AS OBSERVATIONAL BASELINE | gate not reached: 19/63 predictions при MIN_ROWS_GATE=100; дефектов matcher нет; ruleset candidate-tier | 2026-07-22 (пользователь) |
| «Phase 7B больше не должна переоткрываться ради расширения правил» | расширение ruleset = новая фаза, не продолжение 7B | 2026-07-22 (пользователь) |
| Цель 7C: коридор 120–150 новых независимых predictions; F-7 только при недоказанном исчерпании кластеров | запас на фильтрации перед gate; хорошая работа не должна формально считаться провалом | 2026-07-22 (пользователь) |
| D-1 = (a) no_match extraction через container-скрипт с каноническим engine, **только как временный инструмент 7C** | (b) код+deploy и (c) ORM без engine отклонены; скрытая связность с приватными функциями команды осознана и ограничена временем жизни фазы; повторное использование → отдельная архитектурная фаза (публичный API/command) | 2026-07-22 (ревью пользователя) |
| Plan v1 — CHANGES REQUIRED | 6 замечаний: D-1(a) lifecycle, F-7 коридор, ограничение сложности, overlap новых правил, post-commit diff scope, replay per-rule | 2026-07-22 (пользователь) |
| Plan v2 — rework по 6 замечаниям | все пункты внесены (Stage 1, 2.4/2.6, 3.7, 4.6, 5.4, §8/§9) | 2026-07-22 (analyst) |
| Plan v2 — AUTHORIZED | Authorization scope: Stages 0, 1, and 2.1–2.6 only. Mandatory STOP at Stage 2.7 for per-rule human review. D-1(a) approved exclusively as a temporary Phase 7C research instrument. Stages 3–6 are not yet authorized | 2026-07-22 (пользователь) |
| | | |
