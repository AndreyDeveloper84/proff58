# TT-01 · Протокол: новый tool_type `izm-areometry` + re-gate

Дата: 2026-07-28. Исполнитель: окно «Окно» (Kimi Code). Ветка `dev`, только
локально. Staging не трогался, push/PR не выполнялись.

## Что сделано

В canonical manifest добавлена опция:

| поле | значение |
|---|---|
| slug | `izm-areometry` |
| value | `Ареометры (денсиметры)` |
| sort_order | 18 (продолжение блока `izm-*`: 0–17 заняты) |
| origin_kind | `manual_backport` |
| origin_ref | `phase8 step2 recheck + owner decision 2026-07-28` |
| review_status | `approved` |
| review_reason | 9 из 10 ареометров batch упираются в catch-all `izm-analizatory`; обоснование §П6 `scratchpad/phase8/phase8-step2-report.md` |
| review_ref | `phase8-step2-p6` |

Опции в файле отсортированы по slug — вставка на алфавитную позицию
(индекс 89, между `izm-analizatory` и `izm-dalnomery`). Состав: 328 → **329**.

## Хэши (новый эталон цепочки — для TT-03)

```
taxonomy_identity_hash:  fc13be7804b06713…14d8  →  524d4e317a804160548ebd5f4d0c590cb08a9b69910b23355df7558902616439
manifest_semantic_hash:  d906be2f021bcf37…7681  →  5ebbad744c0ecb212e85f3fc47167f9c1dad0bac02aac33c567735e4da07ac0e
labels.sample_hash:      09d5fc90d3302094…7c54  →  d4615f06d2aeefbac7d5ceb3241f5c37bf8af9900cc93b26c1a0ef617f4326b3
release canonical_hash:  2929eccdc3eab2750c0ad1298b70a613e1b2d586ea8f3aa014877ba9f1221a23
```

**TT-03 сверяется с `524d4e31…`, а не с `fc13be78…`.**

## Диф артефактов — доказательства

- Манифест: `git diff` — +11 строк (новая опция) и 2 изменённые hash-строки,
  больше ничего (сериализация indent=2/LF сохранена побайтово).
- Gate-фикстуры: **ровно две изменённые строки** —
  `phase7d-gate-sample-official.json`: `taxonomy_hash`;
  `phase7d-labels.json`: `sample_hash`. Дельта размера файлов 0/0 байт, CRLF
  не появился.
- Скрипт перепривязки (`scratchpad/catalog/tt01_rebind_sample.py`, dry-run →
  --apply) напечатал доказательства: product_id порядок/множество идентичны
  (n=103), строки sample идентичны, ground truth/reviewer_id/reviewed_at/
  rationale идентичны, `ruleset_hash` и `matcher_version` не тронуты.
- **rows=103 / correct=102 / unverifiable=1 — не сдвинулись** (проверено и
  скриптом, и прогоном гейта).

## Гейт и release manifest

- `catalog_rules_gate_validate --gate-sample …official.json --labels …` —
  `gate_passed=true`, EXIT=0, **без** `--allow-legacy-taxonomy-hash`:
  `observed_precision=0.9903 (unrounded 0.9902912621359223)`,
  `wilson95=[0.947041, 0.998284]`, independent replay 103/103, collisions=0.
- `catalog_rules_release_manifest --force` → `mode=written`, тот же прогон;
  `--check` → `check=ok`, EXIT=0. Release manifest перевыпущен **тем же
  коммитом**, что и перепривязка sample (см. ниже).
- Guard-тест `test_ci_job_carries_no_legacy_taxonomy_poblazhka` — зелёный
  (в комплекте 52/52: test_taxonomy_manifest + test_rules_release +
  test_rules_gate_validate). Флаг в CI не возвращался — комментарий в
  `tests.yml` обновлён, шаги не менялись.

## Обновлённая документация (старый хэш как текущее состояние)

- `CLAUDE.md` §8 (инварианты): `524d4e31…` + пометка TT-01.
- `.github/workflows/tests.yml` — комментарий джобы gate.
- `docs/catalog/rules-release-manifest.md` — §Команда.
- `docs/catalog/tool-type-reverse-migration.md` — пример JSON.
- `docs/plans/2026-07-26-WAVE7_1_H3_H5_PLAN.md` — инвариант §H1/H2 + строка
  задачи H4 (аннотирована «hash на момент H4»).
- `docs/plans/2026-07-27-WAVE7_1_ACCEPTANCE_REPORT.md` — история не
  переписана; добавлена post-factum пометка в шапку.
- `docs/catalog/rules-gate-h2.md` — хэш не захардкожен, правки не
  потребовалось.

Пины в тестах: `PINNED_IDENTITY_HASH`/`PINNED_SEMANTIC_HASH` и `options == 329`
в `test_taxonomy_manifest.py`, `CANONICAL_TAXONOMY_HASH` и `options == 329` в
`test_rules_release.py` — обновлены под новый эталон.

## Вопрос владельцу — `manifest_version` (НЕ решён)

Оставлено `manifest_version: 1`. Аргументы:

- **За bump 1 → 2:** `docs/catalog/tool-type-taxonomy-manifest.md` §Изменение
  taxonomy предписывает «правка manifest (новая manifest_version)» — это первое
  реальное изменение состава. H5 reverse-map строился ровно под переход
  `N → N-1` и станет впервые применим. Release manifest фиксирует
  `manifest_version` в inputs — версия станет видна в CI-контуре.
- **За оставить 1:** `taxonomy_identity_hash` от версии не зависит — bump не
  требует повторной перепривязки sample (меняется только
  `manifest_semantic_hash` → перевыпуск release manifest). Можно сделать
  отдельным микрошагом после решения.
- Рекомендация окна: **поднять до 2** отдельным шагом после приёмки TT-01,
  одновременно решив, не привязывать ли к version 2 планируемый `option_uid`
  (future_evolution), чтобы не тратить номер версии на пустой bump.

## Чего не делалось (границы)

- Тип в БД **не сидировался** (`load_tool_types` не запускался в этой задаче;
  сейчас он всё равно fail-closed на дубле `steplery` — зона TT-03).
- Matcher (`evaluate_product`, `facts_hash`), ruleset v2, applied corpus — не
  тронуты (`ruleset_hash=9bf0271a…` до и после одинаков — зафиксирован в
  release manifest).
- `value` существующих опций не менялось. Дубль `steplery` и 46/49 расхождений
  `sort_order` — TT-03, здесь не трогались.
- Глобальные команды не запускались. Staging не трогался. Ступень 3 Phase 8
  не начиналась. Push/PR — нет.

## Regression

Полный прогон на отдельной БД (`proff58_tt01_regress`, `--create-db`,
`-p no:pylama`), два запуска:

- Прогон 1 (до правки H5-пинов): `2 failed, 2111 passed, 1 skipped, 4 errors`.
  Оба failed — задокументированные окружениечные (`test_healthcheck_returns_ok`
  — нет Redis; `test_release_script_is_executable` — Windows exec bit).
  4 errors — фикстура `test_h5_canonical_downgrade_e2e.py` с пином
  `options == 328`: тот же класс намеренного изменения, что и два других
  пин-теста; пины обновлены (328→329, 324→325).
- Прогон 2 (финальное дерево, коммит `e12dfd9`, `--reuse-db`):
  **`2 failed, 2123 passed, 1 skipped`, 0 errors** — те же два
  окруженческих падения, третьего падения нет. Собрано 2126 тестов
  (`--collect-only`). Арифметика: baseline в `CLAUDE.md` (`~1806 passed`)
  относится к старому дереву; на актуальном `origin/dev` + TT-01 собирается
  2126, из них 2123 зелёные. Дельта passed между прогонами (+12) = 4
  восстановленных error-теста + 8 тестов, чьё выполнение зависит от состояния
  БД (create vs reuse); падений новых не появилось ни в одном прогоне.

Коммит: `e12dfd9` — манифест, обе фикстуры (2 строки), release manifest,
пины тестов, документация. Одним коммитом, как требует приёмка. Push не
выполнялся.

## Артефакты

- `scratchpad/catalog/tt01_add_areometry.py` — добавление опции + пересчёт
  hash-полей (dry-run/--apply).
- `scratchpad/catalog/tt01_rebind_sample.py` — перепривязка sample/labels
  (dry-run/--apply, доказательства в stdout).
