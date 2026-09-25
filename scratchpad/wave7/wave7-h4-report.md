# Wave 7.1 / Stage H4 — протокол исполнения (re-gate на canonical taxonomy + clean-taxonomy check)

> По плану `docs/plans/2026-07-26-WAVE7_1_H3_H5_PLAN.md` §5. Scope: binding gate-артефактов,
> CI-политика, release manifest, инвентаризация «серых» записей манифеста. Semantics матчера
> (`evaluate_product`, `facts_hash`), содержимое ruleset v2, applied corpus, enrichment/apply
> pipeline, дерево категорий, фронт — не тронуты. Phase 8 остаётся FROZEN.
> **Push и PR не выполнялись** (запрет владельца). На старте окна `origin/dev = 67349e4`
> (сверено живым `git fetch`), H1+H2+H3 запушены, CI зелёный.

## 1. Commits

| # | SHA | Содержание |
|---|---|---|
| 1 | `10c4f77` | re-gate: `phase7d-gate-sample-official.json` + `phase7d-labels.json` на canonical binding; `rules_release_manifest.v1.json` перевыпущен; из джобы `catalog-rules-gate` убраны `env.LEGACY_TAXONOMY_HASH` и флаг из обоих шагов; 4 тестовых файла переведены на canonical-контракт |
| 2 | `93b9ec8` | docs: `rules-gate-h2.md`, `rules-release-manifest.md`, `CLAUDE.md` §7, план волны §5 |
| 3 | `064a9d2` | clean-taxonomy: 15 `pending_business_review` сняты решением владельца; release manifest перевыпущен; guard-тест на возврат поблажки в CI; пины и тесты манифеста обновлены |

Плюс `bef4293` — статусы стадий в плане волны (итого 4 коммита).

**Постскриптум 2026-07-27.** Коммиты приняты оркестратором и запушены после rebase
поверх merge PR #593; актуальные SHA — `a2b8523`, `49ecb72`, `fcafb61`, `b6361d6`,
`HEAD == origin/dev == b6361d6`. **CI на GitHub — success** (run `30233874674`):
джоба `catalog-rules-gate` за 21s, оба шага без поблажки, вывод совпал с локальным
дословно (`gate_passed=true`, `check=ok`, precision `0.9902912621359223`,
wilson95 `[0.947041, 0.998284]`). Риск P2 «джоба не проверена на GitHub» — **закрыт**.
Побочно подтверждена портабельность `artifact_sha256` Windows ↔ Linux CI.

Пункт 1 плана §5 требовал, чтобы новый sample, release manifest и снятие поблажки из CI
попали **одним коммитом** — выполнено (`10c4f77` атомарен: любое подмножество ломает
либо `--check`, либо джобу).

## 2. Re-gate: смена binding, не переразметка

**Проблема.** Замороженный 7D sample нёс legacy DB-order `taxonomy_hash`
`b357be60…`, поэтому gate проходил только с `--allow-legacy-taxonomy-hash`.
Пока флаг стоял в CI, зелёная джоба не была полным доказательством контура.

**Что сделано.** Изменены ровно два поля (скрипт `scratchpad/wave7/h4_rebind_sample.py`,
точечная байтовая замена, dry-run → apply):

| Поле | До | После |
|---|---|---|
| `sample.taxonomy_hash` | `b357be604801197e…604326b` (legacy) | `fc13be7804b06713…36714d8` (canonical identity, H1) |
| `labels.sample_hash` | `888980e7209c2702…8635a6db` | `09d5fc90d3302094…34357c54` |

`labels.sample_hash` биндится к sample через `canonical_hash(sample)`, поэтому его
пересчёт — обязательное следствие, а не отдельное решение.

**Доказательство идентичности** (вывод скрипта, все девять пунктов `True`):

```
[1] product_id sample: порядок идентичен = True; множество идентично = True; n=103
[2] строки sample идентичны по содержимому = True
[3] изменённые top-level поля sample = ['taxonomy_hash']
[4] ground truth по каждой строке идентичен = True; множество product_id labels идентично = True
[5] изменённые top-level поля labels = ['sample_hash']
[6] decisions ДО = {'correct': 102, 'unverifiable': 1}
    decisions ПОСЛЕ = {'correct': 102, 'unverifiable': 1}; идентичны = True
[7] rows=103 correct=102 unverifiable=1 (ожидалось 103/102/1) -> True
[8] покрытие: каждая строка sample имеет ровно один label = True
[9] ruleset_hash sample/labels без изменений = True / True; matcher_version без изменений = True
дельта размера: sample=0 байт, labels=0 байт
```

Ground truth в п.4 сравнивался как полная запись разметки (`decision`, `rationale`,
`reviewer_id`, `reviewed_at`), а не только `decision`.

**Независимое подтверждение** — `git diff` даёт ровно 2 изменённые строки на два файла:

```
-  "taxonomy_hash": "b357be604801197e33182b84fde1755361e29653d98bd49429623b3ba604326b",
+  "taxonomy_hash": "fc13be7804b06713dccde5cd2888a437a1a7521772d5911acc7d9d93636714d8",
-  "sample_hash": "888980e7209c27026c13f56152330e5264d8da7103345fefb685713f8635a6db"
+  "sample_hash": "09d5fc90d3302094066e6abec9e25ed49ee11c7faf0ecbd46833849434357c54"
```

`artifact_sha256`: sample `873ee2a1…` → `a744b654…`, labels `4cb05d36…` → `d7fe24f7…`.
CRLF не появился (LF-пиннинг `.gitattributes` из H3 держится).

## 3. Gate без поблажки

```
python manage.py catalog_rules_gate_validate \
  --gate-sample apps/catalog/tests/fixtures/phase7d-gate-sample-official.json \
  --labels apps/catalog/tests/fixtures/phase7d-labels.json

rows=103 decisions: correct=102 unverifiable=1
observed_precision=0.9903 (recomputed: correct=102 / rows=103; unrounded=0.9902912621359223)
wilson95=[0.947041, 0.998284]
independent replay: rows=103 checked=103 collisions_recomputed=0 | overlap computed_empty=True
gate_passed=true (recomputed precision>=0.99 and rows>=100 and blocking_errors==0)
EXIT=0
```

Пороги: precision `0.99029…` ≥ 0.99, rows 103 ≥ 100, blocking_errors = 0,
`declared_mismatches` = `[]` (запись `legacy_recipe` исчезла).

## 4. CI: поблажка снята

Из джобы `catalog-rules-gate` (`.github/workflows/tests.yml`) удалены `env.LEGACY_TAXONOMY_HASH`
и `--allow-legacy-taxonomy-hash` из **обоих** шагов. Проверено парсингом YAML:

```
jobs: ['lint', 'frontend', 'test', 'catalog-rules-gate']
env keys: ['DJANGO_SETTINGS_MODULE', 'DJANGO_SECRET_KEY', 'DATABASE_URL',
           'CELERY_BROKER_URL', 'CELERY_RESULT_BACKEND']     <- LEGACY_TAXONOMY_HASH отсутствует
STEP: Gate — frozen 7D sample против default ruleset      legacy flag present: False
STEP: Release manifest — проверка зафиксированной версии  legacy flag present: False
```

**Локальное исполнение обоих шагов дословно теми же командами:**

```
step 1  catalog_rules_gate_validate --gate-sample … --labels …
        gate_passed=true                                                  EXIT=0
step 2  catalog_rules_release_manifest --check
        check=ok (зафиксированный manifest совпадает с пересчитанным)     EXIT=0
```

DB-independence джобы подтверждена повторно: с заведомо мёртвым
`DATABASE_URL=postgres://nobody:nobody@127.0.0.1:1/nodb` шаг 1 → `gate_passed=true`, EXIT=0.

## 5. Release manifest перевыпущен

Тем же коммитом, что и sample (evidence манифеста ссылается на `apps/catalog/tests/fixtures/`).

| Поле | До | После |
|---|---|---|
| `canonical_hash` | `f43d6e0d3b55af12…9e82c223` | `52a8651c79481359…958e5996` |
| `gate.legacy_taxonomy_hash_allowed` | `b357be60…` | `null` |
| `gate.declared_mismatches` | `[{severity: legacy_recipe, …}]` | `[]` |
| `inputs.gate_sample.artifact_sha256` | `873ee2a1…` | `a744b654…` |
| `inputs.labels.artifact_sha256` | `4cb05d36…` | `d7fe24f7…` |

Не изменилось (и не должно было): `ruleset_hash` `9bf0271a…`, rules=38, corpus items=54,
`taxonomy_identity_hash` `fc13be78…`, `manifest_semantic_hash` `91b3ed0c…`, options=328,
метрики gate (rows/correct/precision/wilson95), thresholds, matcher_version, gate_version.

**Байт-стабильность** — три независимых прогона дают идентичный файл:

```
2be430abbaf482094ef35503dd9296eb208d235eb7ce98d4dcc5ab4006299e99 *rules_release_manifest.v1.json
2be430abbaf482094ef35503dd9296eb208d235eb7ce98d4dcc5ab4006299e99 *scratchpad/wave7/h4-rel-run1.json
2be430abbaf482094ef35503dd9296eb208d235eb7ce98d4dcc5ab4006299e99 *scratchpad/wave7/h4-rel-run2.json
```

Повторный прогон без `--force` → `unchanged (байт-идентичен)`; `--check` → `check=ok`.

**LF-пиннинг проверен** сравнением worktree ↔ git index по всем первичным входам:
`tool_type.v2.json` `ff449701…`, `applied_corpus_tool_type.v1.json` `6663a6fe…`,
`tool_type_taxonomy.v1.json` `e996502f…` — совпадают побайтово, значит `artifact_sha256`
в манифесте — ровно те байты, которые увидит CI.

## 6. Негативная матрица на НОВОМ sample

`scratchpad/wave7/h4_negative_matrix.py` — **19 сценариев, отклонений 0**. Испорченные
артефакты создавались только во временных каталогах; `data/` и `fixtures/` не изменялись
(контрольные sha256 в конце прогона совпадают с закоммиченными).

| Сценарий | Ожидание | Результат |
|---|---|---|
| sample с legacy `taxonomy_hash`, gate без флага | 2 | `declared mismatch sample.taxonomy_hash` |
| тот же sample → `release_manifest --check` | 2 | manifest не выпущен, blocking gate errors |
| sample с чужим `taxonomy_hash` (`0×64`) | 2 | blocking |
| чужой `taxonomy_hash` + legacy-флаг на **другой** хэш | 2 | blocking (флаг не «универсальная отмычка») |
| **`labels.sample_hash` от старого sample (не перепривязаны)** | 2 | `labels.sample_hash != canonical_hash(sample)` |
| подделан `predicted_option_slug` | 2 | `declared mismatch rows[37015].predicted_option_slug` |
| подделан `facts_hash` | 2 | `facts_hash не совпадает с пересчитанным` |
| подделаны `rule_refs` | 2 | `declared mismatch rows[37015].rule_refs` |
| подделан `collision_count` | 2 | `declared=7 != recomputed=0` |
| испорченный ruleset (+keyword) → gate | 2 | `declared mismatch sample.ruleset_hash` |
| тот же ruleset → `--check` | 2 | manifest не выпущен |
| чужой ruleset (исторический v1 вместо v2) | 2 | `declared mismatch sample.ruleset_hash` |
| sample обрезан до 99 строк | 1 | `thresholds не пройдены (precision=0.989899 … rows=99 < 100)` |
| release manifest: `canonical_hash` не пересчитан | 2 | `записан '52a8651c…', пересчитан '7019a8d…'` |
| release manifest: самосогласован, но drift (`rules=999`) | 2 | структурный дифф |
| release manifest отсутствует / битый JSON / без `canonical` | 2 | по каждому |
| существующий отличающийся manifest без `--force` | 2 | файл не тронут (проверено побайтово) |

Пятая строка — новая и специфичная для H4: она доказывает, что подменить `taxonomy_hash`
в sample **без** перепривязки labels нельзя, то есть выполненная операция не могла быть
сделана «наполовину».

## 7. Тесты контура переведены на canonical-контракт

10 тестов кодировали legacy-привязку как контракт и обязаны были измениться. Негативное
покрытие при этом **не ослаблено** — проверки legacy перенесены с реальных фикстур на
временные копии:

| Было | Стало |
|---|---|
| `test_frozen_sample_blocks_without_legacy_flag` (gate) | `test_frozen_sample_passes_without_legacy_flag` + `test_frozen_sample_with_legacy_taxonomy_hash_blocks` (tmp-копия) |
| `test_frozen_sample_passes_with_legacy_flag` (gate) | `test_frozen_sample_legacy_flag_still_admits_legacy_artifact` (tmp-копия, `severity=legacy_recipe`) |
| — | `test_frozen_sample_binds_canonical_taxonomy_identity` (новый: sample.taxonomy_hash == manifest identity ≠ legacy) |
| `test_frozen_sample_blocks_without_legacy_flag` (validate) | `test_legacy_taxonomy_binding_blocks_exit_2` (tmp-копия) |
| `test_no_manifest_without_legacy_flag` | `test_no_manifest_on_legacy_taxonomy_binding` (tmp-копия) |
| `test_check_without_legacy_flag_fails_exit_2` | `test_check_on_legacy_binding_fails_exit_2` (tmp-копия) |
| `gate.legacy_taxonomy_hash_allowed == LEGACY`, `[…] == ['legacy_recipe']` | `is None`, `declared_mismatches == []` |

Синтетические тесты H2 `test_tampered_taxonomy_hash_blocks_without_flag` и
`test_legacy_taxonomy_hash_allowed_explicitly` не менялись — они и раньше работали на
собственном мире и продолжают покрывать обе ветки политики.

Прогон четырёх файлов контура: **67 passed** (было 65: +4 −2).

## 8. Clean-taxonomy check

15 `pending_business_review` = 11 `legacy_unknown` + 4 seed-записи «unused». Advisory
`manifest_unused_option` = 4 — это **те же четыре**, а не отдельные (сверено с
`staging-reconcile-report.json` из H1). Итого различных записей на разбор — 15.

**Ключевая находка: `origin_kind=legacy_unknown` — артефакт классификации H1, а не
отсутствие provenance.** H1 помечал так всё, чего нет в seed-файле. Обратный поиск по
`docs/` показал, что все 11 созданы документированными раундами каталога с известными
`AttributeOption.id` (418–429). Счётчики товаров — из `staging-tool_type-usage.json`
(staging, 2026-07-23).

| # | slug | value | товаров | provenance (восстановлено) | предложение |
|---|---|---|---|---|---|
| 1 | `stroitelnye-lesa-vyshki` | Строительные леса и вышки-туры | 83 | `stroitelnyy-roadmap.md:73`, R1, `id=418` | оставить, `approved` |
| 2 | `fiksatory-germetiki-rezby` | Фиксаторы и герметики резьбы | 24 | `stroitelnyy-roadmap.md:111` + `catalog-readiness-roadmap.md:79` (Round 4A), `id=420` | оставить, `approved` |
| 3 | `kukhonnye-razdelochnye-nozhi` | Кухонные и разделочные ножи | 14 | `ruchnoy-roadmap.md:271`, `id=422` | оставить, `approved` |
| 4 | `kovshi-shtukaturnye` | Ковши штукатурные | 10 | `stroitelnyy-roadmap.md:102`, `id=419` | оставить, `approved` |
| 5 | `armiruyushchie-lenty-binty` | Армирующие ленты и бинты | 5 | `catalog-readiness-roadmap.md:76`, `id=426` | оставить, `approved` |
| 6 | `aksessuary-dlya-klyuchey` | Аксессуары для ключей | 4 | `ruchnoy-roadmap.md:361`, `id=425` | оставить, `approved` |
| 7 | `bp-osnastka-pnevmomolotkov` | Оснастка и запчасти для пневмомолотков | 4 | `catalog-readiness-roadmap.md:132`, `id=429` | оставить, `approved` |
| 8 | `rukoyatki-dlya-instrumenta` | Рукоятки для ручного инструмента | 3 | `ruchnoy-roadmap.md:287`, `id=423` | оставить, `approved` |
| 9 | `skruchevateli-provoloki` | Скручиватели проволоки | 2 | `catalog-readiness-roadmap.md:85`, `id=427` | оставить, `approved` |
| 10 | `bp-nabory-pnevmoinstrumenta` | Наборы пневмоинструмента | 1 | `catalog-readiness-roadmap.md:135` | оставить, `approved` |
| 11 | `spetsialnye-nozhi` | Специальные ножи | 1 | `ruchnoy-roadmap.md:339`, `id=424` | оставить, `approved` |
| 12 | `metchiki` | Метчики | 0 | seed-словарь, нигде не применён | оставить (пробел ассортимента) |
| 13 | `plashki` | Плашки | 0 | seed-словарь, нигде не применён | оставить (пробел ассортимента) |
| 14 | `osnastka-rezbonarez` | Оснастка для нарезания резьбы | 0 | seed-словарь, нигде не применён | оставить |
| 15 | `hoz-schetchiki` | Счётчики воды | 0 | seed-словарь, нигде не применён | оставить |

Ни одна из 15 не входит в ruleset v2; в applied corpus — только `bp-osnastka-pnevmomolotkov`.
Поэтому изменение `review_status`/`origin_kind` у них **не влияет** на
`taxonomy_identity_hash` (он считается только по `{slug, value}`), но меняет
`manifest_semantic_hash` → потребует перевыпуска release manifest тем же коммитом.

Слияния и сплиты не предлагались и не выполнялись: №12–14 (метчики / плашки / оснастка
резьбонарезная) выглядят кандидатами на объединение, но это продуктовое решение владельца.

### Решение владельца (2026-07-27) и его применение

| Группа | Решение | Как применено |
|---|---|---|
| 11 записей с восстановленным provenance | утвердить: `approved` + `origin_ref` | `origin_kind` `legacy_unknown` → `manual_backport`, `origin_ref` = раунд создания (см. таблицу выше), `review_ref=wave7-h4` |
| 4 неиспользуемые seed-опции | оставить, пометить `approved` | `review_status=approved`, письменная причина «пробел ассортимента; удаление отложено до процедур отката H5», `review_ref=wave7-h4` |

Применено скриптом `scratchpad/wave7/h4_clean_taxonomy.py` (dry-run → apply), который
перед записью проверяет инварианты и **отказывается писать** при их нарушении:

```
[0] round-trip сериализации байт-в-байт: OK
[1] изменено записей: 15 (ожидалось 15)
[2] множество slug/value не изменилось = True
[3] число options = 328
[4] taxonomy_identity_hash не изменился = True  (fc13be78…)
[5] manifest_semantic_hash: 91b3ed0c… -> d906be2f…
[6] pending_business_review осталось = 0
[7] origin_kind: {'seed': 313, 'manual_backport': 15}
[8] validate_manifest_doc: нарушений нет
```

Пункт [4] — ключевой: `taxonomy_identity_hash` считается только по `{slug, value}`,
а они не менялись, поэтому **привязка gate-артефактов из §2 не затронута** и re-gate
не пришлось повторять. Изменился только `manifest_semantic_hash`, поэтому release
manifest перевыпущен тем же коммитом: `canonical_hash` `52a8651c…` → `e0ff608e…`
(файл sha256 `779d4912…`), два прогона байт-идентичны, `--check=ok`.

Итог: `pending_business_review` = 0, `legacy_unknown` = 0, options = 328 без изменений.
Advisory `manifest_unused_option` = 4 сохраняется намеренно — это те же четыре опции,
теперь с зафиксированным письменным решением владельца.

## 9. Судьба `--allow-legacy-taxonomy-hash` (предложение)

**Предлагаю сохранить механизм, но зафиксировать политику его применения.**

За сохранение:
- H5 (reverse migration hardening) — про воспроизведение и откат исторических состояний;
  все артефакты фаз 7B/7C/7D несут legacy binding, без флага их replay невозможен в принципе;
- механизм не срабатывает молча: требует явно назвать точный хэш, помечает расхождение
  отдельной severity `legacy_recipe`, и эта пометка попадает в release manifest — то есть
  использование поблажки всегда видно в зафиксированной версии контура;
- негативная матрица подтвердила, что флаг не является «универсальной отмычкой»: он
  допускает ровно тот хэш, который назван, и блокирует любой другой.

Против сохранения — единственный содержательный риск: кто-нибудь вернёт флаг в CI.

**Решение владельца (2026-07-27): сохранить механизм + guard-тест.** Реализовано —
`test_ci_job_carries_no_legacy_taxonomy_poblazhka` разбирает `tests.yml` как YAML
(а не как текст, чтобы пояснительные комментарии не давали ложных срабатываний) и
требует: в `env` джобы нет переменных с `LEGACY`, ни один шаг не передаёт
`--allow-legacy-taxonomy-hash`.

Guard проверен обеими сторонами: при временном возврате флага в шаг 1 тест **падает**
(`AssertionError`), после восстановления файла — зелёный. Временная правка откачена,
`git diff` по `tests.yml` пуст.

## 10. Staging (GO владельца получен 2026-07-27)

**Важный контекст:** staging развёрнут с `origin/dev = 67349e4`, коммиты H4 не запушены,
поэтому в контейнере лежит **до-H4** манифест. Это подтверждено preflight'ом и учтено
в ожиданиях.

**Preflight.** Код и артефакт в контейнере побайтово равны закоммиченным в `93b9ec8`:

```
tool_type_taxonomy.v1.json          e996502f2dde898f…  == git show 93b9ec8:…
taxonomy_manifest.py                7583f84cc0482d63…  == локальному
catalog_taxonomy_reconcile.py       e7809e3c2f99cdbe…  == локальному
load_tool_types.py                  1bd3977543c57bc8…  == локальному
manifest в контейнере: options=328, identity=fc13be78…, semantic=91b3ed0c…, pending=15
```

**1. Read-only reconcile** (`--format json --fail-on blocking`), **exit 0**:

- `identity_equal = True`; live options 328 == manifest 328;
  live identity == manifest identity == `fc13be78…`;
- **blocking = 0** по всем пяти категориям (`missing_in_live`, `unexpected_in_live`,
  `slug_value_mismatch`, `used_outside_manifest`, `ruleset_unknown_slug`);
- advisory: `manifest_unused_option` = 4, `pending_business_review` = 15,
  `semantic_duplicate` = 0, `display_metadata_mismatch` = 0 — ровно ожидание из ТЗ.

Evidence: `scratchpad/wave7/h4-staging-reconcile-before.json` (sha256 `0fc4557d…`).

**2. Валидация НОВОГО манифеста против живой БД (до пуша).** Файл H4-манифеста передан
во временный путь `/tmp/h4-taxonomy.json` внутри контейнера (sha256 в контейнере
`19389539…` == локальному — передача побайтовая), reconcile запущен с `--manifest`,
временный файл затем удалён. **В БД ничего не писалось.** Результат, **exit 0**:

- `identity_equal = True`, semantic `d906be2f…`;
- **blocking = 0**;
- advisory: `pending_business_review` **0** (было 15), `manifest_unused_option` 4,
  остальные 0.

То есть после пуша H4 staging останется без blocking-дрейфа, а «серых» записей не будет.
Evidence: `scratchpad/wave7/h4-staging-reconcile-newmanifest.out`.

**3. pg_dump перед записью** (политика `docs/catalog/operations/pgdump-policy.md`,
свежий дамп под конкретную операцию):

```
/home/taximeter/backups/staging/db-2026-07-27-0532.sql.gz     (21 МБ)
/home/taximeter/backups/staging/media-2026-07-27-0532.tgz
```

**4. No-op seed** `python manage.py load_tool_types` (без `--update-display`), **exit 0**:

```
Атрибут tool_type готов (manifest v1, 328 options).
created=0, present=328, display_updated=0, display_mismatch=0.
```

**Снимки «до»/«после»** (`h4-staging-seed-before.json` / `h4-staging-seed-after.json`,
скрипт H1 `staging_seed_snapshot.py`):

| Метрика | До | После |
|---|---|---|
| options | 328 | 328 |
| ProductAttributeValue | 38 822 | 38 822 |
| CategoryAttribute bindings | 19 | 19 |
| live identity | `fc13be78…` | `fc13be78…` |

Полный снимок option (`id/slug/value/sort_order`) — идентичен; полный снимок bindings
(все поля) — идентичен; **весь JSON-снимок целиком идентичен** (`before == after`).

**5. Reconcile после seed** — отчёт **побайтово тот же**, что до seed
(`before == after` на разобранном JSON), exit 0, blocking = 0.

**Статус: STAGING RECONCILIATION + NO-OP SEED VERIFICATION PASS.**

### 10.6 Контрольный reconcile после deploy H4 (2026-07-27, post-push)

После push и успешной джобы `deploy` (run `30233874674`) стенд несёт **H4-манифест**.
Preflight — sha256 в контейнере совпадают с закоммиченными:

```
tool_type_taxonomy.v1.json      19389539d7e2da5f…   (H4)
rules_release_manifest.v1.json  779d4912009c43af…   (H4)
taxonomy_manifest.py            7583f84cc0482d63…
catalog_taxonomy_reconcile.py   e7809e3c2f99cdbe…
манифест: options=328  identity=fc13be78…  semantic=d906be2f…
          pending=0  legacy_unknown=0
```

`catalog_taxonomy_reconcile --format json --fail-on blocking` → **exit 0**:

- `identity_equal = True`; live options 328 == manifest 328; live identity ==
  manifest identity == `fc13be78…`; `manifest_version` = 1;
- **blocking = 0** по всем пяти категориям;
- advisory: `pending_business_review` **0** (было 15 — clean-taxonomy доехал до стенда),
  `semantic_duplicate` 0, `display_metadata_mismatch` 0,
  `manifest_unused_option` **4** — поимённо `hoz-schetchiki`, `metchiki`,
  `osnastka-rezbonarez`, `plashki`, то есть ровно те опции, которые владелец решил
  оставить как пробел ассортимента. Это зафиксированное решение, а не дрейф.

Evidence: `scratchpad/wave7/h4-staging-reconcile-postdeploy.json` (sha256 `76c4ebd7…`).

**Контур прогнан внутри контейнера** (read-only, развёрнутое окружение, без поблажки):

```
catalog_rules_gate_validate …      rows=103 correct=102 unverifiable=1
                                   precision=0.9902912621359223
                                   wilson95=[0.947041, 0.998284]
                                   replay checked=103 collisions=0
                                   gate_passed=true            GATE_EXIT=0
catalog_rules_release_manifest --check
                                   canonical_hash=e0ff608e…
                                   check=ok                    CHECK_EXIT=0
```

Тем самым контур подтверждён на трёх независимых окружениях — Windows-разработка,
Linux CI и staging-контейнер — с побайтово совпадающими хэшами входов.

**Статус: POST-DEPLOY RECONCILIATION PASS. Предсказание §10.2 подтвердилось точно.**

## 11. Regression и служебные проверки

- Тесты контура gate/release (4 файла): **67 passed**.
- Тесты манифеста + контура после clean-taxonomy (6 файлов): **137 passed**.
- Catalog suite (`pytest apps/catalog`): **901 passed, 1 skipped**.
- `manage.py check` — 0 issues; `makemigrations --check --dry-run` — `No changes detected`.
- `ruff check apps/catalog .github` — clean; `black --check apps/catalog/tests/` — clean
  (28 файлов без изменений).
- **Пост-коммитное исполнение обоих шагов CI** на `HEAD = 064a9d2`, дословно командами
  из `tests.yml` и **без** legacy-флага: шаг 1 `gate_passed=true` EXIT=0;
  шаг 2 `check=ok` EXIT=0.

### Дельта тестов

| Стадия | Тестов в полном прогоне |
|---|---|
| baseline после H3 | 1834 passed |
| после re-gate (`10c4f77`) | 1836 passed (+2: `binds_canonical_taxonomy_identity`, разделение legacy-сценариев) |
| после clean-taxonomy (`064a9d2`) | **1839 passed** (+3: 2 теста манифеста вместо 1 + guard-тест CI) |

## 12. Оставшиеся риски

- **P1 — ошибка исполнителя, установлена после push (2026-07-27).** Дважды за окно в
  рабочей копии появлялось изменение tracked-артефакта `data/attribute_rules.json`
  (regex `(\d+)\s*(?:д|ж)` в `impact_energy`, опция `no_load_speed`). Я оба раза
  списал это на побочный эффект тест-сьюта и выполнил `git checkout -- data/attribute_rules.json`.

  **Атрибуция была неверной.** Проверка после push: ни один код-путь не пишет этот файл —
  все 20 вхождений `attribute_rules` в `apps/`, `tests/`, `scripts/` только читают его
  (`enrich_attributes`, `load_attributes`, `attribute_coverage`, `catalog_taxonomy_audit`,
  `catalog_seed_tool_type_filters`, `attribute_extract`); catalog suite (901 тест) файл
  не изменяет. Реальный источник — **параллельная работа в той же рабочей копии** над
  правилами perforatory (Phase 0.5), влитая как PR #593 (`10f7453`, 05:47).

  **Последствие:** я дважды удалил чужие незакоммиченные правки. Содержимое уцелело
  только потому, что автор вёл работу в отдельной ветке и закоммитил её там —
  `no_load_speed` присутствует в `data/attribute_rules.json` на `origin/dev`. Потерь нет,
  но это была случайность, а не следствие аккуратности.

  **Вывод на будущее:** репозиторий — общая рабочая копия с параллельными потоками.
  Незнакомое изменение в tracked-файле нельзя откатывать по догадке о его происхождении;
  сначала выяснить источник (`git log` по файлу, ветки, соседние сессии), при
  необходимости сохранить копию. Стадирование точечными путями (что делалось) остаётся
  верным — именно оно не дало чужой правке попасть в коммиты H4.

  Отдельной задачи «тест пишет в репозиторий» **не требуется** — такого теста нет.
- ~~P2 — джоба не проверена на GitHub~~ — **закрыт 2026-07-27**: run `30233874674`
  success, `catalog-rules-gate` зелёная без поблажки (см. постскриптум в §1).
- P2 — advisory `manifest_unused_option` = 4 сохраняется и после clean-taxonomy: это
  осознанное решение владельца (опции оставлены как пробел ассортимента с письменной
  причиной), а не дрейф. `pending_business_review` = 0.
- P2 — release-evidence по-прежнему живёт в `apps/catalog/tests/fixtures/`; перенос в
  `data/` не выполнялся (унаследовано из H3, вопрос H5).
- ~~P2 — staging проверялся против до-H4 манифеста~~ — **закрыт 2026-07-27**:
  после deploy выполнен контрольный reconcile на H4-манифесте (§10.6) —
  exit 0, blocking=0, `pending_business_review`=0.

## Full regression suite

**2 failed, 1839 passed, 1 skipped (405.28s)** — только два известных environmental
baseline failure (`tests/test_regression_mvp.py::test_healthcheck_returns_ok` — 503 без
Redis; `tests/test_deploy_release.py::test_release_script_is_executable` — Windows exec
bit). Сигнатура совпадает с pinned baseline; 1834 (H3) + 2 (re-gate) + 3 (clean-taxonomy)
= 1839 passed, третьего падения нет.

Промежуточный прогон после re-gate, до clean-taxonomy: **2 failed, 1836 passed,
1 skipped (478.29s)** — та же сигнатура.

> Замечание по гигиене прогона: параллельный запуск `pytest apps/catalog` во время
> фонового полного прогона конфликтует за тестовую БД (`--reuse-db`, одно имя БД).
> Такой запуск был прерван; оба зафиксированных прогона выполнялись эксклюзивно.

## Хэндофф в H5

Состояние контура на выходе H4:

```
ruleset       tool_type.v2.json      hash=9bf0271a…  rules=38
corpus        applied_corpus…v1.json id=staging-tool-type-6ebb8ac9d856 items=54
taxonomy      identity=fc13be78…  semantic=d906be2f…  options=328  pending=0
gate sample   103 строки, taxonomy_hash=canonical, sha256=a744b654…
labels        103, sample_hash=09d5fc90…, sha256=d7fe24f7…
gate          rows=103 correct=102 precision=0.9902912621359223 wilson95=[0.947041, 0.998284]
release       canonical_hash=e0ff608e…  файл sha256=779d4912…
CI            catalog-rules-gate без поблажки, guard-тест против её возврата
```

Что H5 получает как вход:

- `--allow-legacy-taxonomy-hash` сохранён — исторические артефакты 7B/7C/7D
  (legacy binding) остаются воспроизводимыми, это прямая опора reverse-migration;
- `manifest_version` = 1 всё ещё; переход `N → N-1` в H5 будет первым реальным
  изменением версии — reverse-map придётся строить с нуля;
- `future_evolution.immutable_option_identity` (`option_uid`) по-прежнему не реализован;
  H4 показал, почему это важно: 15 записей меняли `origin_kind`/`review_status` без
  изменения identity, но при удалении/переименовании опции такой развязки уже не будет;
- 4 опции с 0 товаров оставлены осознанно — они станут естественным тестовым
  материалом для процедуры удаления/отката в H5.
