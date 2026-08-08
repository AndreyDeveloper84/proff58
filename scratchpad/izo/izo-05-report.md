# ИЗО-05 — протокол окна

**Стадия:** правка кода + тесты + sandbox apply/rollback/reapply + полная регрессия.
**Ветка:** `feature/izo-05-rollback-robots` (worktree `C:/Users/user/PycharmProjects/proff58-izo05`,
от `origin/dev` = `983b937`). **Push и PR не делались** — запрещены заданием.
**Стенд не трогался вовсе.** В сеть не ходили: скачивание и robots замоканы,
robots-строки внесены в тесты литералами из локальных фикстур.

---

## 1. Воспроизведение дефектов (красные тесты ДО правки)

### A. `process_batch` не передаёт `source`

Дефект **воспроизведён и подтверждён на текущем коде**. Одноразовый демонстратор
(`scratchpad/izo/izo05/test_defect_a_demo.py`, после снятия показаний удалён)
на немодифицированном `image_pipeline.py` дал:

```
ДЕМО ДЕФЕКТА A: записей прогона 2, source=[ImageSource.MANUAL, ImageSource.MANUAL],
manual в БД 2, откат resanta видит 0 записей, manual_untouched=2
```

То есть пачка прогона легла как `manual`, `build_rollback_plan(source="resanta")`
её не видит (`records_to_delete = 0`), а откат `manual` запрещён по инварианту —
записи пилота были бы **неоткатываемы** и неотличимы от 107 настоящих ручных.

Постоянные тесты (в `apps/catalog/tests/test_image_reversibility.py`) на
неисправленном коде: **6 failed, 18 passed**.

```
FAILED test_process_batch_marks_run_source_not_manual
FAILED test_process_batch_requires_source
FAILED test_process_batch_refuses_manual_source
FAILED test_process_batch_refuses_unknown_source
FAILED test_batch_run_is_rollbackable_and_manual_survives
FAILED test_sandbox_apply_rollback_reapply
6 failed, 18 passed in 14.22s
```

### B. `RobotsGate` игнорирует `*` и `$`

Дефект **воспроизведён**. Новый файл `parser/tests/test_robots.py` на
неисправленном коде (`urllib.robotparser`): **16 failed, 20 passed**
(сохранено в `scratchpad/izo/izo05/red-robots-before.txt`).

Корень: `urllib.robotparser.RuleLine.applies_to` — это
`self.path == "*" or filename.startswith(self.path)`, а `Entry.allowance`
возвращает **первое** подошедшее правило. Значит: `*` в середине шаблона —
литерал, `$` — литерал, приоритета самого длинного правила нет.

Упавшие кейсы (все — реальные ситуации обоих источников):

| Кейс | Правило | URL | Ожидалось |
|---|---|---|---|
| `*` в середине | `Disallow: /wa-data/public/site/*vihr*` | `/wa-data/public/site/2/vihr-1000.jpg` | запрет |
| `*` в середине | `Disallow: /wa-data/public/site/*utake*` | `/wa-data/public/site/2/utake-1000.jpg` | запрет |
| resanta | `Disallow: */filter/*` | `/category/dreli/filter/moshchnost-500/` | запрет |
| resanta | `Disallow: *-vihr*` | `/product/drel-vihr-500/` | запрет |
| resanta | `Disallow: *?page=*` | `/category/dreli/?page=2` | запрет |
| resanta | `Disallow: */?sort=` | `/category/dreli/?sort=price` | запрет |
| vihr | `Disallow: /wa-data/public/site/*resanta*` | `/wa-data/public/site/1/resanta-logo.png` | запрет |
| vihr | `Disallow: */market/` | `/category/nasosy/market/` | запрет |
| vihr | `Disallow: …/product.js?` | `…/product.js?v=3` | запрет |
| `$` на конце | `Disallow: /*.pdf$` | `/docs/a.pdf` | запрет |
| `$` на конце | `Disallow: /$` | `/x` | разрешено |
| длиннейшее | `Disallow: /catalog/` + `Allow: /catalog/tovar/` | `/catalog/tovar/1` | разрешено |
| длиннейшее | `Disallow: /images/` + `Allow: /images/*/thumb/` | `/images/12/thumb/a.jpg` | разрешено |
| равная длина | `Disallow: /x/y` + `Allow: /x/y` | `/x/y` | разрешено |
| пустой `Allow:` | `Allow:` + `Disallow: /private/` | `/private/x` | запрет |
| группы UA | `User-agent: Yandex` … + `User-Agent: *` … | `/catalog/?utm_source=x` | запрет по `*utm*=` |

**Вывод:** оба диагноза ИЗО-04 верны, «чинить рабочий код» не пришлось.

---

## 2. Что изменено

### A. `apps/catalog/image_pipeline.py:218-243` — `ImagePipeline.process_batch`

Сигнатура `process_batch(self, product, urls)` →
`process_batch(self, product, urls, *, source: str)`:

- `source` — **обязательный keyword**: «забыть источник» больше нельзя
  структурно, а не по договорённости;
- `source not in ImageSource.values` → `ValueError`;
- `source == manual` → `ValueError` (тот же инвариант, что уже держат
  `build_plan` и `build_rollback_plan`);
- источник передаётся в `process_url`, который и так проставляет `source_url`,
  `checksum` и `fetched_at`.

`process_url` оставлен с `source=ImageSource.MANUAL` по умолчанию намеренно:
это путь ручной загрузки из админки, и он обязан класть `manual`. Миграция
`0036` **не менялась** (критерий остановки №2 не сработал: правка в коде).

### B. `parser/_fetch_common.py:106-300` — свой matcher robots вместо `urllib.robotparser`

`urllib.robotparser` заменён (задание это разрешает), все ветки покрыты
тестами. Добавлено:

- `_normalize_robots_path` — одна нормализация для обеих сторон сравнения
  (percent-encoding: кириллица в robots против `%D0%BA…` в URL);
- `_pattern_to_regex` — `*` → `.*`, `$` **в самом конце** → якорь конца строки
  (в середине шаблона `$` остаётся литералом);
- `_RobotsRule` / `_RobotsGroup` / `RobotsRules` — правило со своей
  специфичностью (длина шаблона), группы `User-agent`;
- `parse_robots(text)` — разбор: комментарии `#`, строки без `:`, пустые
  `Disallow:`/`Allow:` (не правило), правила до первого `User-agent`
  игнорируются; последовательные `User-agent` — одна группа, строка правила
  закрывает блок агентов;
- `RobotsRules.can_fetch` — выигрывает **самое длинное** совпавшее правило,
  при равной длине — `Allow` (RFC 9309 §2.2.2);
- `RobotsGate` — публичный контракт не изменился (`__init__(user_agent, fetcher)`,
  `can_fetch(url)`, `RobotsUnavailableError`), кэш на хост сохранён; выбор
  группы по UA оставлен ровно тот же, что был в `robotparser` (токен до `/`,
  регистронезависимое вхождение, `*` как запасная группа) — чтобы **не менять
  поведение уже работающего парсера характеристик** (критерий остановки №4 не
  сработал: менять не потребовалось).

Новый файл тестов: `parser/tests/test_robots.py` (36 кейсов).

---

## 3. Sandbox apply / rollback / reapply

**Только локальная тестовая БД** (`localhost:5436`, отдельная база
`proff58_izo05` → `test_proff58_izo05`, `--create-db`; чужая тестовая база не
пересоздавалась). Стенд не трогался. Скачивание замокано, ни одного сетевого
запроса.

Пакет: 3 товара × 3 URL = 9 записей прогона `resanta` поверх 4 записей `manual`.
Протокол — `scratchpad/izo/izo05/sandbox-cycle.txt`:

```
0. до прогона            записей=4   {'manual': 4}                 файлов=4   сирот=0
   APPLY: process_batch вернул 9 записей
1. после apply           записей=13  {'manual': 4, 'resanta': 9}   файлов=13  сирот=0
   REAPPLY (без отката): process_batch вернул 9 записей
2. после повторного apply записей=13  {'manual': 4, 'resanta': 9}   файлов=13  сирот=0
   ОТКАТ: записей под удаление 9, файлов 9, manual не тронут 4
   ПРИМЕНЕНО: записей 9, файлов 9 (не найдено 0)
3. после rollback        записей=4   {'manual': 4}                 файлов=4   сирот=0
   REAPPLY (после отката): process_batch вернул 9 записей
4. после reapply         записей=13  {'manual': 4, 'resanta': 9}   файлов=13  сирот=0
```

Проверено:

- после отката записи прогона исчезли (13 → 4), **все 4 `manual` целы**,
  файлов 13 → 4, осиротевших файлов 0, `missing_file` 0, `checksum`-дрейф 0;
- повторное применение **не падает** на частичных unique-индексах
  `uniq_product_image_checksum` / `uniq_product_image_source_url` и **не плодит
  дублей**: 13 записей до и 13 после;
- та же картинка под другим URL (`https://cdn.v.test/1.png?v=2`) возвращает
  существующую запись, а не создаёт вторую (проверка в постоянном тесте
  `test_sandbox_apply_rollback_reapply`);
- откат исполнялся боевой командой `catalog_images_ops --mode rollback
  --source resanta --apply` с post-audit внутри.

Цикл закреплён постоянным тестом
`apps/catalog/tests/test_image_reversibility.py::test_sandbox_apply_rollback_reapply`.

---

## 4. Регрессия

Свой `DATABASE_URL` (порт 5436, база `proff58_izo05`), `--create-db` на первом
прогоне. Только `uv run python -m pytest`.

| Набор | Baseline (после ИЗО-02) | После правки | Дельта |
|---|---|---|---|
| `apps/catalog` | 1491 passed, 1 skipped | **1497 passed, 1 skipped** | +6 |
| `parser` | 124 passed | **160 passed** | +36 |

Baseline замерен в этом же worktree до правок и совпал с заявленным:
`1491 passed, 1 skipped in 380.66s`.

Объяснение дельты через `--collect-only`:

- `parser`: `pytest parser --collect-only -q` → **160 tests collected**,
  из них `parser/tests/test_robots.py --collect-only -q` → **36 tests
  collected**. 160 − 36 = 124 = baseline. Все 36 — новые кейсы дефекта B;
- `apps/catalog`: +6 = новые тесты дефекта A в `test_image_reversibility.py`
  (`…marks_run_source_not_manual`, `…requires_source`, `…refuses_manual_source`,
  `…refuses_unknown_source`, `…is_rollbackable_and_manual_survives`,
  `…sandbox_apply_rollback_reapply`).

Падений сверх baseline нет. Ни один существующий тест не ослаблен и не удалён.

## 5. Линтеры

```
uv run ruff check apps/catalog parser     → All checks passed!
uv run black --check apps/catalog parser  → 257 files would be left unchanged
```

---

## 6. Смежные дыры — НЕ трогали (предложения владельцу)

Ни одна из них не мешает A и B работать по-настоящему, поэтому в правку не
включены:

1. **`ImagePipeline._download` не шлёт User-Agent** (уходит дефолтный UA
   `urllib3`). Не связано с B: гейт robots живёт в `parser/`, где запросы шлёт
   `PoliteClient`/`BrowserClient` и **свой честный UA они отправляют** —
   несогласованности «проверяем robots для одного UA, а запрос шлём без UA»
   в контуре B нет. В контуре каталога UA-дыра самостоятельная.
2. **`ImagePipeline._download` не спрашивает robots перед скачиванием файла.**
   Контур каталога с `RobotsGate` вообще не связан. Это отдельное решение:
   либо переиспользовать `RobotsGate` из `parser/`, либо качать только те URL,
   которые уже прошли гейт в парсере.
3. **Троттлинга в `ImagePipeline` нет** — пачка уходит подряд без пауз;
   в парсере темп есть, в каталоге нет.
4. **`sort_order` не выставляется** — вся пачка прогона получает `0`, порядок
   фотографий на витрине держится только на `-is_main` из `Meta.ordering`.

Отдельно, из наблюдений окна (не дефект продукта): WebP с `quality=85`
схлопывает близкие сплошные цвета в **одинаковые байты** — тестовые картинки
`(3,3,3)` и `(4,4,4)` дали один checksum, и запись честно отсеклась ключом
`(product, checksum)`. Для реальных фото это не проблема, но при подготовке
фикстур пилота ИЗО-04 картинки надо брать заведомо разные.

---

## 7. Коммиты

Ветка `feature/izo-05-rollback-robots`, локальная. Conventional Commits,
хуки не пропускались.
