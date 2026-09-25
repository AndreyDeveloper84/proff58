# Wave 7.1 — протокол окна ACCEPTANCE

**Дата:** 2026-07-27. **Ветка:** `dev`. **Тип окна:** документарная приёмка волны.
**Push / PR / объявление «WAVE 7.1 ACCEPTED» — НЕ выполнялись** (прерогатива владельца).

---

## 0. Состояние на входе — сверено живой командой

| Параметр | Заявлено в ТЗ | Фактически |
|---|---|---|
| `origin/dev` | `28c7bef` | `28c7bef` ✔ |
| локальная `dev` | синхронна | **`db28005`, ahead 1** — расхождение, см. §7 |
| tracked-файлы | чисто | чисто (`git status --porcelain -uno` пусто) ✔ |

`db28005` — `docs(plans): актуализировать SHA H5 после push и rebase (Wave 7.1)`,
автор AndreyDeveloper84, 09:17 сегодня, дифф — одна строка §2 плана волны. Это
легитимный незапушенный коммит окна H5, а не чужой трек. Откатывать нечего, он
войдёт в acceptance-PR.

**Второе расхождение с ТЗ:** на момент старта окна в системе уже шёл полный
regression (PID 21088, старт 09:29:51, вывод в `scratchpad/wave7/acceptance-regression.log`).
Свой параллельный прогон НЕ запускался — по ограничению «без параллельных прогонов
против общей тестовой БД» окно дождалось чужого.

---

## 1. Finding A — неканоническая идентичность словаря типов

**Что было.** `taxonomy_hash` считался от живой БД: зависел от порядка строк и
collation, то есть от окружения. Идентичность словаря нельзя было ни зафиксировать
в артефакте, ни воспроизвести на другой машине.

**Что сделано.** H1 ввёл canonical `taxonomy_identity_hash` — рецепт по code-point,
считается от файла-манифеста, не от БД. H4 перевыпустил замороженный gate-sample с
legacy на canonical binding и снял поблажку из CI.

**Доказательства (проверяемые факты):**

| # | Факт | Как проверено в этом окне |
|---|---|---|
| A1 | canonical identity = `fc13be7804b06713dccde5cd2888a437a1a7521772d5911acc7d9d93636714d8` | живой прогон `catalog_rules_release_manifest --check`, вывод сохранён: `scratchpad/wave7/acceptance-release-check.out` |
| A2 | контур **не зависит от БД** | оба прогона выполнены с заведомо мёртвым `DATABASE_URL=postgres://nobody:nobody@127.0.0.1:1/nodb` → gate EXIT=0, release EXIT=0 |
| A3 | смена binding — ровно две строки, разметка не переписана | `git show a2b8523 -- …/phase7d-gate-sample-official.json …/phase7d-labels.json` → `taxonomy_hash` b357be60→fc13be78, `sample_hash` 888980e7→09d5fc90; более ничего |
| A4 | gate проходит **без** поблажки | `catalog_rules_gate_validate` на замороженном sample: `rows=103 correct=102 unverifiable=1 precision=0.9902912621359223 wilson95=[0.947041, 0.998284] gate_passed=true`, EXIT=0 (`acceptance-gate-canonical.out`) |
| A5 | поблажки нет в CI | `grep -i legacy .github/workflows/tests.yml` → единственное вхождение в **комментарии**; guard-тест `test_ci_job_carries_no_legacy_taxonomy_poblazhka` разбирает workflow как YAML и игнорирует комментарии |
| A6 | legacy binding блокируется | тест `test_legacy_taxonomy_binding_blocks_exit_2` — подстановка `b357be60…` без флага → `CommandError`, `returncode == 2` |
| A7 | зелёный CI на канонической привязке | run **30233874674** (`b6361d6`, H4) и run **30241631114** (`28c7bef`, H5): `tests / catalog-rules-gate: success`, `tests / test`, `lint`, `frontend`, `deploy` — success (запрошено через `gh api .../jobs`) |
| A8 | манифест чист | 328 опций, `review_status`: 328 approved (`pending_business_review` = 0), `origin_kind`: 313 seed + 15 manual_backport (`legacy_unknown` = 0), `manifest_version` = 1 |

**Вывод:** finding A закрыт. Идентичность словаря воспроизводима вне БД, зафиксирована
в артефактах, привязка проверяется CI без поблажки, возврат поблажки ловится тестом.

---

## 2. Finding B — gate верил самодекларированным полям артефакта

**Что было.** Аудит Wave 7 подал в старый gate фальшивый sample: 100 строк вида
`{"product_id": N}`, выдуманные `ruleset_hash` = `ffff…`, `taxonomy_hash` = `eeee…`,
`corpus_overlap_checked=true`, `collision_count=0`. Ответ старого gate:
`observed_precision=1.0`, **`gate_passed=true`**.

**Что сделано.** H2 переписал gate в независимый pipeline: primary inputs (ruleset,
applied corpus, canonical manifest) загружаются сами, всё производное пересчитывается
(predictions, `rule_refs`, `facts_hash`, overlap, `collision_count`, хэши, precision,
Wilson), а declared-поля лишь сравниваются и дают structured mismatches.

**Главное доказательство — тот же самый артефакт прогнан через нынешний gate.**
Файлы аудита `scratchpad/wave7/bogus-sample.json` / `bogus-labels.json` сохранены с
Wave 7 и не изменялись. Результат сегодня (`acceptance-bogus-gate.out`):

```
rows=100 decisions: correct=100
observed_precision=1.0 (recomputed: correct=100 / rows=100; unrounded=1.0)
independent replay: rows=100 checked=0 collisions_recomputed=0
mismatch[blocking] sample.ruleset_hash:   declared='ffff…' recomputed='9bf0271a…'
mismatch[blocking] labels.ruleset_hash:   declared='ffff…' recomputed='9bf0271a…'
mismatch[blocking] sample.taxonomy_hash:  declared='eeee…' recomputed='fc13be78…'
blocking: sample row без facts_hash / без predicted_option_slug / без rule_refs …
blocking: row N: facts_hash не совпадает с пересчитанным   (×100)
gate_passed=false
EXIT=2
```

403 blocking-ошибки, `gate_passed=false`, exit 2. Обратите внимание на строку
`observed_precision=1.0`: арифметика по разметке честно осталась единицей —
**но решение гейта больше не следует из неё**. Именно в этом суть закрытия B:
precision перестала быть достаточным условием.

Дополнительно:

| # | Факт | Как проверено |
|---|---|---|
| B1 | declared-поля не влияют на решение | `checked=0` при 100 строках: replay не смог подтвердить ни одной строки и это дало blocking, а не молчаливый пропуск |
| B2 | негативные матрицы | H2 — 16 сценариев, H4 — 19/19 на новом sample, H5 — 40/40; все закреплены тестами, порча только во временных каталогах |
| B3 | guard'ы проверены обеими сторонами | H5: `h5_mutation_matrix.py` — 12/12 guard'ов падают при возврате дефекта в исходник и зеленеют после восстановления |
| B4 | контур зафиксирован release manifest'ом | `canonical_hash=e0ff608e…`, `legacy_taxonomy_hash_allowed=None`, `declared_mismatches=[]`; `--check` = ok в CI на каждом коммите |

**Вывод:** finding B закрыт. Артефакт, который раньше проходил гейт с precision=1.0,
сегодня отклоняется fail-closed.

---

## 3. Границы диффа волны

Волна = 21 коммит с меткой «Wave 7.1» (`e3e0797` … `28c7bef`) плюс локальный
`db28005` = 22. Сплошной диапазон `e3e0797^..HEAD` содержит **28** коммитов; лишние 7 —
чужие треки:

- `10f7453`, `3258ea6` (PR #593), `bd3ecb2`, `592e96c` (PR #594) — правила perforatory,
  трек 2 (Phase 0.5): `data/attribute_rules.json`, `apps/catalog/test_attribute_extract.py`;
- `989aec6` — Round 4A «Фиксаторы и герметики», `docs/catalog/stroitelnyy-roadmap.md`;
- `2962778` — архив планов фаз 6–7D; `13ad30b` — `.claude/settings.json`.

Ни один из этих файлов не попал в дифф ревью: пути отбирались поимённо, а
`docs/catalog/stroitelnyy-roadmap.md` исключён явно, хотя формально лежит в
`docs/catalog/`. Проверено `git show --stat` по всем семи невлновым коммитам.

Дифф разложен на четыре части (`scratchpad/wave7/acceptance-diff-*.patch`):
код 3050 строк, тесты 3779, документы 505, данные/фикстуры 5867.

**Контрольный факт границ волны:** `git diff e3e0797^..HEAD -- apps/catalog/rules_engine.py
data/catalog_processing_rules/tool_type.v2.json data/catalog_processing_rules/applied_corpus_tool_type.v1.json`
→ **пусто**. Матчер, ruleset v2 и applied corpus волной не тронуты, как и обещал §3 плана.

---

## 4. Проверки

| Проверка | Результат | Файл-свидетель |
|---|---|---|
| Полный regression | **2 failed, 1934 passed, 1 skipped** (502.01 s) | `acceptance-regression.log`, `.xml` |
| junit | `tests=1937 failures=2 errors=0 skipped=1` | 1934 + 2 + 1 = 1937 ✔ |
| Оба падения | `test_healthcheck_returns_ok` (redis недоступен: `getaddrinfo failed`) и `test_release_script_is_executable` (`33206 & 64` = 0, Windows exec bit) — известные environmental, третьего падения нет | |
| **Арифметика** | baseline H5 = 1920 passed. Дельта +14 — **целиком чужой трек**: PR #594 (`bd3ecb2`) добавил 6 тест-функций в `apps/catalog/test_attribute_extract.py`, параметризация даёт 4+3+1+1+4+1 = **14** собранных кейсов (пересчитано по junit поимённо). 1920 + 14 = **1934** ✔. Вклад волны в дельту — **0** | |
| `manage.py check` | System check identified no issues (0 silenced), EXIT=0 | |
| `makemigrations --check --dry-run` | No changes detected, EXIT=0 | |
| `ruff check apps config tests scripts` | All checks passed, EXIT=0 | |
| `black --check apps config tests scripts` | 571 files would be left unchanged, EXIT=0 | |
| gate без поблажки (мёртвая БД) | `gate_passed=true`, EXIT=0 | `acceptance-gate-canonical.out` |
| `release_manifest --check` (мёртвая БД) | `check=ok`, EXIT=0 | `acceptance-release-check.out` |

Прогон выполнен **без параллельной нагрузки** на тестовую БД: свой pytest не
запускался, окно дождалось уже идущего прогона. `DeadlockDetected` не возникал.

Примечание: прогон выполнялся без `-p no:pylama` и отработал штатно — в этом
окружении плагин не ломает сбор.

## 5. Независимое второе мнение — разбор находок поимённо

**`/codex review` буквально выполнить не удалось.** `codex` CLI отсутствует: нет в
PATH ни в PowerShell, ни в bash; не найден в npm-global (`npm ls -g` — 13 пакетов,
codex среди них нет), в `~/.bun/bin`, scoop, choco, `%LOCALAPPDATA%\Programs`.
Каталог `~/.codex` с `config.toml`, `auth.json` и `.sandbox-bin/codex-command-runner-*.exe`
сохранился — то есть codex когда-то стоял, но исполняемый файл отсутствует.

Замена: два независимых ревьюера с чистым контекстом, разделённые по зонам (ядро
H1–H4 / контур отката H5). Каждому выдан дифф волны по путям контура, **замысел**
обоих findings и прямая инструкция не верить самоотчёту стадий; запрещены запись,
тесты и git-мутации. Дифф отбирался поимённо по путям — чужой трек (perforatory
PR #593/#594, Round 4A) в него не попал.

Ключевые находки я перепроверил лично чтением кода перед тем, как принять.

### 5.1 Ядро контура (H1–H4)

| # | Находка | Реш. | Обоснование |
|---|---|---|---|
| 1 | **major** `corpus_path=None` — единственная ветка, где отсутствие первичного входа не даёт blocking; отчёт при этом пишет `overlap.computed_empty=true`, то есть утверждает непроверенное | **принято** | Проверено: `rules_gate.py:161` `corpus = load_corpus(...) if corpus_path else None`, `:330` overlap считается только `if corpus is not None`, `:395` поле пишется безусловно. Из CLI недостижимо (команда и `build_release_manifest` подставляют `DEFAULT_CORPUS_PATH`), но `run_independent_gate` публична. Задача, не правка окна |
| 2 | **major** `--allow-legacy-taxonomy-hash` принимает произвольный хэш: условие `declared_tax == allow_legacy_taxonomy_hash` сверяет флаг с тем, что артефакт сам про себя объявил; allow-list `b357be60…` в коде отсутствует | **принято** | Проверено `rules_gate.py:248-264` — дословно так. Расхождение **кода с инвариантом CLAUDE.md** («legacy hash допустим только явным флагом» читается как «только этот хэш»). Смягчения реальны: флага нет в CI (guard-тест), факт попадает в `declared_mismatches` с severity `legacy_recipe` и в `canonical` release manifest → любой прогон с поблажкой меняет `canonical_hash` и ловится `--check`; slug'и sample и ruleset независимо сверяются с манифестом. **Вынесено владельцу**: сузить до allow-list или удалить флаг |
| 3 | **major** provenance sample (`seed` / `pool` / `pool_filter_version`) — declared-поля, которые не пересчитываются и даже не сравниваются, хотя полностью определяют precision | **принято как граница метода** | Это не дефект реализации: перевыборка пула требует БД, а джоба сознательно DB-independent. Но граница нигде не проведена, а docstring обещает «все проверки пересчитываются из первичных inputs». Прямо влияет на честность приёмки → внесено в раздел незакрытого сводного отчёта |
| 4 | **minor** битый sample (без `rows` / без `product_id`) даёт exit 3 (internal) вместо 2 (invalid inputs) | **принято** | `validate_gate_labels` вызывается независимо от накопленных `sample_violations`; fail-closed сохранён, страдает семантика кода возврата |
| 5 | **minor** `** 0.5` вместо `math.sqrt` в Wilson: `pow` не обязан быть correctly rounded, 1 ULP между glibc и msvcrt изменит `canonical_hash` | **принято, но риск эмпирически не реализовался** | `wilson95` действительно входит в canonical. Однако release manifest сгенерирован на Windows, а `--check` зелёный и в Linux CI (run 30241631114), и в staging-контейнере — расхождения нет. Держим как дешёвую страховку, не как дефект |
| 6 | **minor** в machine report `primary_inputs.ruleset` и `artifact_sha256.ruleset` = `null` именно в том вызове, который делает CI (без `--ruleset`) | **принято** | Проверено `rules_gate.py:367, 381-385`. Компенсировано `hashes.ruleset_hash` и полным release manifest, но байтовый pin в отчёте гейта теряется |
| 7 | **minor** `--check` сверяет только секцию `canonical`, лишние top-level ключи проходят; юнит-тест строже команды | **принято** | Практический риск низкий (файл с лишними ключами инструментом не создаётся, `tests`-джоба ловит), но команда должна быть не слабее теста |
| 8 | **minor** `catalog_taxonomy_reconcile`: `live_by_slug = {o.slug: o for o in live}` схлопывает все опции с пустым slug в один ключ — drift недосчитывается | **принято** | Fail-closed сохранён (`""` не проходит `SLUG_RE` → blocking), страдает достоверность числа и объёма затронутых товаров |
| 9 | **minor** `semantic_duplicate_allowlist` в манифесте нереализуем против `unique_together = ("attribute","value")` — вторая опция даст `IntegrityError` вместо `CommandError` | **принято, латентно** | Проверено: в манифесте allowlist пуст. Контракт манифеста обещает то, чего БД не умеет |
| 10a | **nit** `reconcile:128` `load_ruleset` не обёрнут в `try/except ValueError`, рядом `load_manifest` обёрнут | **принято** | |
| 10b | **nit** `artifact_sha256` считается вторым чтением файла (TOCTOU относительно распарсенного содержимого) | **отклонено как задача** | Файлы под git с LF-пиннингом, чтения в одном процессе подряд, сценарий подмены между чтениями требует уже скомпрометированной ФС. Фиксируем как замечание, задачу не заводим |
| 10c | **nit** `mkstemp(dir=path.parent)` падает `FileNotFoundError` при отсутствии родительского каталога | **принято** | Сама схема atomic-записи признана корректной обоими ревью |
| 10d | **nit** `_canonical_json(..., default=str)` глушит типовые ошибки | **принято** | Для файла манифеста защищено JSON Schema, но функция вызывается и с live-данными |
| 10e | **nit** нет NFC-нормализации в рецепте identity | **отклонено** | Рецепт считается от файла, зафиксированного в git (NFD-форм в нём нет); расхождение с БД проявится как `slug_value_mismatch`, то есть не молча. Сам ревьюер это оговаривает |
| 11 | **minor/методология** gate решает по точечной оценке precision; посчитанный Wilson 95% в политику не входит. Запас над порогом = **одна метка** (102/103 = 0.99029 проходит, 101/103 = 0.98058 нет); LCB = 0.947, то есть «precision ≥ 0.99» на n=103 статистически не подтверждён | **принято как незафиксированное решение** | Не дефект: порог был выбран осознанно. Но нигде не записано, что он точечный и что запас = 1 метка. **Вынесено владельцу**: документировать или гейтить по LCB (тогда нужно ~370 строк выборки) |

### 5.2 Контур отката (H5)

| # | Находка | Реш. | Обоснование |
|---|---|---|---|
| 1 | **blocker** между планом и применением baseline не перепроверяется: `plan_rollback` читает live вне транзакции, `apply_rollback` внутри своей транзакции сверяет только исчезновение товара и опции, но **не** сверяет `value_option` с `from_option_slug`; `select_for_update` есть только внутри `flush_attrs_cache_merged`, то есть уже после записей | **принято, severity понижена blocker → major** | Факт подтверждён лично: `tool_type_rollback.py:311-348` — да, дословно так. Понижение обосновано: окно план→применение внутри одного `handle()`, план на диск не сохраняется; штатных конкурентных писателей `tool_type` нет — форвардный `enrich_tool_type` авторизуется отдельно, а 1С по ADR-0007 контент не пишет. Но обещание документа («conflict, а не молчаливая перезапись») **сильнее кода**, и post-audit такую перезапись не поймает — он сверяет live с `to` и пройдёт. Это самая тяжёлая находка ревью |
| 2 | **major** `noop` решается только по `option_slug` (`:285-290`), а post-audit сверяет ещё и `attrs_cache_tool_type` (`:365`) → товар с рассинхроненным кэшем получает `noop`, ремонта нет, а post-audit валит **уже закоммиченный** откат, и повтор даёт то же самое | **принято** | Подтверждено чтением. Прямо противоречит `docs/catalog/operations/rollback.md:47`. Достижимо через известный в проекте дрейф `attrs_cache` (под него существует `rebuild_attrs_cache`) |
| 3 | **major** post-audit выполняется после коммита и ничего не откатывает; вызов `verify_post_state` стоит вне `try` | **принято** | Подтверждено `catalog_tool_type_rollback.py:78-91`. Инвариант «нет полуприменённого состояния» держится только для исключений внутри `apply_rollback` |
| 4 | **minor→ по эргономике major** пустой снимок (`--product-ids ""`) проходит все гарды и даёт `written=0 post-audit=PASS`, exit 0 — «успешно откатил ничего» | **принято** | `validate_snapshot` действительно не отвергает `rows_count=0`. Для инцидентного инструмента вакуумный PASS — опасный вид зелёного |
| 5 | **minor** понижение версии не идемпотентно: после успешного выполнения повтор даёт blocking `live_not_at_from_manifest` с подсказкой, толкающей оператора вернуть словарь к N | **принято** | Подтверждено `taxonomy_reverse.py:158-169` — сверка только с `src.identity_hash`. Противоречит принципу «повтори — получишь тот же ответ», на котором построен остальной контур |
| 6 | **minor** у понижения версии нет post-audit: сверки live identity с целевым манифестом в продуктовом коде нет, хотя тест e2e её делает | **принято** | Шаг 4 процедуры (seed манифеста N-1) ничем не проверяется |
| 7 | **minor** `catalog_taxonomy_downgrade` пишет `--out` / `--emit-from` / `--emit-to` без `--force`, в отличие от snapshot-команды | **принято** | Повторный прогон затрёт доказательную базу отката — в связке с находкой 4 даёт вакуумный PASS |
| 8 | **minor** пара снимков не связана родословной: `from` из одной волны и `to` из другой пройдут все гарды | **принято** | Conflict-guard не обходится, но неверная **цель** отката не детектируется. Минимальное закрытие — запись в docs, что корректность пары на операторе |
| 9 | **minor** `build_downgrade_plan` не проверяет, что манифесты вообще про `tool_type` — защита деструктивного пути держится на побочном эффекте `live_taxonomy_identity()` | **принято** | |
| 10 | **minor** структурно битый снимок (строка не dict / нет ключей) даёт exit 3 вместо 2 | **принято** | Подтверждено: `validate_snapshot` проверяет хэш, версию, атрибут, дубли, `rows_count` — но не схему строки |
| 11 | **nit** `to`-снимок для remap наследует селектор `from` (`{"kind":"option_slugs", …}`), хотя описывает товары уже на целевых опциях; селектор входит в canonical hash | **принято** | |
| 12 | **nit** откат не батчится: `--all-with-tool-type` тянет все товары в память и лочит их до конца транзакции | **принято как эксплуатационное ограничение, отклонено как дефект корректности** | Атомарность требует одной транзакции; батчинг — это смена контракта атомарности, отдельное решение |

### 5.3 Что оба ревью признали корректным

Ядро: построчный replay матчера (facts_hash, вердикт, slug, rule_refs, collisions —
всё recomputed, declared только сравнивается); герметичность связки `labels.sample_hash
== canonical_hash(sample)` (подмена любой строки инвалидирует разметку, precision > 1
недостижим); fail-closed по всем загрузкам кроме corpus; канонизация identity
(сортировка по code-point, проекция строго на `{slug, value}`, перестановочная
инвариантность — покрыта тестами); LF-пиннинг всех пяти артефактов через
`.gitattributes` + регрессионный тест; **заявка H4 подтверждена фактами** (sample
объявляет ровно canonical identity, `legacy_taxonomy_hash_allowed: null`, флага в
workflow нет ни в одном шаге); release manifest не выпускается поверх непройденного
gate; `load_tool_types` физически не содержит delete/reslug.

H5: инвариант manifest-only (ни один модуль не создаёт `AttributeOption`, целевые slug
валидируются в трёх точках); fail-closed по usage при удалении опции **под правильной
блокировкой** (`select_for_update` + пересчёт в момент выполнения, а не по плану);
атомарность самой записи; канонизация снимка по рецептуре H3; гард по
`taxonomy_identity` фиксирует всё отображение `slug → value`; `unique_together` на PAV
снимает неоднозначность выбора строки; набор полей отката симметричен форвардному
`enrich_tool_type`; матрица блокировок понижения полна и разделена по диагнозам;
read-only обещания dry-run соблюдены.

### 5.4 Главный вывод ревью

**Ни одна находка не переоткрывает finding A или finding B.** Канонической
идентичности и независимому пересчёту гейта ревью не предъявило претензий — обе
находки-major по ядру (1 и 2) касаются путей, недостижимых из CI, а находка 3 —
границы метода, а не реализации.

**Но контур отката H5 получил находку уровня major с подтверждённым фактом
(TOCTOU в conflict-guard) и две смежные.** Это не дефект доверия волны, это
качество новой функциональности, добавленной последней стадией.

---

## 6. Коммиты окна — локальные, НЕ запушены

| SHA | Заголовок | Файлы |
|---|---|---|
| `e953f0e` | `docs(plans): сводный отчёт волны Wave 7.1 — доказательства findings A/B (acceptance)` | `docs/plans/2026-07-27-WAVE7_1_ACCEPTANCE_REPORT.md` (+233) |
| `4256a72` | `docs(plans): статусы acceptance и открытые вопросы волны (Wave 7.1)` | `docs/plans/2026-07-26-WAVE7_1_H3_H5_PLAN.md` (+41/−8) |
| `e8806a4` | `docs(claude): §7 — снятие заморозки Phase 8 объявляет владелец (Wave 7.1)` | `CLAUDE.md` (+5/−1) |

Итого ветка `dev` ahead 4 от `origin/dev`: `db28005` (хвост H5) + три коммита выше.
`git diff --name-only db28005..HEAD` не содержит ничего вне `docs/` и `CLAUDE.md` —
кода контура в acceptance-PR нет.

**`git push` и `gh pr create` не выполнялись.**

## 7. Расхождения, находки и вопросы владельцу

1. **Локальная `dev` = `db28005`, ahead 1 от `origin/dev`** — вопреки формулировке ТЗ
   «синхронна». Коммит легитимен (окно H5, правка одной строки плана), не откатывался.
2. **Regression был уже запущен до старта окна** — свой прогон не запускался.
3. **Baseline сместился 1920 → 1934** за счёт чужого трека.
4. **`codex` CLI отсутствует** — п. 2 §7 плана выполнен эквивалентом.
5. **Протоколы стадий H1–H5 и все evidence-скрипты не в git** (`scratchpad/` не в
   `.gitignore`, но и никогда не коммитился). CLAUDE.md §7 и план ссылаются на них
   как на доказательства.
6. **Правка кода по находкам ревью в этом окне НЕ выполнялась** — по границе
   «acceptance документарен; если нужен код — это находка, а не задача окна».

7. **В общей рабочей копии появилась чужая правка контура — не откатывалась.**
   В 09:48–09:49, уже после моих проверок и после завершения ревью, изменились два
   отслеживаемых файла:

   - `apps/catalog/tool_type_rollback.py` — вынесено решающее правило в `_decide`,
     `apply_rollback` берёт `Product` и PAV под `select_for_update` (порядок по `id`)
     и повторяет сверку baseline внутри транзакции: дрейф → `RollbackError`
     «baseline изменился между планом и применением», товар, уже приведённый к цели
     чужим процессом, считается `noop`;
   - `apps/catalog/tests/test_h5_negative_matrix.py` — два новых теста
     (`test_baseline_changed_between_plan_and_apply_aborts_whole_write`,
     `test_pav_removed_between_plan_and_apply_aborts_write`).

   Правка помечена в комментариях как **H6** — стадия, о которой ни один из моих
   ревьюеров не знал (им сообщалось только про H1–H5), и содержательно совпадает с
   рекомендацией находки H5-1. Вывод: в той же рабочей копии параллельно идёт окно
   исправления. **Источник до конца не установлен, поэтому изменения не откатывались
   и не стадировались** — прямой урок P1 из H4 («незнакомое изменение tracked-файла
   нельзя откатывать по догадке о происхождении»). Мои коммиты собраны точечным
   `git add` по трём путям и этих файлов не содержат — проверено
   `git diff --name-only db28005..HEAD`.

   **Следствие для доказательной базы:** все четыре проверки (regression 09:29–09:38,
   `check` / `makemigrations` / ruff / black ~09:40) выполнены на дереве
   `db28005` **без** этих изменений. Они валидны ровно для того, что уходит в
   acceptance-PR (три документарных коммита), и **не** относятся к правке H6 —
   её обязано проверить своё окно.

---

# Дополнение окна ACCEPTANCE (второй поток, 2026-07-27)

> Оба окна работали в одной копии параллельно. По решению владельца поток продолжен
> этим окном; правки первого потока не откатывались, документы дополнены, а не
> переписаны. Раздел дополняет §5 и §6 выше и исправляет один факт из §7.

## 8. `codex review` — выполнен (исправление п. 4 §7)

**Вывод «`codex` CLI отсутствует» был неверен.** Бинарь не установлен глобально,
но поставляется в бандле расширения ChatGPT:

```
C:\Users\user\.vscode\extensions\openai.chatgpt-26.721.41059-win32-x64\bin\windows-x86_64\codex.exe
codex-cli 0.146.0-alpha.3.1        # ~/.codex/auth.json валиден
```

Найден поиском `codex.exe` по `%USERPROFILE%` на глубину 8; поиск в п. 4 §7
ограничивался PATH, npm-global, bun/scoop/choco и `~/.codex` и до бандлов
расширений не дошёл.

### 8.1. Как собран дифф для ревью

`codex review` принимает `--commit`, `--base` или `--uncommitted`, но не
произвольный path-ограниченный дифф, а `--commit` несовместим с кастомным
промптом. Поэтому:

1. `git worktree add --detach <tmp> e3e0797^` — пред-волновое состояние (`58ede33`);
2. поверх наложены **только пути контура** (`git checkout db28005 -- …`): модули
   `taxonomy_manifest` / `rules_gate` / `rules_release` / `rules_engine` /
   `tool_type_rollback` / `taxonomy_reverse`, `management/commands/`,
   `apps/catalog/tests/`, `data/catalog_processing_rules/`, `.gitattributes`,
   `apps/catalog/schemas/`, `.github/workflows/tests.yml`, доки контура и три
   контрактных теста H1.4 из `apps/catalog/`;
3. один коммит `42c1ad5` — **43 файла, +12 621 / −489**;
4. `codex review --commit 42c1ad5` в этом worktree.

**Проверка чистоты границ.** Коммиты вне волны в диапазоне: `10f7453` и `bd3ecb2`
(perforatory, PR #593/#594) → `data/attribute_rules.json`,
`apps/catalog/test_attribute_extract.py`; `989aec6` → `docs/catalog/stroitelnyy-roadmap.md`;
`13ad30b` → `.claude/settings.json`. Ни один из этих путей в наложение не входил —
чужие треки в дифф не попали.

Сырой вывод: `scratchpad/wave7/acceptance-codex-review.log`.

### 8.2. Находки codex — поимённо

| # | Находка | Решение | Обоснование |
|---|---|---|---|
| Н-1 (P1) | `tool_type_rollback.py:311-316` — `apply_rollback` не берёт блокировок и не перепроверяет baseline внутри транзакции; конкурентное изменение перезаписывается молча | **принята, исправлена (H6)** | Проверено чтением кода: внутри транзакции сверялось только существование товара и опции. Отягчающее, чего нет в самой находке: `verify_post_state` дефект не ловит — после перезаписи live == цель, post-audit PASS. Совпала с находкой H5-1 первого потока |
| Н-2 (P2) | `enrich_tool_type.py:262-264` — при отсутствии manifest-опции в БД enrichment её создаёт, а `backfill_option_slugs` в той же ситуации fail-closed | **принята, отложена** | Асимметрия подтверждена диффами обоих файлов. Но инвариант «не создавать типы вне манифеста» не нарушен: создаётся ровно manifest-опция, live-identity едет **к** идентичности манифеста. Расходятся политики, не корректность. Приведение к fail-closed — после ACCEPTED |
| Н-3 (P2) | `load_tool_types.py:95-96` — `{existing_slug, mopt.slug} not in allow` уронит `TypeError: unhashable type: 'set'` | **отклонена: ложная** | CPython в `set.__contains__` при неудачном хешировании ключа-`set` повторяет поиск временным `frozenset`. Проверено прогоном: `{'a','b'} in {frozenset({'a','b'})}` вернуло `True`, без исключения. Ни ветка ошибки, ни ветка allow-list не падают |

## 9. Стадия H6 — исправление Н-1 / п. 12 §6

Открыта решением владельца («чинить сейчас, до ACCEPTED»). Код контура ⇒ **отдельная
ветка и отдельный PR**, в acceptance-PR не входит.

**Ветка:** `feature/catalog-wave71-h6-rollback-toctou`, коммит `af29a7f`
(`CLAUDE.md`, `apps/catalog/tool_type_rollback.py`,
`apps/catalog/tests/test_h5_negative_matrix.py`,
`docs/catalog/tool-type-reverse-migration.md`; +180/−13).

**Суть.** Решающее правило вынесено в `_decide(live_row, from_slug, to_slug)` —
общую точку для `plan_rollback` и `apply_rollback`. Внутри транзакции записи
`apply_rollback` берёт `Product` и `ProductAttributeValue` под
`SELECT … FOR UPDATE` (порядок по id), перечитывает live и повторяет сверку.
Дрейф → `RollbackError` до первой записи; товар, уже приведённый к цели чужим
процессом → `noop`; сообщения H5 про исчезнувший товар и исчезнувшую опцию
сохранены дословно (старые тесты не переписывались).

**TDD.** Три сценарных теста написаны до фикса и **падали**:

```
FAILED test_baseline_changed_between_plan_and_apply_aborts_whole_write
FAILED test_pav_removed_between_plan_and_apply_aborts_write
FAILED test_concurrent_rollback_to_same_target_is_counted_as_noop
3 failed, 2 passed
```

**Слабый guard, найденный и исправленный по ходу.** Первая версия
`test_apply_locks_product_and_pav_rows` проверяла наличие `FOR UPDATE` по обеим
таблицам — и **не ловила** мутацию «снять блокировку `Product`»: третий
`FOR UPDATE` по `catalog_product` берёт сам `flush_attrs_cache_merged`. Тест
переписан на проверку **порядка**: первое обращение `apply` к каждой из таблиц
обязано быть блокирующим («блокируй, потом смотри»). После переписывания мутация
ловится.

**Мутационная матрица** (`scratchpad/wave7/h6_mutation_matrix.py`, лог
`h6-mutation-matrix.log`) — **4/4**:

| мутация | результат |
|---|---|
| снятие повторной сверки baseline | тесты падают ✔ |
| снятие блокировки `Product` | тесты падают ✔ |
| снятие блокировки `ProductAttributeValue` | тесты падают ✔ |
| обезвреживание отказа по дрейфу (`if False and drifted`) | тесты падают ✔ |
| чистый прогон после восстановления | PASS, скрипт `exit=0` |

**Остаточный риск** записан в `docs/catalog/tool-type-reverse-migration.md` §4 и в
§9 сводного отчёта: `FOR UPDATE` не мешает чужой транзакции **вставить**
отсутствовавший PAV; полная сериализация потребовала бы `SERIALIZABLE` и
сознательно не вводится.

## 10. Проверки этого потока

| Проверка | Результат |
|---|---|
| Полный regression **до** H6 (дерево `db28005`) | `2 failed, 1934 passed, 1 skipped` (502 s) |
| Полный regression **с** H6 | **`2 failed, 1938 passed, 1 skipped`** (512 s) |
| Арифметика 1 | 1920 (baseline H5) + 14 (чужой трек PR #594) = 1934; junit-дифф: добавилось 14, исчезло 0 |
| Арифметика 2 | 1934 + 4 (новые H6) = **1938**; junit-дифф: добавилось ровно 4 теста H6, исчезло 0 |
| Оба падения | `test_healthcheck_returns_ok` (нет Redis) + `test_release_script_is_executable` (Windows exec bit) — только они |
| Контур H5+H6 | 84 passed (было 81) |
| Catalog suite | 1000 passed, 1 skipped |
| `manage.py check` | 0 issues |
| `makemigrations --check --dry-run` | No changes detected |
| ruff / black (`apps config tests scripts`) | clean; black — 571 files unchanged |
| Гейт по фальшивому sample аудита | `gate_passed=false`, EXIT=2, 403 blocking (`acceptance-findingB-bogus.log`) |
| CI на `28c7bef` (run `30241631114`) | `test` / `lint` / `frontend` / `catalog-rules-gate` / `deploy` — все success |

Regression гонялся **без параллельных прогонов** против общей тестовой БД.

## 11. Состояние на выходе

```
dev        = 3f50376   ahead 5 от origin/dev (28c7bef)
             db28005 · e953f0e · 4256a72 · e8806a4 · 3f50376
             дифф 28c7bef..dev — только CLAUDE.md и два документа плана,
             кода контура нет

feature/catalog-wave71-h6-rollback-toctou = af29a7f   (от dev, до 3f50376)
             код контура H6 + его документация
```

**`git push` и `gh pr create` не выполнялись — ждут явной просьбы владельца.**

Два PR, а не один:

1. **acceptance** (документарный) — `dev` от `origin/dev`;
2. **H6** (код контура) — `feature/catalog-wave71-h6-rollback-toctou`.

## 12. Открытое для владельца

1. **Объявить `WAVE 7.1 ACCEPTED`** — или назвать, чего недостаёт. Рекомендация:
   после того, как H6 пройдёт ревью и CI, иначе заявленный в `CLAUDE.md` §7
   инвариант conflict-guard'а не соответствовал реализации.
2. **Н-2** (`enrich_tool_type` доращивает словарь мимо seed) — привести к fail-closed
   отдельной задачей после ACCEPTED.
3. Смежные находки первого потока по H5, оставшиеся открытыми: `noop` решается только
   по `option_slug` и не учитывает `attrs_cache`; post-audit выполняется после коммита
   и ничего не откатывает; пустой снимок проходит все гарды.
4. **Организационное.** Два окна одновременно правили одни и те же документы приёмки.
   Ни одно не откатило чужое (урок P1 из H4 сработал), но 233-строчный отчёт и три
   коммита были написаны дважды. Правило «одна стадия = одно окно» надо распространить
   и на acceptance.
