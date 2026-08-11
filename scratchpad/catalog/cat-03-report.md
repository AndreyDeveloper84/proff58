# CAT-03 · Протокол: пер-категорийная подпись характеристики в фасетах

Исполнитель: окно CAT-03 · 2026-07-28 · ветка `dev`.

## Решение по варианту

Выбран **вариант переопределения подписи в `CategoryAttribute`** (поле `display_name`),
не разведение атрибутов. Обоснование по коду:

- Подпись фасета эмитится в одном месте — `apps/catalog/facets.py` (`build_facets`,
  `"name": attr.name`) и TypePanel (`_build_tool_type_panel`); атрибуты категории
  собирает `_category_filter_attributes` (`apps/catalog/queries.py`), который уже
  пробрасывает per-category метаданные транзиентом на `Attribute` (`_facet_group`,
  closest-wins). Переопределение легло ровно в этот механизм — новых запросов и
  изменений типов не потребовалось.
- Ключ фильтра — `Attribute.slug`, в ответе и в `attrs_cache` он от имени не зависит;
  переопределение подписи его не трогает по построению.
- Разведение `size` на два атрибута потребовало бы миграции 1594 значений,
  правки `attribute_rules.json` и повторного прогона правил — всё это запрещено
  границами задачи и не нужно для смены подписи.

Продуктовых вопросов (разные единицы измерения и т.п.) не всплыло: `unit` у атрибута
общий («мм») и для угольников корректен.

## Изменения

- `apps/catalog/models.py` — `CategoryAttribute.display_name`
  (CharField, blank=True; пусто = имя атрибута), help_text для куратора.
- `apps/catalog/migrations/0028_categoryattribute_display_name.py` — AddField,
  неразрушающая; обратимость проверена: `migrate catalog 0027` → `migrate catalog` — OK.
- `apps/catalog/queries.py` — `_category_filter_attributes` пробрасывает
  `display_name` транзиентом `attribute._display_name` из ближайшей строки
  (тот же closest-wins, что и `_facet_group`).
- `apps/catalog/facets.py` — фасет и TypePanel эмитят
  `getattr(attr, "_display_name", "") or attr.name`; `slug`, `unit`, счётчики не менялись.
- `apps/catalog/admin.py` — поле `display_name` добавлено в `CategoryAttributeInline`
  (кураторская подсказка — в help_text модели).
- `apps/catalog/test_facets.py` — 3 новых теста (см. ниже).

**Фронт не правился**: подпись берётся из API — `frontend/lib/adapters.ts`
(`label: af.name`, оба пути range/checkbox). Хардкода имени нет
(проверено grep по `frontend/{app,components,lib}`: «под ключ», «Размер» — 0 совпадений).
Сверка с gitlab: `origin/dev` опережает `gitlab/dev` на 62 коммита, дивергенции нет,
конфликта зон с фронтенд-командой нет (файлы фронта не тронуты).

## Применение к данным

- `CategoryAttribute(category=izmeritelnyy-ugolniki-i-lineyki, attribute=size).display_name
  = "Размер"` — проставлено в локальной БД. Выбор формулировки: «Размер» — для угольника
  `size` — длина стороны в мм; «под ключ» там бессмысленно. Единица («мм») не менялась.
- Остальные 4 строки `size` (ruchnoy-instrument, ruchnoy, ruchnoy-golovki-…, ruchnoy-klyuchi)
  — без переопределения, контрольным скриптом подтверждено `display_name == ""`.
- Значения характеристик, `Attribute`, `AttributeOption` не тронуты; новых не создано
  (контроль: `ProductAttributeValue` по `size` в локальной копии — 1451, записей в
  значения не выполнялось; на staging их 1594 — туда код ещё не катился).

## Доказательства

Локальная БД, реальный facets-view (`APIClient`, скрипт
`scratchpad/catalog/cat03_e2e_check.py`):

```
izmeritelnyy-ugolniki-i-lineyki -> ('size', 'Размер', 'мм')
ruchnoy-klyuchi                 -> ('size', 'Размер «под ключ»', 'мм')
```

Baseline живых запросов к `dev.proff58.ru` ДО деплоя (обе страницы — старое поведение):

```
/api/catalog/categories/izmeritelnyy-ugolniki-i-lineyki/facets/ → size | Размер «под ключ» | мм
/api/catalog/categories/ruchnoy-klyuchi/facets/                 → size | Размер «под ключ» | мм
```

Живую проверку «после» на `dev.proff58.ru` выполнить нельзя без деплоя: staging катится
из `dev` через CI (`deploy.yml`), а push/PR — только по явной просьбе владельца.
Пункт приёмки «применена на staging + живые запросы» — **ожидает решения владельца
о push/PR**; после деплоя достаточно проставить `display_name` в БД staging (админка
или shell) и повторить те же два запроса.

## Тесты

`apps/catalog/test_facets.py` (+3):

- `test_display_name_override` — переопределение отдаётся, `slug` и `unit` неизменны;
- `test_display_name_fallback_to_attribute_name` — пустое поле → имя атрибута;
- `test_display_name_closest_wins` — override листа не трогает родителя (общий атрибут).

`pytest apps/catalog/test_facets.py` — **47 passed**.

## Regression

- Арифметика: `pytest apps tests -q` — **2 failed, 2051 passed, 1 skipped** (8:25).
  Оба падения — baseline-окружение, не регрессия:
  `test_regression_mvp.py::test_healthcheck_returns_ok` (нет Redis),
  `test_deploy_release.py::test_release_script_is_executable` (Windows exec bit).
  Третьего падения нет.
- Особенность окружения: полный `pytest` без аргументов падает на сборе (1311 error)
  из-за чужого неотслеживаемого каталога `.codex-ai-bot-platform-pr1092/` — в
  `pyproject.toml` `norecursedirs` переопределён без `.*`, pytest лезет в dotdir.
  Не регрессия CAT-03; прогон выполнен как `pytest apps tests` (тот же объём, что baseline).

## Границы — соблюдены

- `attribute_rules.json`, контур `tool_type` (manifest/gate/ruleset) не тронуты.
- Глобальные команды (`enrich_attributes`, `rebuild_attrs_cache`) не запускались.
- Данные товаров не менялись; миграция обратима и неразрушающая.
- Push/PR не выполнялись.
- Рабочие скрипты-артефакты: `scratchpad/catalog/cat03_check.py`,
  `cat03_facets_check.py`, `cat03_e2e_check.py`.
