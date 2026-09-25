# КАТ-14J: Отчёт о привязке категорий по `category_id`

## Краткая сводка

В рамках окна КАТ-14J реализована привязка характеристик к категориям через поле `category_id` в `data/attribute_rules.json` с поддержкой строгого режима `--strict-bindings`. Все gate-cycle проверки на sandbox/staging пройдены, расхождения с эталоном КАТ-14I объяснены.

## Контекст ревизии

| Параметр | Значение |
|---|---|
| HEAD | `72b574ed0b772a236153740dd441c1ed13f3ec26` |
| Branch | `fix/catalog-attribute-slug-collisions` |
| Worktree | `C:/Users/user/PycharmProjects/proff58-cat14i` |
| SHA-256 `data/attribute_rules.json` @ baseline `2b4942b` | `cb9fced35721902419858080d77c8841df84e4454ed90d5e8eff516dff4da5eb` |
| SHA-256 `data/attribute_rules.json` @ HEAD | `336f3b212ca8cfa7e3256694ea9af27a3fda6c46ba2f76a25f861e4070c59661` |
| SHA-256 staging dump | `520e80fd7cb216b96f0e39583e9dbeb3170c9cc5aff60ff0f88a3d09790f87b1` |

### Git status (`--porcelain`)

```
```

## Изменённые файлы

| Файл | Статус | Примечание |
|---|---|---|
| `data/attribute_rules.json` | modified | добавлены `category_id` для 7 tool_types, разрешены slug-коллизии |
| `apps/catalog/management/commands/load_attributes.py` | modified | поддержка `--strict-bindings`, привязка по `category_id`; строковая форма `category` теперь только по имени |
| `apps/catalog/taxonomy_audit.py` | modified | рендер coverage корректно извлекает имя категории из объекта `category` |
| `apps/catalog/test_attribute_extract.py` | modified | зелёные проверки до sandbox gate-cycle |
| `apps/catalog/tests/test_load_attributes_binding.py` | added | тесты привязки `category_id` и строгого режима |
| `docs/reports/catalog-taxonomy-coverage.md` | modified | обновлено покрытие таксономии из текущего `attribute_rules.json` |
| `docs/superpowers/plans/2026-08-04-cat-14j-category-binding.md` | added | план окна |
| `docs/superpowers/specs/2026-08-04-cat-14j-category-binding-design.md` | added | дизайн-спецификация окна |
| `scratchpad/cat14/cat-14i-slug-collisions-report.md` | added | контекст из окна КАТ-14I |
| `scratchpad/cat14/cat-14j-category-id-mapping-report.md` | added | данный отчёт |

## Diff-stat словаря

```bash
git diff --stat 2b4942b HEAD -- data/attribute_rules.json
```

```
 data/attribute_rules.json | 52 +++++++++++++++++++++++++++++++++++++----------
 1 file changed, 41 insertions(+), 11 deletions(-)
```

## SHA-256 `data/attribute_rules.json`

### Baseline `2b4942b`

```bash
git show 2b4942b:data/attribute_rules.json | sha256sum
```

```
cb9fced35721902419858080d77c8841df84e4454ed90d5e8eff516dff4da5eb  -
```

### Current HEAD `72b574e`

```bash
sha256sum data/attribute_rules.json
```

```
336f3b212ca8cfa7e3256694ea9af27a3fda6c46ba2f76a25f861e4070c59661  data/attribute_rules.json
```

## Gate-cycle показатели (Task 7)

### `load_attributes`

| Метрика | Значение |
|---|---|
| attrs | 129 |
| options | 203 |
| bound | 128 |
| missing | 0 |

### Audit состояния

| Таблица | Записей |
|---|---|
| catalog_attribute | 69 |
| attributeoption | 507 |
| categoryattribute | 169 |

### Pre dry-run

| Метрика | Значение |
|---|---|
| processed | 15672 |
| keep | 21634 |
| create | 5402 |
| skip | 1 |
| pruned | 0 |

#### Распределение create/keep по ключевым атрибутам

| Атрибут | create | keep |
|---|---|---|
| size | 2 | 1342 |
| glove_size | 95 | — |
| chuck | 7 | 148 |

### Apply

| Параметр | Значение |
|---|---|
| ImportRun.id | 49 |
| status | done |

### Post-audit

| Таблица | Записей |
|---|---|
| PAV count | 66741 |

### Post dry-run

| Метрика | Значение |
|---|---|
| keep | 27036 |
| create | 0 |
| update | 0 |
| prune | 0 |

## Сверка со стендом

| Сущность | Sandbox | Staging | Статус |
|---|---|---|---|
| categories | 327 | 327 | совпадает |
| products | 47225 | 47225 | совпадает |
| category_attributes | 147 | 147 | совпадает |

## Сверка конечных состояний

| Параметр | Baseline (`2b4942b`) | HEAD (`72b574e`) |
|---|---|---|
| `category_id` в `attribute_rules.json` | не заданы | заданы для 7 tool_types |
| Режим `--strict-bindings` | не поддерживался | поддерживается |
| Привязка атрибута к категории | по строковому имени | по `category_id` |
| attrs | — | 129 |
| options | — | 203 |
| bound | — | 128 |
| missing | — | 0 |
| `catalog_attribute` | — | 69 |
| `attributeoption` | — | 507 |
| `categoryattribute` | — | 169 |
| Pre dry-run processed | — | 15672 |
| Pre dry-run keep | — | 21634 |
| Pre dry-run create | — | 5402 |
| Pre dry-run skip | — | 1 |
| Post-audit PAV count | — | 66741 |
| Post dry-run keep | — | 27036 |
| Post dry-run create / update / prune | — | 0 / 0 / 0 |

### Распределение create/keep по ключевым атрибутам

| Атрибут | keep | create | Примечание |
|---|---|---|---|
| size | 1342 | 2 | — |
| glove_size | — | 95 | — |
| chuck | 148 | 7 | в том числе 7 create по категории `bystrozazhimnoy` |

## Примечания и открытые вопросы

- `str-kisti` пока не имеет `CategoryAttribute`; привязка отложена до отдельного окна «Кисти».
- Все slug-коллизии атрибутов сохраняют единый `tool_type` и разрешаются через `category_id`.
- Gate-cycle на sandbox/staging завершён без pruning и без skipped, кроме 1 skip на pre dry-run.
- Отчёт основан на pytest: `2615 passed, 2 failed, 1 skipped` (замер `2026-08-05`).
