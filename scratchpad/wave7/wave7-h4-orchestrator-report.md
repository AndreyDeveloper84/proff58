# Wave 7.1 / H4 — отчёт для оркестратора

**Проект:** «Профессионал» (Django + DRF, каталог электро/ручного инструмента).
**Контур:** детерминированный rules-engine распознавания `tool_type` для товаров из 1С.
**Стадия:** H4 «re-gate на canonical taxonomy + clean-taxonomy check».
**Дата:** 2026-07-27. **Ветка:** `dev`. **Статус: ВЫПОЛНЕНА ПОЛНОСТЬЮ.**

---

## 1. Итог одной строкой

Замороженный gate-sample перевыпущен с legacy на canonical taxonomy binding,
поблажка `--allow-legacy-taxonomy-hash` снята из CI и защищена guard-тестом,
release manifest перевыпущен, все 15 «серых» записей словаря разобраны решением
владельца, staging проверен. Зелёный CI снова является полным доказательством контура.

## 2. Зачем стадия существовала

Wave 7 (аудит) нашёл два дефекта доверия. H1–H3 закрыли их механически, но
оставался хвост: замороженный 7D gate-sample нёс **legacy DB-order** `taxonomy_hash`
(`b357be60…`), поэтому гейт проходил только с явной поблажкой, и эта поблажка стояла
в CI-джобе. Пока она там — «зелёный CI» не доказывает, что контур согласован с
канонической идентичностью словаря. H4 убирает этот хвост.

## 3. Что сделано

| # | Задача | Статус |
|---|---|---|
| 1 | Re-gate sample+labels на canonical binding | ✅ |
| 2 | `gate_passed=true` без поблажки, precision ≥ 0.99, rows ≥ 100 | ✅ |
| 3 | Снятие `LEGACY_TAXONOMY_HASH` и флага из обоих шагов CI | ✅ |
| 4 | Перевыпуск release manifest тем же коммитом | ✅ (дважды: после re-gate и после clean-taxonomy) |
| 5 | Clean-taxonomy: 15 `pending_business_review` | ✅ разобраны, стало 0 |
| 6 | Staging: reconcile + no-op seed (по GO владельца) | ✅ PASS |
| 7 | Решение по судьбе legacy-механизма | ✅ сохранён + guard-тест |

## 4. Коммиты — **в `origin/dev`, CI зелёный**

Приняты оркестратором и запушены 2026-07-27 после rebase поверх merge PR #593:

```
b6361d6  docs(catalog): статусы стадий H3/H4 и закрытые вопросы волны
fcafb61  feat(catalog): clean-taxonomy — снято 15 pending_business_review
49ecb72  docs(catalog): контракт гейта и release manifest без legacy-поблажки
a2b8523  feat(catalog): re-gate на canonical taxonomy binding, поблажка снята из CI
```

(прежние локальные `10c4f77`/`93b9ec8`/`064a9d2`/`bef4293` неактуальны после rebase)

`HEAD == origin/dev == b6361d6`, ahead/behind 0/0, рабочее дерево по tracked-файлам чистое.

**CI на GitHub — success** (run `30233874674`, Deploy #69): джоба `catalog-rules-gate`
прошла за 21s, `tests`/`frontend`/`lint`/`deploy` — зелёные. Лог джобы:

```
шаг 1  python manage.py catalog_rules_gate_validate …          (без поблажки)
       rows=103 decisions: correct=102 unverifiable=1
       observed_precision=0.9903 (unrounded=0.9902912621359223)
       wilson95=[0.947041, 0.998284]
       independent replay: rows=103 checked=103 collisions_recomputed=0
       gate_passed=true
шаг 2  python manage.py catalog_rules_release_manifest --check  (без поблажки)
       check=ok (зафиксированный manifest совпадает с пересчитанным)
```

Цифры совпали с локальными до последнего знака. Побочно это доказывает
портабельность `artifact_sha256` Windows ↔ Linux CI: `--check` сверяет байтовые хэши
входов, и LF-пиннинг из H3 удержался.

## 5. Ключевое доказательство: смена binding, а не переразметка

Это главное требование стадии — перепривязать разметку, ничего в ней не изменив.

`git diff` по обоим артефактам — **ровно две строки**:

```
- "taxonomy_hash": "b357be604801197e…604326b"      (legacy DB-order)
+ "taxonomy_hash": "fc13be7804b06713…36714d8"      (canonical identity, H1)
- "sample_hash":   "888980e7209c2702…8635a6db"
+ "sample_hash":   "09d5fc90d3302094…34357c54"
```

Второе изменение — обязательное следствие первого: `labels.sample_hash` биндится
как `canonical_hash(sample)`.

Скрипт `scratchpad/wave7/h4_rebind_sample.py` (dry-run → apply) выдал девять проверок,
все `True`: порядок и множество `product_id` идентичны (103), содержимое строк sample
идентично, ground truth по каждой строке идентичен (сравнение полной записи разметки —
`decision`, `rationale`, `reviewer_id`, `reviewed_at`), `decisions` идентичны
(`correct=102`, `unverifiable=1`), покрытие 1 label на строку сохранено,
`ruleset_hash`/`matcher_version` не тронуты, дельта размера файлов **0 байт**.

**rows=103 / correct=102 / unverifiable=1 — не изменились.** Подгонки разметки под
ruleset не выполнялось.

## 6. Гейт и CI

```
catalog_rules_gate_validate --gate-sample … --labels …        (без поблажки)
  rows=103 correct=102 unverifiable=1
  precision=0.9902912621359223   wilson95=[0.947041, 0.998284]
  replay: checked=103 collisions_recomputed=0  overlap computed_empty=True
  declared_mismatches=[]   gate_passed=true   EXIT=0
```

Из джобы `catalog-rules-gate` удалены `env.LEGACY_TAXONOMY_HASH` и флаг из **обоих**
шагов (проверено разбором YAML). Оба шага исполнены локально дословно теми же
командами на закоммиченном `HEAD` → EXIT=0/0. DB-independence подтверждена прогоном
с заведомо мёртвым `DATABASE_URL`.

**Guard-тест** `test_ci_job_carries_no_legacy_taxonomy_poblazhka` разбирает `tests.yml`
как YAML (не как текст — чтобы комментарии не давали ложных срабатываний) и требует
отсутствия поблажки. Проверен обеими сторонами: при временном возврате флага **падает**,
на чистом файле — зелёный.

## 7. Негативная матрица на НОВОМ sample — 19/19 заблокированы

Покрыты: legacy и чужой `taxonomy_hash` без флага; флаг, выданный на другой хэш;
подделка `predicted_option_slug` / `facts_hash` / `rule_refs` / `collision_count`;
испорченный и чужой ruleset; thresholds (99 строк → exit 1); release manifest с
непересчитанным `canonical_hash`, с дрейфом, отсутствующий, битый, без секции
`canonical`; перезапись без `--force`.

Новый сценарий, специфичный для H4: **labels со старым `sample_hash`** → exit 2.
Он доказывает, что подменить `taxonomy_hash` «наполовину», без перепривязки разметки,
невозможно. Испорченные артефакты создавались только во временных каталогах.

## 8. Release manifest

| | после re-gate | после clean-taxonomy |
|---|---|---|
| `canonical_hash` | `52a8651c…` | **`e0ff608e…`** (финальный) |
| файл sha256 | `2be430ab…` | **`779d4912…`** |

`legacy_taxonomy_hash_allowed` = `null`, `declared_mismatches` = `[]`.
Байт-стабильность подтверждена тремя и двумя независимыми прогонами соответственно;
`--check` = `ok`. Первичные входы сверены worktree ↔ git index побайтово (LF-пиннинг
из H3 держится).

## 9. Clean-taxonomy — решение владельца применено

**Находка:** `origin_kind=legacy_unknown` у 11 записей был артефактом классификации H1
(помечалось всё, чего нет в seed-файле), а не отсутствием provenance. Обратный поиск по
`docs/` показал: все 11 созданы документированными раундами каталога, имеют
`AttributeOption.id` 418–429 и подтверждены товарами на staging (83…1 шт).

- 11 записей → `origin_kind=manual_backport`, `origin_ref` на раунд создания,
  `review_status=approved`, `review_ref=wave7-h4`;
- 4 неиспользуемые seed-опции (`metchiki`, `plashki`, `osnastka-rezbonarez`,
  `hoz-schetchiki`; 0 товаров) → оставлены как пробел ассортимента с письменной
  причиной; удаление отложено до процедур отката H5.

**Слияний и сплитов типов не выполнялось** — это продуктовое решение владельца.

`slug`/`value` не менялись, поэтому `taxonomy_identity_hash` остался `fc13be78…` и
**привязка gate-артефактов не затронута** — re-gate повторять не пришлось.
Изменился только `manifest_semantic_hash`: `91b3ed0c…` → `d906be2f…`.

Итог: `pending_business_review` = **0**, `legacy_unknown` = **0**, options = 328.

## 10. Staging (GO владельца получен и исполнен)

Развёрнут `origin/dev = 67349e4` → в контейнере **до-H4** манифест; код и артефакт
сверены по sha256 с закоммиченными.

1. Read-only `catalog_taxonomy_reconcile --fail-on blocking` → **exit 0**,
   `identity_equal=True`, **blocking = 0** по всем пяти категориям,
   advisory `manifest_unused_option`=4, `pending_business_review`=15 — ожидание ТЗ.
2. Бонус, read-only для БД: новый манифест передан во временный путь контейнера и
   проверен против живой БД → **blocking = 0**, `pending_business_review` **0**
   (было 15). Временный файл удалён, в БД не писалось.
3. pg_dump по политике перед записью: `db-2026-07-27-0532.sql.gz` (21 МБ).
4. No-op `load_tool_types` → `created=0, present=328, display_updated=0`, exit 0.
   Снимки «до»/«после»: options 328→328, PAV **38 822 → 38 822**, bindings 19→19,
   **весь JSON-снимок идентичен целиком**.
5. Reconcile после seed — отчёт совпадает с дореестровым, exit 0.

**STAGING RECONCILIATION + NO-OP SEED VERIFICATION PASS.**

**6. Контрольный reconcile после deploy H4** (post-push, 2026-07-27). Стенд обновлён
джобой `deploy`, в контейнере H4-манифест (sha256 `19389539…`, `semantic=d906be2f…`,
`pending=0`, `legacy_unknown=0`). `catalog_taxonomy_reconcile --fail-on blocking` →
**exit 0**, `identity_equal=True`, **blocking = 0**, `pending_business_review` **0**
(было 15), `manifest_unused_option` 4 — поимённо те четыре опции, которые владелец
решил оставить. Предсказание из п.2 подтвердилось точно.

Дополнительно контур прогнан **внутри контейнера** без поблажки: gate
`gate_passed=true` EXIT=0, `release_manifest --check` `check=ok` EXIT=0,
`canonical_hash=e0ff608e…`. Итого контур подтверждён на трёх независимых окружениях —
Windows-разработка, Linux CI, staging-контейнер — с побайтово совпадающими хэшами
входов. Evidence: `scratchpad/wave7/h4-staging-reconcile-postdeploy.json`
(sha256 `76c4ebd7…`).

## 11. Судьба legacy-механизма — решено

`--allow-legacy-taxonomy-hash` **сохранён** как инструмент replay исторических
артефактов (7B/7C/7D несут legacy binding; без него reverse-migration в H5 невозможен),
но выведен из штатного контура. Механизм не срабатывает молча: требует явно назвать
точный хэш, помечает расхождение severity `legacy_recipe`, и эта пометка попадает в
release manifest. Возврат в CI закрыт guard-тестом.

## 12. Проверки

| Проверка | Результат |
|---|---|
| Полный regression | **2 failed, 1839 passed, 1 skipped** (405s) |
| — из них известные environmental | redis-healthcheck + Windows exec bit — **только они** |
| Арифметика | 1834 (baseline H3) + 2 (re-gate) + 3 (clean-taxonomy) = 1839 ✔ |
| Catalog suite | 901 passed, 1 skipped |
| Тесты контура gate/release | 67 passed |
| Тесты манифеста + контура | 137 passed |
| `manage.py check` | 0 issues |
| `makemigrations --check --dry-run` | No changes detected |
| ruff / black | clean |
| Шаги CI локально, без поблажки | EXIT 0 / 0 |

## 13. Границы соблюдены

Не тронуты: semantics матчера (`evaluate_product`, `facts_hash`), содержимое ruleset v2,
applied corpus, enrichment/apply pipeline, дерево категорий, фронт.
Phase 8 (pilot rollout) остаётся **FROZEN** до `WAVE 7.1 ACCEPTED`.

## 14. Требует решения / действий вне стадии

1. **P1 — ошибка исполнителя, установлена после push. Ранее в этом отчёте была
   изложена неверно, ниже — исправление.**

   Дважды за окно в рабочей копии появлялось изменение отслеживаемого
   `data/attribute_rules.json`. Я списал это на побочный эффект тест-сьюта и оба
   раза выполнил `git checkout -- data/attribute_rules.json`.

   Атрибуция была неверной: ни один код-путь не пишет этот файл (все 20 вхождений
   `attribute_rules` в `apps/`/`tests/`/`scripts/` — чтение; catalog suite из 901 теста
   файл не меняет). Источник — **параллельная работа в той же рабочей копии** над
   правилами perforatory (Phase 0.5), влитая как PR #593 (`10f7453`).

   Последствие: дважды удалены чужие незакоммиченные правки. Содержимое уцелело
   только потому, что автор вёл работу в отдельной ветке — `no_load_speed` присутствует
   в файле на `origin/dev`. **Потерь нет, но по случайности, а не по аккуратности.**

   Отдельной задачи «тест пишет в репозиторий» **не требуется** — такого теста нет.
   Действующий вывод: в общей рабочей копии незнакомое изменение tracked-файла нельзя
   откатывать по догадке о происхождении.

2. Release-evidence по-прежнему живёт в `apps/catalog/tests/fixtures/`; перенос в
   `data/` унаследован из H3 как вопрос H5.

## 15. Вход для следующей стадии (H5 — reverse migration hardening)

Состояние контура на выходе H4:

```
ruleset     tool_type.v2.json        hash=9bf0271a…  rules=38
corpus      applied_corpus…v1.json   items=54
taxonomy    identity=fc13be78…  semantic=d906be2f…  options=328  pending=0
sample      103 строки, taxonomy_hash=canonical, sha256=a744b654…
labels      103, sample_hash=09d5fc90…, sha256=d7fe24f7…
gate        rows=103 correct=102 precision=0.9902912621359223
release     canonical_hash=e0ff608e…  файл sha256=779d4912…
CI          catalog-rules-gate без поблажки + guard-тест
```

Что H5 получает:

- legacy-механизм сохранён → исторические артефакты воспроизводимы, это прямая опора
  reverse-migration;
- `manifest_version` = 1 до сих пор; переход `N → N-1` будет первым реальным изменением
  версии, reverse-map строится с нуля;
- `future_evolution.immutable_option_identity` (`option_uid`) не реализован. H4 показал,
  почему это важно: 15 записей поменяли метаданные без изменения identity, но при
  удалении/переименовании опции такой развязки уже не будет;
- 4 опции с 0 товаров оставлены осознанно — естественный тестовый материал для
  процедуры удаления и отката.

---

**Полный протокол стадии со всеми выкладками:** `scratchpad/wave7/wave7-h4-report.md`.
**План волны:** `docs/plans/2026-07-26-WAVE7_1_H3_H5_PLAN.md`.
**Воспроизводимые скрипты:** `scratchpad/wave7/h4_rebind_sample.py`,
`h4_negative_matrix.py`, `h4_clean_taxonomy.py`.
