# Phase 7A.2 — DEVIATION-2 Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Устранить DEVIATION-2 — duplicate slug `steplery` у двух живых `AttributeOption` — по утверждённой архитектуре c+: обе таксономические сущности сохраняются, записи id=16 даётся новый уникальный slug, вводится DB-констрейнт `(attribute, slug)`, все slug-lookup переводятся на fail-fast `.get()`, seed-импорт валидируется до записи.

**Architecture:** Точечная правка seed (`data/tool_type_rules.json`) + preflight-валидация в `load_tool_types` + строгие `.get()` в `processing.py`/`provenance.py` + одна миграция (data re-slug с guard + partial UniqueConstraint) + тесты инвариантов. PAV, `attrs_cache`, `sort_order`, ruleset v1 и pinned taxonomy export не изменяются.

**Tech Stack:** Django/PostgreSQL, pytest (`pyproject.toml`: `DJANGO_SETTINGS_MODULE=config.settings.dev`, `--reuse-db`), локальный runner `./.venv/Scripts/python.exe`.

## Контекст (из Phase 7A.1 investigation)

- Дубль единственный в каталоге: `tool_type` / `steplery` ×2 —
  **id=16** «Степлеры и заклёпочники» (sort_order=15, 10 PAV/10 товаров),
  **id=73** «Степлеры (скобозабивные)» (sort_order=28, 42 PAV/42 товара).
- Каноническая запись (решение пользователя): **id=73** сохраняет slug `steplery`.
- Новый slug для id=16: **`steplery-i-zaklepochniki`** (ровно вывод `slugify_value('Степлеры и заклёпочники')`; pre-flight на staging: свободен, 0 конфликтов).
- Дивергенция подсистем: apply/provenance `.first()` → id=16; facets last-write-wins → id=73. После remediation обе подсистемы резолвят однозначно.
- Root cause: `data/tool_type_rules.json:167` и `:766` — дублированный slug в seed; `unique_together = [(attribute, value)]` (`apps/catalog/models.py:167`); constraint на `(attribute, slug)` отсутствует.
- `Attribute.slug` уже `unique=True` (`models.py:127`) — attribute-level lookup безопасны; меняются только для единообразия контракта в затрагиваемых функциях.
- `enrich_tool_type.py:214-220` строит `opt_by_slug` dict (last-write-wins) — после устранения дубля нормализуется автоматически, код не меняется.
- `load_attributes.py:101` пишет option slug из seed — тот же класс риска; в scope НЕ входит (в его seed дублей нет — доказано инвариант-SELECT из Phase 7A.1), системную защиту даёт новый DB-констрейнт.

## Global Constraints

- Только перечисленные файлы; никаких изменений PAV/`attrs_cache`/`sort_order`/ruleset v1/corpus fixture/pinned taxonomy export.
- Pinned taxonomy export (`data/catalog_processing_rules/tool_type_taxonomy_export.v1.json`) — исторический артефакт Phase 7A; НЕ регенерируется; его integrity-тест не трогаем (он фиксирует исторический дубль как факт).
- Новый slug строго `steplery-i-zaklepochniki`; id=73 и slug `steplery` не изменяются.
- Fail-fast: нарушение инварианта = громкая ошибка (`CommandError` / reason_code `option_slug_conflict` / `IntegrityError`), не молчаливый выбор.
- Миграция идемпотентна и guarded: свежая БД (нет id=16) — no-op; неожиданное состояние id=16 — RuntimeError (остановка до ручной проверки).
- Каждый коммит проходит: `./.venv/Scripts/python.exe -m pytest <затронутые тесты> -q`.
- Перед PR — полный сьют: `./.venv/Scripts/python.exe -m pytest -q` (baseline: 1712 passed, 1 skipped + 2 известных env-фейла: Redis healthcheck 503 и Windows exec bit на `docker/release.sh` — НЕ дефекты).
- Phase 7B этот план НЕ авторизует. Merge/deploy — отдельные чекпоинты пользователя.

---

### Task 1: Seed fix + repo-тест уникальности slug

**Files:**
- Modify: `data/tool_type_rules.json:167`
- Test: `apps/catalog/tests/test_tool_type_seed_integrity.py` (create)

**Interfaces:**
- Consumes: `ToolTypeRules.from_file(path)`, `rules.categories`, `rules.options(category) -> list[Rule]`, `Rule.slug` (`apps/catalog/tool_type.py:120-151`); `data_dir()` (`apps/catalog/ingest.py`).
- Produces: инвариант «в seed нет duplicate option slug», используемый Task 2.

- [ ] **Step 1: Написать падающий тест**

```python
"""Инвариант seed-файла tool_type: slug отображается ровно в одно value.

DEVIATION-2: «Степлеры и заклёпочники» и «Степлеры (скобозабивные)» имели
общий slug steplery — slug переставал быть функцией value. Повтор одной пары
(value, slug) в нескольких категориях ЛЕГАЛЕН (loader дедупит по value);
недопустим именно slug с >1 distinct value.
"""

from apps.catalog.ingest import data_dir
from apps.catalog.tool_type import ToolTypeRules


def _seed_slug_values() -> dict[str, set[str]]:
    rules = ToolTypeRules.from_file(f"{data_dir()}/tool_type_rules.json")
    slug_values: dict[str, set[str]] = {}
    for cat in rules.categories:
        for r in rules.options(cat.category):
            if r.slug:
                slug_values.setdefault(r.slug, set()).add(r.tool_type)
    return slug_values


def test_tool_type_seed_slug_maps_to_single_value():
    slug_values = _seed_slug_values()
    ambiguous = {slug: sorted(vals) for slug, vals in slug_values.items() if len(vals) > 1}
    assert ambiguous == {}, f"slug maps to multiple values in tool_type_rules.json: {ambiguous}"
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `./.venv/Scripts/python.exe -m pytest apps/catalog/tests/test_tool_type_seed_integrity.py -v`
Expected: FAIL, `slug maps to multiple values in tool_type_rules.json: {'steplery': [...]}` — и ТОЛЬКО steplery (повторы mfi/shlifmashiny/svar-klemmy/zaryadnye с одним value легальны и тестом не ловятся)

- [ ] **Step 3: Исправить seed**

В `data/tool_type_rules.json` у записи `"tool_type": "Степлеры и заклёпочники"` (строка ~166-167) заменить `"slug": "steplery"` на `"slug": "steplery-i-zaklepochniki"`. Запись «Степлеры (скобозабивные)» (~строка 765-766) НЕ трогать. Проверить, что JSON парсится: `./.venv/Scripts/python.exe -c "import json; json.load(open('data/tool_type_rules.json', encoding='utf-8'))"`.

- [ ] **Step 4: Убедиться, что тест проходит**

Run: `./.venv/Scripts/python.exe -m pytest apps/catalog/tests/test_tool_type_seed_integrity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add data/tool_type_rules.json apps/catalog/tests/test_tool_type_seed_integrity.py
git commit -m "fix(catalog): seed tool_type — уникальный slug для «Степлеры и заклёпочники» (DEVIATION-2)"
```

---

### Task 2: Preflight-валидация slug в load_tool_types

**Files:**
- Modify: `apps/catalog/management/commands/load_tool_types.py`
- Test: `apps/catalog/tests/test_load_tool_types_slug_guard.py` (create)

**Interfaces:**
- Consumes: `ToolTypeRules` API из Task 1; `AttributeOption` (`apps/catalog/models.py:150`).
- Produces: `Command._validate_option_slugs(rules) -> None`. Контракт — **slug обязан отображаться ровно в одно distinct value** (повтор пары (value, slug) в нескольких категориях легален — loader дедупит по value). `CommandError` трёх классов: (а) `duplicate option slugs in seed` — slug с >1 distinct value в seed; (б) `duplicate option slugs in DB` — в БД уже >1 записи на slug; (в) `option slug conflicts with DB` — одна DB-запись на slug с другим value. Одна DB-запись с тем же value — допустимо. Вызывается в `handle()` ДО `transaction.atomic()`.

- [ ] **Step 1: Написать падающие тесты**

```python
"""Preflight-валидация option slug в load_tool_types (DEVIATION-2)."""

import json
from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.models import Attribute, AttributeOption, AttributeType


def _rules_file(tmp_path, rules):
    payload = {
        "categories": [
            {"category": "Ручной инструмент", "extraction": "priority_keyword", "rules": rules}
        ]
    }
    path = tmp_path / "tool_type_rules.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return tmp_path


@pytest.mark.django_db
def test_duplicate_slugs_in_seed_rejected(tmp_path):
    """Один slug у двух разных значений в seed — импорт запрещён."""
    base = _rules_file(
        tmp_path,
        [
            {"tool_type": "Степлеры и заклёпочники", "slug": "steplery"},
            {"tool_type": "Степлеры (скобозабивные)", "slug": "steplery"},
        ],
    )
    with pytest.raises(CommandError, match="duplicate option slugs in seed"):
        call_command("load_tool_types", path=str(base))


@pytest.mark.django_db
def test_same_value_slug_repeat_in_seed_allowed(tmp_path):
    """Повтор пары (value, slug) в нескольких категориях — легален (дедуп по value)."""
    base = _rules_file(
        tmp_path,
        [
            {"tool_type": "Зарядные устройства", "slug": "zaryadnye"},
            {"tool_type": "Зарядные устройства", "slug": "zaryadnye"},
        ],
    )
    call_command("load_tool_types", path=str(base))
    assert AttributeOption.objects.count() == 1


@pytest.mark.django_db
def test_duplicate_slug_already_in_db_rejected(tmp_path):
    """В БД уже >1 записи на slug (состояние до констрейнта) — импорт запрещён.

    Дубль в тестовой БД через ORM не создать (констрейнт миграции 0027),
    поэтому выборка мокается — проверяется именно логика multiplicity guard.
    """
    Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )
    base = _rules_file(
        tmp_path,
        [{"tool_type": "Степлеры (скобозабивные)", "slug": "steplery"}],
    )
    fake_rows = [
        ("steplery", "Степлеры и заклёпочники"),
        ("steplery", "Степлеры (скобозабивные)"),
    ]
    qs = Mock()
    qs.values_list.return_value = fake_rows
    with patch.object(AttributeOption.objects, "filter", return_value=qs):
        with pytest.raises(CommandError, match="duplicate option slugs in DB"):
            call_command("load_tool_types", path=str(base))


@pytest.mark.django_db
def test_slug_value_conflict_with_db_rejected(tmp_path):
    """Одна DB-запись на slug, но с другим value — импорт запрещён."""
    attr = Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )
    AttributeOption.objects.create(attribute=attr, value="Степлеры (скобозабивные)", slug="steplery")
    base = _rules_file(
        tmp_path,
        [{"tool_type": "Степлеры и заклёпочники", "slug": "steplery"}],
    )
    with pytest.raises(CommandError, match="option slug conflicts with DB"):
        call_command("load_tool_types", path=str(base))


@pytest.mark.django_db
def test_valid_seed_passes(tmp_path):
    base = _rules_file(
        tmp_path,
        [
            {"tool_type": "Степлеры и заклёпочники", "slug": "steplery-i-zaklepochniki"},
            {"tool_type": "Степлеры (скобозабивные)", "slug": "steplery"},
        ],
    )
    call_command("load_tool_types", path=str(base))
    assert AttributeOption.objects.count() == 2
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `./.venv/Scripts/python.exe -m pytest apps/catalog/tests/test_load_tool_types_slug_guard.py -v`
Expected: FAIL у всех 5 тестов (preflight отсутствует — CommandError не бросается, дубли загружаются)

- [ ] **Step 3: Реализация**

В `load_tool_types.py`: импорт `from django.core.management.base import BaseCommand, CommandError`; добавить метод и вызов:

```python
    def handle(self, *args, **options):
        base = options["path"] or data_dir()
        rules = ToolTypeRules.from_file(f"{base}/tool_type_rules.json")
        self._validate_option_slugs(rules)

        with transaction.atomic():
            ...

    def _validate_option_slugs(self, rules: ToolTypeRules) -> None:
        """Fail-fast: slug обязан отображаться ровно в одно value; конфликты с БД запрещены.

        Повтор пары (value, slug) в нескольких категориях легален (дедуп по value);
        недопустим slug с >1 distinct value (DEVIATION-2).
        """
        slug_values: dict[str, set[str]] = {}
        for cat in rules.categories:
            for rule in rules.options(cat.category):
                if rule.slug:
                    slug_values.setdefault(rule.slug, set()).add(rule.tool_type)
        ambiguous = {slug: sorted(vals) for slug, vals in slug_values.items() if len(vals) > 1}
        if ambiguous:
            details = "; ".join(f"{slug}: {vals}" for slug, vals in ambiguous.items())
            raise CommandError(f"duplicate option slugs in seed: {details}")

        existing_rows = AttributeOption.objects.filter(
            attribute__slug=TOOL_TYPE_SLUG, slug__in=slug_values
        ).values_list("slug", "value")
        db_values: dict[str, list[str]] = {}
        for slug, value in existing_rows:
            db_values.setdefault(slug, []).append(value)
        db_duplicates = {slug: vals for slug, vals in db_values.items() if len(vals) > 1}
        if db_duplicates:
            details = "; ".join(
                f"{slug} x{len(vals)}: {sorted(vals)}" for slug, vals in db_duplicates.items()
            )
            raise CommandError(f"duplicate option slugs in DB: {details}")
        conflicts = {
            slug: (vals[0], next(iter(slug_values[slug])))
            for slug, vals in db_values.items()
            if vals[0] != next(iter(slug_values[slug]))
        }
        if conflicts:
            details = "; ".join(
                f"{slug}: db={db_val!r} vs seed={seed_val!r}"
                for slug, (db_val, seed_val) in conflicts.items()
            )
            raise CommandError(f"option slug conflicts with DB: {details}")
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `./.venv/Scripts/python.exe -m pytest apps/catalog/tests/test_load_tool_types_slug_guard.py -v`
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add apps/catalog/management/commands/load_tool_types.py apps/catalog/tests/test_load_tool_types_slug_guard.py
git commit -m "feat(catalog): load_tool_types — fail-fast валидация duplicate option slug (DEVIATION-2)"
```

---

### Task 3: Fail-fast .get() в slug-lookup (processing.py, provenance.py)

**Files:**
- Modify: `apps/catalog/processing.py:324-330` и `apps/catalog/processing.py:570-588`
- Modify: `apps/catalog/provenance.py:153-171`
- Test (modify, append): `apps/catalog/tests/test_processing_service.py` — 2 новых теста, переиспользуют фикстуры файла (`feature_enabled`, `reviewer`, `attr`, `drill_option`, `_product`, `_run`, `_item`, `_cmd`, `_propose`, `_approve`)
- Test (modify, append): `apps/catalog/tests/test_provenance.py` — 1 новый тест, переиспользует `_product`, `_cmd`, `prov`

**Interfaces:**
- Consumes: существующие контракты `CatalogValidationResult(valid, reason)`, `CatalogDecisionResult(status, change_id, reason)`, `ApplyResult(status, reason)` (`provenance.py:78-80`); `_mark_item_needs_review`.
- Produces: новый reason code **`option_slug_conflict`** (≤ 32 символов — влезает в `CatalogChange.reason_code`); семантика: DoesNotExist → прежние коды (`missing_attribute` / `unknown_option` / `"unknown option"`), MultipleObjectsReturned → `option_slug_conflict` (processing) / `ApplyResult("invalid", "option slug conflict")` (provenance). Существующие тесты (`test_unknown_option_invalid`, `test_validate_detects_unknown_option`, `test_apply_unknown_option_invalid`) должны остаться зелёными без правок.

- [ ] **Step 1: Написать падающие тесты**

Append в `apps/catalog/tests/test_processing_service.py` (добавить импорты `from unittest.mock import patch` и `CatalogChange`/`AttributeOption`, если их ещё нет в файле):

```python
@pytest.mark.django_db
def test_validate_option_slug_conflict_is_loud(feature_enabled, attr, drill_option):
    """Дубль option slug при валидации — громкая ошибка, не молчаливый .first()."""
    p = _product(slug="p-slug-conflict-validate")
    run = _run()
    item = _item(run, p)
    proposed = _propose(_cmd(item, drill_option.slug))

    with patch.object(
        AttributeOption.objects, "get", side_effect=AttributeOption.MultipleObjectsReturned
    ):
        validated = processing.validate_catalog_change(proposed.change_id)
    assert validated.valid is False
    assert validated.reason == "option_slug_conflict"


@pytest.mark.django_db
def test_apply_option_slug_conflict_is_loud(feature_enabled, reviewer, attr, drill_option):
    """Дубль option slug при apply — change INVALID с reason_code=option_slug_conflict."""
    p = _product(slug="p-slug-conflict-apply")
    run = _run()
    item = _item(run, p)
    proposed = _propose(_cmd(item, drill_option.slug))
    reviewed = _approve(proposed.change_id, reviewer)
    assert reviewed.status == "approved"

    with patch.object(
        AttributeOption.objects, "get", side_effect=AttributeOption.MultipleObjectsReturned
    ):
        result = processing.apply_catalog_change(proposed.change_id)
    assert result.status == "invalid"
    change = CatalogChange.objects.get(pk=proposed.change_id)
    assert change.reason_code == "option_slug_conflict"
```

Append в `apps/catalog/tests/test_provenance.py` (импорты `patch`, `AttributeOption` — по необходимости):

```python
@pytest.mark.django_db
def test_apply_option_slug_conflict_invalid():
    """Дубль option slug в provenance — ApplyResult(invalid, 'option slug conflict')."""
    p = _product()
    Attribute.objects.create(name="Патрон", slug="chuck", attribute_type=AttributeType.SELECT)
    cmd = _cmd(
        p,
        target_kind="attribute",
        attribute_slug="chuck",
        value={"type": "option", "value": "sds-plus"},
        observed_value_hash=prov.value_hash(None),
        observed_source="",
    )
    with patch.object(
        AttributeOption.objects, "get", side_effect=AttributeOption.MultipleObjectsReturned
    ):
        r = prov.apply_sourced_value(cmd)
    assert r.status == "invalid"
    assert r.reason == "option slug conflict"
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `./.venv/Scripts/python.exe -m pytest apps/catalog/tests/test_processing_service.py::test_validate_option_slug_conflict_is_loud apps/catalog/tests/test_processing_service.py::test_apply_option_slug_conflict_is_loud apps/catalog/tests/test_provenance.py::test_apply_option_slug_conflict_invalid -v`
Expected: FAIL у всех трёх — текущий код идёт через `.filter().first()`, patched `.get` не вызывается (validate вернёт valid, apply вернёт applied, provenance вернёт `"unknown option"`)

- [ ] **Step 3: Реализация — processing.py validate (324-330)**

```python
    try:
        attr = Attribute.objects.get(slug=TOOL_TYPE_SLUG)
    except Attribute.DoesNotExist:
        return CatalogValidationResult(False, "missing_attribute")
    option_slug = change.proposed_value.get("option_slug")
    try:
        AttributeOption.objects.get(attribute=attr, slug=option_slug)
    except AttributeOption.DoesNotExist:
        return CatalogValidationResult(False, "unknown_option")
    except AttributeOption.MultipleObjectsReturned:
        return CatalogValidationResult(False, "option_slug_conflict")
```

- [ ] **Step 4: Реализация — processing.py apply (570-588)**

Та же замена `.filter(...).first()` → `.get(...)` с тремя ветками; ветка MultipleObjectsReturned зеркалит ветку `unknown_option` (change INVALID + `_mark_item_needs_review`), но `reason_code="option_slug_conflict"`, `reason_detail=f"multiple tool_type options for slug: {option_slug}"`.

- [ ] **Step 5: Реализация — provenance.py (153-171)**

```python
    try:
        attr = Attribute.objects.get(slug=cmd.attribute_slug)
    except Attribute.DoesNotExist:
        return ApplyResult("missing_attribute")
    ...
    if is_option:  # #371/#9b: select/multiselect читаются из value_option, не value_text
        raw = cmd.value.get("value")
        try:
            option = AttributeOption.objects.get(attribute=attr, slug=raw)
        except AttributeOption.DoesNotExist:
            try:
                option = AttributeOption.objects.get(attribute=attr, value=raw)
            except (AttributeOption.DoesNotExist, AttributeOption.MultipleObjectsReturned):
                return ApplyResult("invalid", "unknown option")
        except AttributeOption.MultipleObjectsReturned:
            return ApplyResult("invalid", "option slug conflict")
```

- [ ] **Step 6: Прогнать новые и существующие тесты затронутых модулей**

Run: `./.venv/Scripts/python.exe -m pytest apps/catalog/tests/test_processing_service.py apps/catalog/tests/test_provenance.py -q`
Expected: все PASSED (включая прежние `unknown_option`/`missing_attribute` сценарии)

- [ ] **Step 7: Commit**

```bash
git add apps/catalog/processing.py apps/catalog/provenance.py apps/catalog/tests/test_processing_service.py apps/catalog/tests/test_provenance.py
git commit -m "refactor(catalog): fail-fast .get() для option slug lookup — option_slug_conflict (DEVIATION-2)"
```

---

### Task 4: Миграция 0027 — re-slug id=16 + partial UniqueConstraint

**Files:**
- Create: `apps/catalog/migrations/0027_reslug_steplery_unique_option_slug.py`
- Test: `apps/catalog/tests/test_migration_0027_guards.py` (create)

**Interfaces:**
- Consumes: состояние staging из Phase 7A.1 (id=16: value «Степлеры и заклёпочники», slug `steplery`, sort_order 15).
- Produces: схема с констрейнтом `uniq_attributeoption_attr_slug_nonempty`; guard-семантика миграции (idempotent / no-op / RuntimeError).

- [ ] **Step 1: Написать миграцию**

```python
"""DEVIATION-2: re-slug option id=16 + уникальность (attribute, slug) для непустых slug.

Порядок операций важен: сначала data re-slug (устраняет единственный дубль),
затем констрейнт. Guard: свежая БД без id=16 — no-op; уже re-slugged — no-op;
неожиданное состояние id=16 — RuntimeError (остановка до ручной проверки).
"""

from django.db import migrations, models
from django.db.models import Q

OPTION_ID = 16
EXPECTED_VALUE = "Степлеры и заклёпочники"
OLD_SLUG = "steplery"
NEW_SLUG = "steplery-i-zaklepochniki"


def reslug_forward(apps, schema_editor):
    AttributeOption = apps.get_model("catalog", "AttributeOption")
    try:
        opt = AttributeOption.objects.get(pk=OPTION_ID)
    except AttributeOption.DoesNotExist:
        return  # свежая БД без исторических данных — нечего мигрировать
    if opt.slug == NEW_SLUG:
        return  # уже применено (идемпотентность)
    if opt.value != EXPECTED_VALUE or opt.slug != OLD_SLUG:
        raise RuntimeError(
            f"DEVIATION-2 reslug guard: option {OPTION_ID} имеет неожиданные "
            f"value/slug: {opt.value!r}/{opt.slug!r}; ожидались "
            f"{EXPECTED_VALUE!r}/{OLD_SLUG!r}. Миграция остановлена."
        )
    if AttributeOption.objects.filter(attribute_id=opt.attribute_id, slug=NEW_SLUG).exists():
        raise RuntimeError(f"DEVIATION-2 reslug guard: slug {NEW_SLUG!r} уже занят.")
    opt.slug = NEW_SLUG
    opt.save(update_fields=["slug"])


def reslug_backward(apps, schema_editor):
    AttributeOption = apps.get_model("catalog", "AttributeOption")
    AttributeOption.objects.filter(pk=OPTION_ID, slug=NEW_SLUG).update(slug=OLD_SLUG)


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0026_catalogchange_applied_by_catalogchange_comment_and_more"),
    ]

    operations = [
        migrations.RunPython(reslug_forward, reslug_backward),
        migrations.AddConstraint(
            model_name="attributeoption",
            constraint=models.UniqueConstraint(
                fields=["attribute", "slug"],
                condition=~Q(slug=""),
                name="uniq_attributeoption_attr_slug_nonempty",
            ),
        ),
    ]
```

- [ ] **Step 2: Написать guard-тесты миграции**

Test: `apps/catalog/tests/test_migration_0027_guards.py` (create). Прямой вызов функций миграции (без доп. зависимостей), `apps` — глобальный реестр:

```python
"""Guard-сценарии миграции 0027 (DEVIATION-2): no-op / idempotent / RuntimeError."""

import importlib.util
from pathlib import Path

import pytest
from django.apps import apps as global_apps

from apps.catalog.models import Attribute, AttributeOption, AttributeType

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "0027_reslug_steplery_unique_option_slug.py"
)
_spec = importlib.util.spec_from_file_location("migration_0027", _MIGRATION_PATH)
_mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mig)


def _attr():
    return Attribute.objects.create(
        slug="tool_type", name="T", attribute_type=AttributeType.SELECT
    )


@pytest.mark.django_db
def test_reslug_noop_without_option_16():
    _attr()
    _mig.reslug_forward(global_apps, None)  # нет id=16 — no-op
    assert AttributeOption.objects.count() == 0


@pytest.mark.django_db
def test_reslug_noop_when_already_applied():
    AttributeOption.objects.create(
        pk=16,
        attribute=_attr(),
        value="Степлеры и заклёпочники",
        slug="steplery-i-zaklepochniki",
    )
    _mig.reslug_forward(global_apps, None)
    assert AttributeOption.objects.get(pk=16).slug == "steplery-i-zaklepochniki"


@pytest.mark.django_db
def test_reslug_happy_path():
    AttributeOption.objects.create(
        pk=16, attribute=_attr(), value="Степлеры и заклёпочники", slug="steplery"
    )
    _mig.reslug_forward(global_apps, None)
    assert AttributeOption.objects.get(pk=16).slug == "steplery-i-zaklepochniki"


@pytest.mark.django_db
def test_reslug_guard_raises_on_unexpected_state():
    AttributeOption.objects.create(
        pk=16, attribute=_attr(), value="Другое значение", slug="steplery"
    )
    with pytest.raises(RuntimeError, match="reslug guard"):
        _mig.reslug_forward(global_apps, None)
```

- [ ] **Step 3: Прогнать guard-тесты**

Run: `./.venv/Scripts/python.exe -m pytest apps/catalog/tests/test_migration_0027_guards.py -v`
Expected: 4 PASSED

- [ ] **Step 4: Проверить план миграции и применимость на тестовой БД**

Run: `./.venv/Scripts/python.exe manage.py sqlmigrate catalog 0027 | head -30`
Expected: `UPDATE ... slug ... WHERE id = 16` внутри RunPython не виден (это Python), констрейнт — `CREATE UNIQUE INDEX ... WHERE NOT (slug = '')`.
Run: `./.venv/Scripts/python.exe -m pytest apps/catalog/tests/ -q --create-db`
Expected: PASSED — на пустой тестовой БД guard no-op, констрейнт создаётся.

- [ ] **Step 5: Commit**

```bash
git add apps/catalog/migrations/0027_reslug_steplery_unique_option_slug.py apps/catalog/tests/test_migration_0027_guards.py
git commit -m "feat(catalog): миграция 0027 — re-slug «Степлеры и заклёпочники» + unique (attribute, slug) (DEVIATION-2)"
```

---

### Task 5: Тесты DB-инварианта уникальности

**Files:**
- Test: `apps/catalog/tests/test_attributeoption_slug_constraint.py` (create)

**Interfaces:**
- Consumes: констрейнт из Task 4 (применён в тестовой БД миграциями).
- Produces: инвариант «дубль непустого slug в пределах атрибута невозможен на уровне БД; пустые slug по-прежнему разрешены».

- [ ] **Step 1: Написать тесты**

```python
"""DB-инвариант DEVIATION-2: (attribute, slug) уникален для непустых slug."""

import pytest
from django.db import IntegrityError, transaction

from apps.catalog.models import Attribute, AttributeOption, AttributeType


@pytest.mark.django_db
def test_duplicate_nonempty_slug_rejected():
    attr = Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )
    AttributeOption.objects.create(attribute=attr, value="A", slug="dup")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            AttributeOption.objects.create(attribute=attr, value="B", slug="dup")


@pytest.mark.django_db
def test_same_slug_allowed_across_different_attributes():
    a1 = Attribute.objects.create(slug="tool_type", name="T", attribute_type=AttributeType.SELECT)
    a2 = Attribute.objects.create(slug="material", name="M", attribute_type=AttributeType.SELECT)
    AttributeOption.objects.create(attribute=a1, value="A", slug="same")
    AttributeOption.objects.create(attribute=a2, value="B", slug="same")  # не падает


@pytest.mark.django_db
def test_blank_slug_still_allowed_multiple():
    attr = Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )
    AttributeOption.objects.create(attribute=attr, value="A", slug="")
    AttributeOption.objects.create(attribute=attr, value="B", slug="")  # не падает
```

- [ ] **Step 2: Прогнать**

Run: `./.venv/Scripts/python.exe -m pytest apps/catalog/tests/test_attributeoption_slug_constraint.py -v`
Expected: 3 PASSED

- [ ] **Step 3: Commit**

```bash
git add apps/catalog/tests/test_attributeoption_slug_constraint.py
git commit -m "test(catalog): DB-инвариант уникальности (attribute, slug) (DEVIATION-2)"
```

---

### Task 6: ADR-0012 + ledger

**Files:**
- Create: `docs/adr/ADR-0012-attributeoption-slug-uniqueness.md`
- Modify: `.superpowers/sdd/progress.md` (append)

**Interfaces:**
- Consumes: Phase 7A.1 investigation report; архитектурное решение пользователя (c+).
- Produces: зафиксированное решение для будущих фаз (Phase 7B ссылается на ADR-0012); ledger-запись, отражающая статус remediation и блокировку Phase 7B.

- [ ] **Step 1: Написать ADR по образцу ADR-0011**

Структура: статус/дата/связано (ADR-0001, ADR-0010, DEVIATION-2, Phase 7A.1) → контекст (дубль, дивергенция apply→id=16 vs facets→id=73, 10 недостижимых товаров) → варианты (b слияние / c+ re-slug / d только код) с причинами отклонения → решение: каноническая id=73, id=16 → `steplery-i-zaklepochniki`, констрейнт, fail-fast `.get()`, loader preflight → последствия и риски (SEO: смена URL фасета для 10 товаров; обратимость через reverse-миграцию).

- [ ] **Step 2: Дописать запись в ledger**

Append в `.superpowers/sdd/progress.md`:

```markdown
## Phase 7A.2 — DEVIATION-2 remediation implemented (2026-07-22)
- Phase 7A.1 investigation COMPLETE; архитектурное решение c+ утверждено пользователем (каноническая id=73, id=16 → steplery-i-zaklepochniki).
- Реализовано: seed fix + repo-тест уникальности; load_tool_types preflight (seed duplicate / DB duplicate / slug→value conflict); fail-fast .get() с option_slug_conflict в processing.py и provenance.py; миграция 0027 (guarded re-slug + partial UniqueConstraint); тесты DB-инварианта; ADR-0012.
- DEVIATION-2: REMEDIATED в коде; RESOLVED — только после post-deploy verification (инвариант-SELECT → 0 rows, facets smoke).
- Phase 7B: NOT AUTHORIZED — до post-deploy verification и отдельного решения пользователя.
```

- [ ] **Step 3: Commit (ADR + ledger одним коммитом)**

```bash
git add docs/adr/ADR-0012-attributeoption-slug-uniqueness.md .superpowers/sdd/progress.md
git commit -m "docs(adr): ADR-0012 — уникальность AttributeOption slug, DEVIATION-2 resolution"
```

---

## Verification (после merge, отдельная авторизация deploy)

1. **Backup** перед deploy: `pg_dump | gzip > backups/pre_deviation2_YYYYMMDD_HHMMSS.sql.gz` + sha256 (паттерн Phase 7A).
2. Deploy на staging (миграции применяются релиз-процессом).
3. Post-deploy read-only проверки:
   - инвариант: `SELECT attribute_id, slug, COUNT(*) FROM catalog_attributeoption WHERE slug <> '' GROUP BY 1,2 HAVING COUNT(*) > 1` → **0 rows**;
   - id=16: slug = `steplery-i-zaklepochniki`, value/sort_order неизменны; id=73 неизменна;
   - констрейнт виден: `\d catalog_attributeoption` → `uniq_attributeoption_attr_slug_nonempty`;
   - PAV = 60896, options = 328 rows, CatalogChange = 57, runs = 4 — без изменений;
   - `/healthz/` → 200.
4. Функциональный smoke (read-only): facets-резолв обоих slug — `?tool_type=steplery` → 42 товара; `?tool_type=steplery-i-zaklepochniki` → 10 товаров (проверка через shell `_option_slug_maps`/`resolve_attr_tokens`, без записи).

## Rollback

1. Код: `git revert` merge-коммита.
2. БД: `./manage.py migrate catalog 0026` — reverse снимает констрейнт и возвращает slug `steplery` записи id=16 (обратная data-миграция guarded по NEW_SLUG).
3. Данные не теряются: re-slug затрагивает только поле `slug` одной строки; PAV/attrs_cache не менялись в любую сторону.

## Риски и mitigations

| Риск | Вероятность | Mitigation |
|---|---|---|
| SEO: смена URL фасета «Степлеры и заклёпочники» (`?tool_type=steplery` → `?tool_type=steplery-i-zaklepochniki`) | неизбежно | Осознанный trade-off (утверждён в c+); старый slug теперь однозначно ведёт на id=73 (42 товара) — это корректнее прежнего last-write-wins |
| Миграция на staging упадёт guard'ом из-за drift id=16 | низкая (pre-flight 2026-07-22: состояние номинальное) | RuntimeError останавливает deploy до ручной проверки — fail-fast by design |
| Сторонний код, резолвящий `steplery` вне трёх найденных точек | низкая | grep по `apps/` в Phase 7A.1 нашёл все slug-lookup; `enrich_tool_type opt_by_slug` нормализуется сам |
| Регрессия ruleset v1 / replay-тестов | низкая | ruleset не использует `steplery` (доказано); полный сьют перед PR |
| Будущий дубль из другого seed/админки | закрыт системно | DB-констрейнт (все пути записи) + loader preflight (известный путь) + repo-тест seed |

## Non-scope

- Phase 7B (отдельная авторизация).
- Регенерация pinned taxonomy export / corpus fixture (исторические артефакты).
- `load_attributes.py:101` preflight (тот же класс риска, дублей в его seed нет; системная защита — констрейнт; отдельный follow-up при необходимости).
- Изменение `match_keywords` записей степлеров (routing-пересечение `степлер`/`скобозабив` — отдельный вопрос rules, не DEVIATION-2).
- Frontend-изменения.

## Acceptance Criteria

- Все задачи 1–6 выполнены, полный сьют зелёный (1712+ passed, известные 2 env-фейла не считаются).
- PR прошёл CI и review checkpoint, смёржен в dev (отдельная авторизация).
- Post-deploy: инвариант-SELECT → 0 rows; id=16 имеет `steplery-i-zaklepochniki`; инварианты каталога (PAV 60896 / 328 / 57 / 4) без изменений; `/healthz/` 200.
- DEVIATION-2 переводится в статус RESOLVED; Phase 7B может быть разблокирована отдельным решением.
