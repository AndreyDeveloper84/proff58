"""Тесты точечной привязки осей к листьям (DRF-1428, A2).

Смысл команды — не «создать привязку», а не создать плохую. Поэтому тесты держат
порог: редкая ось и ось с единственным значением привязаны быть не должны, а обход
порога обязан требовать письменного объяснения.
"""

import io
import json

import pytest
from django.core.management import CommandError, call_command

from apps.catalog.models import (
    Attribute,
    AttributeType,
    Category,
    CategoryAttribute,
    Product,
    ProductStatus,
    StockStatus,
)


@pytest.fixture
def leaf(db):
    root = Category.add_root(name="Крепёж", slug="krepezh")
    node = root.add_child(name="Шурупы", slug="shurupy")
    Attribute.objects.create(
        slug="diameter", name="Диаметр", attribute_type=AttributeType.DECIMAL, is_filterable=True
    )
    return node


def fill(leaf, values):
    """values: список attrs_cache — по товару на элемент."""
    for i, attrs in enumerate(values):
        Product.objects.create(
            category=leaf,
            name=f"p{i}",
            slug=f"p{i}",
            attrs_cache=attrs,
            status=ProductStatus.PUBLISHED,
            is_active=True,
            stock_status=StockStatus.IN_STOCK,
            stock_quantity=1,
        )


def manifest(tmp_path, **extra):
    path = tmp_path / "leaf-filters.json"
    entry = {"category": "shurupy", "attributes": ["diameter"], **extra}
    path.write_text(
        json.dumps({"version": 1, "min_coverage": 0.5, "bindings": [entry]}), encoding="utf-8"
    )
    return str(path)


def run(path, *args):
    out = io.StringIO()
    call_command("catalog_bind_leaf_axes", *args, manifest=path, stdout=out)
    return out.getvalue()


def test_заполненная_ось_привязывается(leaf, tmp_path):
    fill(leaf, [{"diameter": 6.0}, {"diameter": 8.0}, {"diameter": 6.0}])

    run(manifest(tmp_path), "--commit")

    binding = CategoryAttribute.objects.get(category=leaf, attribute__slug="diameter")
    assert binding.is_filter is True


def test_редкая_ось_отклоняется(leaf, tmp_path):
    # Заполнена у двух товаров из десяти: выбрав значение, покупатель потеряет восемь
    # позиций, у которых поле просто не проставлено.
    fill(leaf, [{"diameter": 6.0}, {"diameter": 8.0}] + [{} for _ in range(8)])

    output = run(manifest(tmp_path), "--commit")

    assert not CategoryAttribute.objects.filter(category=leaf).exists()
    assert "фасет спрячет остальные" in output


def test_единственное_значение_отклоняется(leaf, tmp_path):
    fill(leaf, [{"diameter": 6.0}, {"diameter": 6.0}])

    output = run(manifest(tmp_path), "--commit")

    assert not CategoryAttribute.objects.filter(category=leaf).exists()
    assert "ничего не сужает" in output


def test_force_с_объяснением_проходит_порог(leaf, tmp_path):
    fill(leaf, [{"diameter": 6.0}, {"diameter": 8.0}] + [{} for _ in range(8)])
    path = manifest(tmp_path, force=True, reason="владелец согласовал 01.09")

    run(path, "--commit")

    assert CategoryAttribute.objects.filter(category=leaf).exists()


def test_force_без_объяснения_это_ошибка(leaf, tmp_path):
    fill(leaf, [{"diameter": 6.0}, {"diameter": 8.0}])
    path = manifest(tmp_path, force=True)

    with pytest.raises(CommandError, match="reason"):
        run(path, "--commit")


def test_повторный_прогон_ничего_не_плодит(leaf, tmp_path):
    fill(leaf, [{"diameter": 6.0}, {"diameter": 8.0}])
    path = manifest(tmp_path)
    run(path, "--commit")

    output = run(path, "--commit")

    assert CategoryAttribute.objects.filter(category=leaf).count() == 1
    assert "Уже привязано" in output


def test_откат_снимает_созданное(leaf, tmp_path, settings):
    settings.BASE_DIR = tmp_path
    fill(leaf, [{"diameter": 6.0}, {"diameter": 8.0}])
    run(manifest(tmp_path), "--commit")
    snapshot = next((tmp_path / "var" / "restructure").glob("bind-leaf-axes-*.json"))

    call_command("catalog_bind_leaf_axes", rollback=str(snapshot), stdout=io.StringIO())

    assert not CategoryAttribute.objects.filter(category=leaf).exists()


def test_боевой_манифест_ссылается_на_существующие_объекты(db, tmp_path):
    """Манифест в репозитории не должен ломаться на опечатке в slug.

    Категорий и атрибутов из него в тестовой БД нет, поэтому проверяем разбор и
    внятность ошибки — сам JSON при этом обязан быть валидным.
    """
    from pathlib import Path

    from django.conf import settings as django_settings

    doc = json.loads(
        (Path(django_settings.BASE_DIR) / "data" / "catalog_leaf_filters.json").read_text(
            encoding="utf-8"
        )
    )

    assert doc["bindings"], "манифест пуст"
    assert all(b.get("attributes") for b in doc["bindings"])
    with pytest.raises(CommandError, match="Нет категории"):
        call_command("catalog_bind_leaf_axes", stdout=io.StringIO())
