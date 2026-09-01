"""Карантин характеристик (трек P2): реестр, короткое замыкание, уборка.

Главное доказательство модуля — ``test_quarantine_never_deletes_existing_pav``.
Гейт карантина нельзя ставить в ``attribute_extract`` рядом со ``skip_if``:
prune-цикл ``enrich_attributes`` идёт ДО цикла записи и удаляет PAV по условию
«slug не входит в извлечённое», если источник ∈ ``PRUNABLE_SOURCES``. Пустой
``values`` ⇒ пустой ``current`` ⇒ все engine-PAV товара ушли бы в удаление, то
есть строка в реестре молча стёрла бы данные. Поэтому короткое замыкание стоит в
команде между вычислением ``tt_slug`` и ``rules.extract`` и пропускает разом
prune, ``no_attributes`` и запись.

Тесты работают через явный ``--quarantine`` на СВОЕЙ фикстуре: боевой реестр
(``data/attribute_quarantine.json``) отдельно проверяется на схему в
``test_production_registry_is_valid`` без обращения к БД.

Отдельный блок — corrective-доказательство по норме владельца: после того как
фразы «бакелит» и «пластмассовой ручкой 5-рядная» сняты из ``skip_if`` боевых
правил, класс названий снова извлекается (``test_*_class_gate_removed``), а
конкретные товары не получают значений уже через карантин. Без этой пары тест
зеленел бы вхолостую.
"""

from __future__ import annotations

import json
from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog import attribute_quarantine as quarantine
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    Product,
    ProductAttributeValue,
    Source,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

SHAROSHKI = "sharoshki"
KORSHCHETKI = "korshchetki"

#: Имена со стенда — те самые, ради которых раньше стояли фразы в skip_if.
NAME_18455 = "Шарошка бакелитовая 100мм М14 Р40"
NAME_18578 = "Щетка с пластмассовой ручкой 5-рядная"


# --- вспомогательное ---------------------------------------------------------


def _entry(product_id: int, **over) -> dict:
    entry = {
        "product_id": product_id,
        "reason": "owner_excluded",
        "added_at": "2026-08-14",
        "added_by": "owner",
        "status": "active",
    }
    entry.update(over)
    return entry


def _registry(tmp_path: Path, items: list, *, version: int = 1, name: str = "q.json") -> str:
    path = tmp_path / name
    payload = {"version": version, "items": items}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _run(*args) -> tuple[str, str]:
    out, err = StringIO(), StringIO()
    call_command("enrich_attributes", *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def _dry_run(*args) -> tuple[dict, str]:
    out, err = StringIO(), StringIO()
    call_command("enrich_attributes", "--dry-run", *args, stdout=out, stderr=err)
    return json.loads(out.getvalue()), err.getvalue()


def _slugs(product) -> set[str]:
    return set(
        ProductAttributeValue.objects.filter(product=product)
        .exclude(attribute__slug="tool_type")
        .values_list("attribute__slug", flat=True)
    )


@pytest.fixture
def catalog(db):
    """Категория + опции tool_type + загруженные боевые атрибуты."""
    root = Category.add_root(name="Каталог", slug="katalog", on_site=True)
    tool_type = Attribute.objects.create(
        slug="tool_type",
        name="Тип инструмента",
        attribute_type=AttributeType.SELECT,
        is_filterable=True,
    )
    options = {
        slug: AttributeOption.objects.create(attribute=tool_type, value=slug, slug=slug)
        for slug in (SHAROSHKI, KORSHCHETKI)
    }
    call_command("load_attributes")
    return {"root": root, "tool_type": tool_type, "options": options}


def _make_product(catalog, name, code, *, tool_type=KORSHCHETKI):
    product = Product.objects.create(
        category=catalog["root"],
        name=name,
        slug=code,
        code_1c=code,
        available_quantity=Decimal("5"),
        is_active=True,
    )
    ProductAttributeValue.objects.create(
        product=product,
        attribute=catalog["tool_type"],
        value_option=catalog["options"][tool_type],
        source=Source.MANUAL,
    )
    return product


def _seed_engine_number(product, slug: str, value: str) -> ProductAttributeValue:
    """Значение, записанное движком ранее (source ∈ PRUNABLE_SOURCES)."""
    pav = ProductAttributeValue.objects.create(
        product=product,
        attribute=Attribute.objects.get(slug=slug),
        value_decimal=Decimal(value),
        source=Source.REGEX,
    )
    cache = dict(product.attrs_cache or {})
    cache[slug] = float(value)
    product.attrs_cache = cache
    product.save(update_fields=["attrs_cache"])
    return pav


# --- 1. неизвестный товар — fatal -------------------------------------------


@pytest.mark.django_db
def test_unknown_product_id_is_fatal_and_writes_nothing(catalog, tmp_path):
    """Опечатка в product_id останавливает прогон, а не «просто ничего не карантинит»."""
    product = _make_product(catalog, "Щетка дисковая 100 мм латунированная", "k1")
    registry = _registry(tmp_path, [_entry(10_000_000)])

    with pytest.raises(CommandError) as exc:
        _run("--quarantine", registry)

    assert "10000000" in str(exc.value)
    assert _slugs(product) == set(), "прогон упал — в БД не должно появиться ни одного PAV"


# --- 2. ГЛАВНОЕ: карантин не удаляет существующие PAV ------------------------


@pytest.mark.django_db
def test_quarantine_never_deletes_existing_pav(catalog, tmp_path):
    """Карантинный товар сохраняет ВСЕ ранее записанные engine-значения.

    Без короткого замыкания в команде пустой ``values`` увёл бы их в prune —
    строка в реестре стёрла бы данные вместо того, чтобы их защитить.
    """
    product = _make_product(catalog, NAME_18578, "k18578")
    # diameter движок из этого названия НЕ извлекает — идеальный кандидат в prune.
    kept = _seed_engine_number(product, "diameter", "125")
    registry = _registry(tmp_path, [_entry(product.pk, attributes=None)])

    _run("--quarantine", registry)

    assert ProductAttributeValue.objects.filter(pk=kept.pk).exists()
    kept.refresh_from_db()
    assert kept.value_decimal == Decimal("125")
    assert kept.source == Source.REGEX
    product.refresh_from_db()
    assert product.attrs_cache.get("diameter") == 125.0


@pytest.mark.django_db
def test_prune_deletes_the_same_pav_without_quarantine(catalog, tmp_path):
    """Контроль: без записи в реестре тот же PAV движок удаляет.

    Пара к предыдущему тесту: доказывает, что prune действительно достаёт до
    этого значения, а сохранил его именно карантин.
    """
    product = _make_product(catalog, NAME_18578, "k18578")
    doomed = _seed_engine_number(product, "diameter", "125")

    _run("--quarantine", _registry(tmp_path, []))

    assert not ProductAttributeValue.objects.filter(pk=doomed.pk).exists()


# --- 3. карантинный товар не пишет новых значений ---------------------------


@pytest.mark.django_db
def test_quarantined_product_writes_no_values(catalog, tmp_path):
    product = _make_product(catalog, NAME_18578, "k18578")
    registry = _registry(tmp_path, [_entry(product.pk)])

    _run("--quarantine", registry)

    assert _slugs(product) == set()


@pytest.mark.django_db
def test_same_product_gets_values_without_quarantine(catalog, tmp_path):
    """Контроль к предыдущему: пустой реестр — движок пишет mount и brush_shape."""
    product = _make_product(catalog, NAME_18578, "k18578")

    _run("--quarantine", _registry(tmp_path, []))

    assert _slugs(product) == {"mount", "brush_shape"}


# --- 4. частичный скоуп ------------------------------------------------------


@pytest.mark.django_db
def test_partial_scope_blocks_only_listed_attribute(catalog, tmp_path):
    """Карантин по одной оси: она не пишется и не удаляется, остальные — как обычно."""
    product = _make_product(catalog, "Щетка дисковая 100 мм латунированная", "k2")
    shape = Attribute.objects.get(slug="brush_shape")
    stale = ProductAttributeValue.objects.create(
        product=product,
        attribute=shape,
        value_option=shape.options.get(slug="chashechnaya"),
        source=Source.KEYWORD,
    )
    registry = _registry(tmp_path, [_entry(product.pk, attributes=["brush_shape"])])

    _run("--quarantine", registry)

    stale.refresh_from_db()
    # не перезаписано (движок извлёк бы «Дисковая») и не удалено
    assert stale.value_option.slug == "chashechnaya"
    # остальные оси того же товара обработаны нормально
    assert {"diameter", "material"} <= _slugs(product)
    diameter = ProductAttributeValue.objects.get(product=product, attribute__slug="diameter")
    assert diameter.value_decimal == Decimal("100")


@pytest.mark.django_db
def test_partial_scope_counted_as_partial(catalog, tmp_path):
    product = _make_product(catalog, "Щетка дисковая 100 мм латунированная", "k2")
    registry = _registry(tmp_path, [_entry(product.pk, attributes=["brush_shape"])])

    report, _ = _dry_run("--quarantine", registry)

    assert report["totals"]["quarantined"] == 0
    assert report["totals"]["quarantined_partial"] == 1
    assert report["quarantined"][0]["scope"] == "product+attribute"
    assert report["quarantined"][0]["attributes"] == ["brush_shape"]


# --- 5. lifted и истёкший срок ----------------------------------------------


@pytest.mark.django_db
def test_lifted_entry_does_not_block(catalog, tmp_path):
    product = _make_product(catalog, NAME_18578, "k18578")
    registry = _registry(
        tmp_path,
        [
            _entry(
                product.pk,
                status="lifted",
                lifted_at="2026-08-14",
                lifted_by="owner",
                lift_note="исследование закрыто",
            )
        ],
    )

    _run("--quarantine", registry)

    assert _slugs(product) == {"mount", "brush_shape"}


@pytest.mark.django_db
def test_expired_entry_does_not_block_and_warns(catalog, tmp_path):
    product = _make_product(catalog, NAME_18578, "k18578")
    registry = _registry(tmp_path, [_entry(product.pk, expires_at="2020-01-01")])

    _, err = _run("--quarantine", registry)

    assert _slugs(product) == {"mount", "brush_shape"}
    assert "истёк" in err
    assert str(product.pk) in err


@pytest.mark.django_db
def test_future_expires_at_still_blocks(catalog, tmp_path):
    product = _make_product(catalog, NAME_18578, "k18578")
    registry = _registry(tmp_path, [_entry(product.pk, expires_at="2099-01-01")])

    _run("--quarantine", registry)

    assert _slugs(product) == set()


# --- 6. отдельный счётчик, не «без характеристик» ---------------------------


@pytest.mark.django_db
def test_quarantined_is_separate_counter_not_no_attributes(catalog, tmp_path):
    product = _make_product(catalog, NAME_18455, "s18455", tool_type=SHAROSHKI)
    registry = _registry(tmp_path, [_entry(product.pk, ticket="ХАР-13")])

    report, _ = _dry_run("--quarantine", registry)

    assert report["totals"]["processed"] == 1
    assert report["totals"]["quarantined"] == 1
    assert report["totals"]["no_attributes"] == 0
    assert report["totals"]["by_action"] == {}
    row = report["quarantined"][0]
    assert row["product_id"] == product.pk
    assert row["scope"] == "product"
    assert row["tool_type"] == SHAROSHKI
    assert row["ticket"] == "ХАР-13"
    assert "diameter" in row["managed_attributes"]
    assert report["quarantine"]["active"] == 1
    assert report["quarantine"]["in_scope"] == 1


@pytest.mark.django_db
def test_without_quarantine_same_product_is_no_attributes(catalog, tmp_path):
    """Контроль: без карантина тот же товар попадает именно в «без характеристик»."""
    _make_product(catalog, NAME_18455, "s18455", tool_type=SHAROSHKI)

    report, _ = _dry_run("--quarantine", _registry(tmp_path, []))

    assert report["totals"]["quarantined"] == 0
    assert report["totals"]["no_attributes"] == 1


@pytest.mark.django_db
def test_preserved_pav_listed_in_report(catalog, tmp_path):
    product = _make_product(catalog, NAME_18578, "k18578")
    _seed_engine_number(product, "diameter", "125")
    registry = _registry(tmp_path, [_entry(product.pk)])

    report, _ = _dry_run("--quarantine", registry)

    preserved = report["quarantined"][0]["preserved_pav"]
    assert [p["attribute"] for p in preserved] == ["diameter"]
    assert preserved[0]["source"] == Source.REGEX


@pytest.mark.django_db
def test_import_run_stats_carry_quarantine(catalog, tmp_path):
    from apps.catalog.models import ImportRun

    product = _make_product(catalog, NAME_18578, "k18578")
    registry = _registry(tmp_path, [_entry(product.pk)])

    _run("--quarantine", registry)

    stats = ImportRun.objects.latest("started_at").stats
    assert stats["quarantined"] == 1
    assert stats["quarantine"]["active"] == 1
    assert stats["quarantine"]["version"] == 1
    assert stats["quarantine"]["product_ids"] == [product.pk]


# --- 7. строгая валидация — каждый случай отдельным падением ----------------


@pytest.mark.django_db
def test_unknown_field_is_fatal(catalog, tmp_path):
    product = _make_product(catalog, NAME_18578, "k18578")
    registry = _registry(tmp_path, [_entry(product.pk, atributes=["diameter"])])

    with pytest.raises(CommandError, match="atributes"):
        _run("--quarantine", registry)


@pytest.mark.django_db
def test_duplicate_active_product_is_fatal(catalog, tmp_path):
    product = _make_product(catalog, NAME_18578, "k18578")
    registry = _registry(tmp_path, [_entry(product.pk), _entry(product.pk)])

    with pytest.raises(CommandError, match="дважды"):
        _run("--quarantine", registry)


@pytest.mark.django_db
def test_rule_defect_without_ticket_is_fatal(catalog, tmp_path):
    product = _make_product(catalog, NAME_18578, "k18578")
    registry = _registry(tmp_path, [_entry(product.pk, reason="rule_defect")])

    with pytest.raises(CommandError, match="ticket"):
        _run("--quarantine", registry)


@pytest.mark.django_db
def test_rule_defect_with_ticket_is_accepted(catalog, tmp_path):
    product = _make_product(catalog, NAME_18578, "k18578")
    registry = _registry(tmp_path, [_entry(product.pk, reason="rule_defect", ticket="ХАР-13")])

    _run("--quarantine", registry)

    assert _slugs(product) == set()


@pytest.mark.django_db
def test_attribute_outside_managed_slugs_is_fatal(catalog, tmp_path):
    product = _make_product(catalog, NAME_18578, "k18578")
    registry = _registry(tmp_path, [_entry(product.pk, attributes=["no-such-attribute"])])

    with pytest.raises(CommandError, match="no-such-attribute"):
        _run("--quarantine", registry)


@pytest.mark.django_db
def test_lifted_without_lifted_at_is_fatal(catalog, tmp_path):
    product = _make_product(catalog, NAME_18578, "k18578")
    registry = _registry(tmp_path, [_entry(product.pk, status="lifted", lifted_by="owner")])

    with pytest.raises(CommandError, match="lifted_at"):
        _run("--quarantine", registry)


@pytest.mark.django_db
def test_bad_reason_status_version_and_date_are_fatal(catalog, tmp_path):
    product = _make_product(catalog, NAME_18578, "k18578")

    with pytest.raises(CommandError, match="reason"):
        _run("--quarantine", _registry(tmp_path, [_entry(product.pk, reason="потому что")]))
    with pytest.raises(CommandError, match="status"):
        _run("--quarantine", _registry(tmp_path, [_entry(product.pk, status="paused")]))
    with pytest.raises(CommandError, match="версия"):
        _run("--quarantine", _registry(tmp_path, [_entry(product.pk)], version=2))
    with pytest.raises(CommandError, match="added_at"):
        _run("--quarantine", _registry(tmp_path, [_entry(product.pk, added_at="14.08.2026")]))
    with pytest.raises(CommandError, match="attributes"):
        _run("--quarantine", _registry(tmp_path, [_entry(product.pk, attributes=[])]))


@pytest.mark.django_db
def test_missing_registry_file_is_empty_not_error(catalog, tmp_path):
    product = _make_product(catalog, NAME_18578, "k18578")

    _, err = _run("--quarantine", str(tmp_path / "нет-такого.json"))

    assert "файла нет" in err
    assert _slugs(product) == {"mount", "brush_shape"}


# --- 8. боевой реестр ---------------------------------------------------------


def test_production_registry_is_valid():
    """Боевой data/attribute_quarantine.json обязан проходить ту же валидацию."""
    rules = json.loads((DATA_DIR / "attribute_rules.json").read_text(encoding="utf-8"))
    managed = {a["slug"] for tt in rules["tool_types"] for a in tt["attributes"]}
    path = DATA_DIR / quarantine.FILENAME

    registry = quarantine.load_registry(path, managed_slugs=managed)

    assert registry.exists
    assert registry.version == quarantine.VERSION
    assert {e.product_id for e in registry.active} == {18455, 18578}
    for entry in registry.entries:
        assert entry.reason in quarantine.REASONS
        assert entry.status in quarantine.STATUSES
        assert entry.added_by


def test_production_rules_no_longer_carry_the_phrases():
    """Фразы конкретных товаров сняты из боевых правил (иначе карантин вхолостую)."""
    raw = (DATA_DIR / "attribute_rules.json").read_text(encoding="utf-8")
    rules = json.loads(raw)
    for tt in rules["tool_types"]:
        for attr in tt["attributes"]:
            assert "пластмассовой ручкой 5-рядная" not in attr.get("skip_if", [])
            if tt["tool_type"] == SHAROSHKI:
                assert "бакелит" not in attr.get("skip_if", [])
    sharoshki = next(t for t in rules["tool_types"] if t["tool_type"] == SHAROSHKI)
    diameter = next(a for a in sharoshki["attributes"] if a["slug"] == "diameter")
    # классовые гейты набора трогать было нельзя
    assert diameter["skip_if"] == ["набор", "предм"]


# --- corrective-доказательство: гейт снят, класс снова извлекается -----------


@pytest.mark.django_db
def test_korshchetki_class_gate_removed(catalog, tmp_path):
    """Название с той же фразой у ДРУГОГО товара больше не гасится.

    Раньше фраза стояла в skip_if всех пяти правил блока — то есть глушила класс
    названий ради одного товара.
    """
    other = _make_product(catalog, "Щетка ручная с пластмассовой ручкой 5-рядная нейлон", "k3")

    _run("--quarantine", _registry(tmp_path, []))

    assert {"mount", "brush_shape", "material"} <= _slugs(other)


@pytest.mark.django_db
def test_sharoshki_class_gate_removed(catalog, tmp_path):
    """«бакелит» больше не глушит блок sharoshki: соседний товар получает значения."""
    other = _make_product(
        catalog, "Шарошка бакелитовая алмазная 16х14 мм", "s2", tool_type=SHAROSHKI
    )

    _run("--quarantine", _registry(tmp_path, []))

    assert {"diameter", "material"} <= _slugs(other)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("name", "code", "tool_type"),
    [(NAME_18455, "s18455", SHAROSHKI), (NAME_18578, "k18578", KORSHCHETKI)],
)
def test_quarantine_replaces_removed_skip_if(catalog, tmp_path, name, code, tool_type):
    """После снятия фразы товар всё ещё без новых значений — и старые целы."""
    product = _make_product(catalog, name, code, tool_type=tool_type)
    kept = _seed_engine_number(product, "diameter", "125")
    registry = _registry(tmp_path, [_entry(product.pk, ticket="ХАР-13")])

    _run("--quarantine", registry)

    assert _slugs(product) == {"diameter"}  # только ранее записанное
    kept.refresh_from_db()
    assert kept.value_decimal == Decimal("125")


# --- 9. команда уборки --------------------------------------------------------


@pytest.fixture
def dirty(catalog, tmp_path):
    """Карантинный товар с engine-значением и ручным значением + реестр."""
    product = _make_product(catalog, NAME_18578, "k18578")
    engine = _seed_engine_number(product, "diameter", "125")
    material = Attribute.objects.get(slug="material")
    manual = ProductAttributeValue.objects.create(
        product=product,
        attribute=material,
        value_option=material.options.get(slug="nylon"),
        source=Source.MANUAL,
    )
    cache = dict(product.attrs_cache or {})
    cache["material"] = "Нейлон"
    product.attrs_cache = cache
    product.save(update_fields=["attrs_cache"])
    registry = _registry(tmp_path, [_entry(product.pk)])
    return {"product": product, "engine": engine, "manual": manual, "registry": registry}


def _cleanup(*args) -> str:
    out, err = StringIO(), StringIO()
    call_command("catalog_attribute_cleanup_quarantine", *args, stdout=out, stderr=err)
    return out.getvalue()


@pytest.mark.django_db
def test_cleanup_dry_run_deletes_nothing_and_writes_snapshot(dirty, tmp_path):
    snapshot = tmp_path / "snapshot.json"

    output = _cleanup("--quarantine", dirty["registry"], "--snapshot", str(snapshot))

    assert "dry-run" in output
    assert ProductAttributeValue.objects.filter(pk=dirty["engine"].pk).exists()
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    assert payload["mode"] == "dry-run"
    assert payload["totals"]["values"] == 1
    item = payload["items"][0]
    # ключ восстановления — product_id + attribute, а не pav_id
    assert item["product_id"] == dirty["product"].pk
    assert item["attribute"] == "diameter"
    assert item["source"] == Source.REGEX


@pytest.mark.django_db
def test_cleanup_apply_requires_snapshot(dirty):
    with pytest.raises(CommandError, match="snapshot"):
        _cleanup("--quarantine", dirty["registry"], "--apply")


@pytest.mark.django_db
def test_cleanup_apply_deletes_exactly_engine_values(dirty, tmp_path):
    snapshot = tmp_path / "snapshot.json"

    output = _cleanup("--quarantine", dirty["registry"], "--snapshot", str(snapshot), "--apply")

    assert "post-audit: остатков нет" in output
    assert not ProductAttributeValue.objects.filter(pk=dirty["engine"].pk).exists()
    # ручное значение карантин не трогает
    assert ProductAttributeValue.objects.filter(pk=dirty["manual"].pk).exists()
    product = dirty["product"]
    product.refresh_from_db()
    assert "diameter" not in (product.attrs_cache or {})
    assert product.attrs_cache.get("material") == "Нейлон"
    assert json.loads(snapshot.read_text(encoding="utf-8"))["mode"] == "apply"


@pytest.mark.django_db
def test_cleanup_second_run_is_noop(dirty, tmp_path):
    snapshot = tmp_path / "snapshot.json"
    _cleanup("--quarantine", dirty["registry"], "--snapshot", str(snapshot), "--apply")

    output = _cleanup("--quarantine", dirty["registry"], "--snapshot", str(snapshot), "--apply")

    assert "no-op" in output
    assert ProductAttributeValue.objects.filter(pk=dirty["manual"].pk).exists()


@pytest.mark.django_db
def test_cleanup_ignores_lifted_entry(catalog, tmp_path):
    product = _make_product(catalog, NAME_18578, "k18578")
    engine = _seed_engine_number(product, "diameter", "125")
    registry = _registry(
        tmp_path,
        [_entry(product.pk, status="lifted", lifted_at="2026-08-14", lifted_by="owner")],
    )

    output = _cleanup("--quarantine", registry)

    assert "убирать нечего" in output
    assert ProductAttributeValue.objects.filter(pk=engine.pk).exists()
