# TT-11 — Правила названия окна: разрешение конфликта + покрытие тремя типами

## Цель

1. Закрыть единым механизмом случаи, когда в названии товара признаки двух типов, а побеждает главное существительное, а не то, что идёт после `+`, `с`, дефиса, в скобках или после запятой.
2. Добавить покрытие для трёх ходовых типов без ложных срабатываний.
3. Сохранить девять правых предложений TT-09/TT-10.

## Контур работы

- Работа выполнялась только с артефактами контура `tool_type`:
  - `data/catalog_processing_rules/tool_type.v2.json`
  - `data/catalog_processing_rules/rules_release_manifest.v1.json`
  - gate-фикстуры `apps/catalog/tests/fixtures/phase7d-*`
- База каталога не трогалась: ни импорты, ни применение правил к товарам, ни ручные правки `ProductAttributeValue`.
- Изолированный git worktree: `.worktrees/tt-11`, ветка `feature/tt-11-rules`, база `origin/dev` (`af51d76`).

## Что изменилось

### 1. Negative keywords для существующих правил

| Правило | Добавленные negative keywords | Зачем |
|---------|------------------------------|-------|
| `tt-fonari-akkum` | `шуруп`, `дрель`, `винтоверт`, `яяшуруп` | Отсекать «шуруповёрт + фонарь», где главное существительное — шуруповёрт, а фонарь — комплектация. |
| `tt-izm-shtativy-derzhatel` | `нивелир` | Отсекать нивелиры, у которых в названии есть «держатель» как аксессуар. |
| `tt-lomy-gvozdodery-lom` | `молоток` | Отсекать «молоток-гвоздодер», где главное существительное — молоток. |

### 2. Три новых правила

| rule_ref | option_slug | Ключевые слова | Negative keywords | Источники (derived_from) |
|----------|-------------|----------------|-------------------|--------------------------|
| `tt-dreli-shurupoverty-shurupovert` | `dreli-shurupoverty` | `шуруп`, `дрель`, `винтоверт` | — | `777`, `778` |
| `tt-molotki-molotok` | `molotki` | `молоток` | `отб`, `пневмо`, `отвертк` | `37445`, `37446` |
| `tt-izm-niveliry-nivelir` | `izm-niveliry` | `нивелир` | — | `11141`, `11156` |

Состав ключевых слов согласован с пользователем: `гайковерт` и `отвертк` намеренно исключены из правила `dreli-shurupoverty`, чтобы не откатить TT-08.

### 3. Negative fixtures

Для граничных случаев добавлены rule-scoped negative fixtures:

- `fix-dreli-shurupoverty-gaikovert-434` — гайковёрт в `Аккумуляторный инструмент`, не должен попадать под правило дрелей/шуруповёртов.
- `fix-molotki-otvertka-34161` — «отвёртка шоферская под молоток» — отвёртка, не молоток.
- `fix-izm-niveliry-derzhatel-10631` — держатель в `Измерительный инструмент` без токена `нивелир`.

## Замер по реальным товарам

Универс: активные товары (`status=published` / `is_active`), не `content_locked`, с непустым артикулом.

| | До изменений | После изменений |
|---|---|---|
| ruleset_hash | `9bf0271a61e729a900cda57705bdf785b96496efc462448894b27650a04bf330` | `6231d84309f538b1aa0fa82991bc4e9a0b6c304a714c8bab817f128d944f31cc` |
| Всего правил | 38 | 41 |
| Товаров в замере | 47225 | 47225 |
| **mismatch rows** | **13** | **0** |

### 13 устранённых mismatch

| pid | cur | proposed до | Название | Что исправило |
|-----|-----|-------------|----------|---------------|
| 777 | `dreli-shurupoverty` | `fonari` | Шуруп. аккум. DS12DVF3+ФОНАРЬ; 12V, 2x1.5А/ч, 26Hм | negative keywords у `tt-fonari-akkum` |
| 778 | `dreli-shurupoverty` | `fonari` | Шуруп. аккум. DS12DVF3+ФОНАРЬ; 12V, 2x2.0А/ч, 26Hм | negative keywords у `tt-fonari-akkum` |
| 782 | `dreli-shurupoverty` | `fonari` | Шуруп. аккум. DS14DCL-RA;+фонарь, биты, 14,4V... | negative keywords у `tt-fonari-akkum` |
| 794 | `dreli-shurupoverty` | `fonari` | Шуруп. аккум. DS14DVF3+фонарь; 14,4V... | negative keywords у `tt-fonari-akkum` |
| 804 | `dreli-shurupoverty` | `fonari` | Шуруп. аккум. DS18DVF3-TA+фонарь; 18V... | negative keywords у `tt-fonari-akkum` |
| 805 | `dreli-shurupoverty` | `fonari` | Шуруп. аккум. DS18DVF3-TB+фонарь; 18V... | negative keywords у `tt-fonari-akkum` |
| 964 | `dreli-shurupoverty` | `fonari` | Шуруп. аккум. ЗУБР DB-125-42ABF КОМБИ +УШМ+фонарь... | negative keywords у `tt-fonari-akkum` |
| 975 | `dreli-shurupoverty` | `fonari` | Шуруп. аккум. ЗУБР DL-121-22F 12В 2 АКБ 2А/ч +фонарь... | negative keywords у `tt-fonari-akkum` |
| 1100 | `dreli-shurupoverty` | `fonari` | яяШуруп. аккум. DS12DVFA+фонарь; 12V... | negative keyword `яяшуруп` у `tt-fonari-akkum` |
| 11141 | `izm-niveliry` | `izm-shtativy` | Нивелир лазерный KRAFTOOL LL-3D... держатель ВМ1... | negative keyword `нивелир` у `tt-izm-shtativy-derzhatel` |
| 11156 | `izm-niveliry` | `izm-shtativy` | Нивелир лазерный STAYER SL-3D 50м зеленый луч + микролифт, держатель | negative keyword `нивелир` у `tt-izm-shtativy-derzhatel` |
| 37445 | `molotki` | `lomy-gvozdodery` | Молоток-гвоздодер столярный с фиберглассовой ручкой 450 гр. KRAFTOOL | negative keyword `молоток` у `tt-lomy-gvozdodery-lom` |
| 37446 | `molotki` | `lomy-gvozdodery` | Молоток-гвоздодер столярный с фиберглассовой ручкой 560 гр. KRAFTOOL | negative keyword `молоток` у `tt-lomy-gvozdodery-lom` |

### Примечание про `яяшуруп`

В промпте изначально не было. `pid=1100` («яяШуруп. аккум. DS12DVFA+фонарь») остался бы mismatch, потому что нормализация даёт токен `яяшуруп`. На стенде этот товар деактивирован (CAT-07), но локально активен, поэтому для достижения цели `13 → 0` добавлен отдельный negative keyword.

## Gate-валидация

Команда:

```bash
python manage.py catalog_rules_gate_validate \
  --gate-sample apps/catalog/tests/fixtures/phase7d-gate-sample-official.json \
  --labels apps/catalog/tests/fixtures/phase7d-labels.json \
  --ruleset data/catalog_processing_rules/tool_type.v2.json
```

Результат:

```
rows=103 decisions: correct=102 unverifiable=1
observed_precision=0.9903
wilson95=[0.947041, 0.998284]
gate_passed=true
```

## Release manifest

Перевыпущен командой:

```bash
python manage.py catalog_rules_release_manifest --force
```

- `canonical_hash`: `e54943cb2ca0ac7ac4c7dca07d55d6231fc0997056016cee334ac99b0f076e9b`
- ruleset hash: `6231d84309f538b1aa0fa82991bc4e9a0b6c304a714c8bab817f128d944f31cc`
- Правил: 41
- Пороги: `precision_gate=0.99`, `min_rows_gate=100` — пройдены.

## Тесты

```bash
pytest apps/catalog
```

```
1108 passed, 1 skipped in 162.05s
```

## Проверка отсутствия записей в БД

- `ProductAttributeValue` с `attribute__slug='tool_type'`: **38833** шт.
- За время работы не запускались команды применения правил к товарам, импорта или ручного обновления PAV.
- В git-статусе только JSON-артефакты и scratchpad-файлы; файл БД не отслеживается и не изменялся.

## Изменённые файлы

```
 M apps/catalog/tests/fixtures/phase7d-gate-sample-official.json
 M apps/catalog/tests/fixtures/phase7d-labels.json
 M data/catalog_processing_rules/rules_release_manifest.v1.json
 M data/catalog_processing_rules/tool_type.v2.json
?? scratchpad/catalog/tt-11-measure-before.json
?? scratchpad/catalog/tt-11-measure.json
?? scratchpad/catalog/tt-11-report.md
```

## Следующий шаг

Точечный `git add` + `git commit` в worktree. Push/PR — только по явной просьбе.
