"""Тесты команды catalog_taxonomy_apply (перестройка раздела «Электроинструмент»).

Покрывают гарантии:
  * dry-run (по умолчанию) НИЧЕГО не меняет, но печатает объёмы переноса;
  * --commit переносит товары в раздел, ставит category_is_manual=True, скрывает
    опустевшие узлы (on_site=False), пишет снимок отката;
  * --rollback восстанавливает категории/видимость по снимку.

Нужен PostgreSQL (как и остальной каталог). EAV-значения создаём реальными
ProductAttributeValue — команда считает питание по EAV, а не по attrs_cache.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    Product,
    ProductAttributeValue,
    ProductStatus,
)


@pytest.fixture
def section():
    """Дерево и товары под slug'и из SECTIONS['electroinstrument']."""
    root = Category.add_root(name="Электроинструмент", slug="elektroinstrument")
    setevoy = root.add_child(name="Сетевой инструмент", slug="setevoy-instrument")
    akkum = root.add_child(name="Аккумуляторный инструмент", slug="akkumulyatornyy-instrument")
    root.add_child(
        name="Аккумуляторы и зарядные устройства",
        slug="akkumulyatory-i-zaryadnye-ustroystva",
    )

    power = Attribute.objects.create(
        slug="power_source", name="Питание", attribute_type=AttributeType.SELECT
    )
    o_mains = AttributeOption.objects.create(attribute=power, value="Сеть", slug="mains")
    o_batt = AttributeOption.objects.create(attribute=power, value="Аккумулятор", slug="battery")
    tool_type = Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )
    o_perf = AttributeOption.objects.create(
        attribute=tool_type, value="Перфораторы", slug="perforatory"
    )

    def mk(cat, slug, *, power_opt=None):
        p = Product.objects.create(
            category=cat, name=slug, slug=slug, status=ProductStatus.PUBLISHED, is_active=True
        )
        ProductAttributeValue.objects.create(product=p, attribute=tool_type, value_option=o_perf)
        if power_opt is not None:
            ProductAttributeValue.objects.create(product=p, attribute=power, value_option=power_opt)
        return p

    # Сетевой: 2 (один с питанием, один без); Аккумуляторный: 1 (с питанием).
    p_set1 = mk(setevoy, "set-1", power_opt=o_mains)
    p_set2 = mk(setevoy, "set-2", power_opt=None)
    p_akk1 = mk(akkum, "akk-1", power_opt=o_batt)
    return {
        "root": root,
        "setevoy": setevoy,
        "akkum": akkum,
        "products": [p_set1, p_set2, p_akk1],
    }


@pytest.mark.django_db
def test_dry_run_changes_nothing(section):
    out = StringIO()
    call_command("catalog_taxonomy_apply", "--section", "electroinstrument", stdout=out)
    text = out.getvalue()

    # Отчёт посчитал объёмы: к переносу 3, без питания после переноса 1 (set-2).
    assert "ИТОГО к переносу: 3" in text
    assert "ОСТАНУТСЯ без питания после переноса: 1" in text
    # Разбивка по tool_type: все 3 — настоящий инструмент (perforatory).
    assert "настоящий инструмент 3" in text
    assert "DRY-RUN" in text

    # Ничего не изменилось.
    for p in section["products"]:
        p.refresh_from_db()
    assert section["products"][0].category_id == section["setevoy"].pk
    assert section["products"][2].category_id == section["akkum"].pk
    assert all(p.category_is_manual is False for p in section["products"])
    section["setevoy"].refresh_from_db()
    assert section["setevoy"].on_site is True


@pytest.mark.django_db
def test_commit_moves_and_hides_then_rollback(section):
    root, setevoy, akkum = section["root"], section["setevoy"], section["akkum"]

    out = StringIO()
    call_command("catalog_taxonomy_apply", "--section", "electroinstrument", "--commit", stdout=out)
    assert "COMMIT:" in out.getvalue()

    # Все 3 товара в разделе, помечены вручную.
    for p in section["products"]:
        p.refresh_from_db()
        assert p.category_id == root.pk
        assert p.category_is_manual is True
    # Опустевшие узлы скрыты.
    setevoy.refresh_from_db()
    akkum.refresh_from_db()
    assert setevoy.on_site is False and akkum.on_site is False

    # Снимок отката создан.
    backup_dir = Path(settings.BASE_DIR) / "var" / "restructure"
    snaps = sorted(backup_dir.glob("electroinstrument-*.json"))
    assert snaps, "снимок отката не создан"

    # Откат восстанавливает категории и видимость.
    call_command("catalog_taxonomy_apply", "--rollback", str(snaps[-1]), stdout=StringIO())
    for p in section["products"]:
        p.refresh_from_db()
    assert section["products"][0].category_id == setevoy.pk
    assert section["products"][2].category_id == akkum.pk
    assert all(p.category_is_manual is False for p in section["products"])
    setevoy.refresh_from_db()
    assert setevoy.on_site is True


@pytest.mark.django_db
def test_missing_category_raises(section):
    # Снести один из ожидаемых slug → команда падает понятной ошибкой, не молча.
    section["setevoy"].slug = "moved-away"
    section["setevoy"].name = "Другое"
    section["setevoy"].save(update_fields=["slug", "name"])
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("catalog_taxonomy_apply", "--section", "electroinstrument", stdout=StringIO())


@pytest.mark.django_db
def test_dry_run_tool_type_breakdown(section):
    # Добавляем в «Сетевой» комплектующее (tool_type=akkumulyatory) и «не-инструмент»
    # (без tool_type) — проверяем три корзины разбивки.
    setevoy = section["setevoy"]
    tt = Attribute.objects.get(slug="tool_type")
    o_akb = AttributeOption.objects.create(attribute=tt, value="Аккумуляторы", slug="akkumulyatory")

    p_compl = Product.objects.create(
        category=setevoy, name="АКБ 18В", slug="akb-1", status=ProductStatus.PUBLISHED
    )
    ProductAttributeValue.objects.create(product=p_compl, attribute=tt, value_option=o_akb)
    # «Антенна» — без tool_type вовсе (кандидат на разбор отдельным шагом).
    Product.objects.create(
        category=setevoy, name="Антенна авто", slug="antenna-1", status=ProductStatus.PUBLISHED
    )

    out = StringIO()
    call_command("catalog_taxonomy_apply", "--section", "electroinstrument", stdout=out)
    text = out.getvalue()

    # 3 perforatory (инструмент) + 1 akkumulyatory (комплектующее) + 1 без типа.
    assert "настоящий инструмент 3" in text
    assert "комплектующие (→ подкатегория) 1" in text
    assert "без типа / не-инструмент 1" in text
    assert "Антенна авто" in text  # показан в примерах «без типа»
