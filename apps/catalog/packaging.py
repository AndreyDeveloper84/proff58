"""Упаковка товара для доставки (DRF-2299): товар → ближайший раздел выше.

Публичный контракт каталога для доставки: модуль доставки не читает таблицы
каталога сам, а зовёт ``package_for(product_ids)``.

Правила:
- вес и габариты наследуются **раздельно**: у товара часто уточняют только вес, а
  коробка остаётся типовой для раздела;
- габариты — тройкой: уровень, где заданы все три, отдаёт все три;
- поиск идёт от товара к его категории и дальше вверх по дереву (путь MP_Node);
- если вес или габариты не нашлись нигде — упаковки нет (``None``), и доставка
  внешним перевозчиком считается вручную. Значений «по умолчанию» код не придумывает.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Category, Product

_STEPLEN = Category.steplen


@dataclass(frozen=True)
class Package:
    weight_g: int
    length_cm: int
    width_cm: int
    height_cm: int


def _ancestor_paths(path: str) -> list[str]:
    """Путь узла и всех предков, от ближайшего к корню."""
    return [path[:i] for i in range(len(path), 0, -_STEPLEN)]


def package_for(product_ids) -> dict[int, Package | None]:
    """Упаковка для каждого товара. Два запроса к БД на любое число товаров."""
    ids = list({int(pid) for pid in product_ids})
    if not ids:
        return {}
    products = list(
        Product.objects.filter(pk__in=ids).values(
            "pk",
            "category__path",
            "package_weight_g",
            "package_length_cm",
            "package_width_cm",
            "package_height_cm",
        )
    )
    paths = {
        ancestor
        for p in products
        if p["category__path"]
        for ancestor in _ancestor_paths(p["category__path"])
    }
    categories = {
        c["path"]: c
        for c in Category.objects.filter(path__in=paths).values(
            "path",
            "package_weight_g",
            "package_length_cm",
            "package_width_cm",
            "package_height_cm",
        )
    }

    result: dict[int, Package | None] = {pid: None for pid in ids}
    for p in products:
        levels = [p] + [
            categories[a] for a in _ancestor_paths(p["category__path"] or "") if a in categories
        ]
        weight = next((lv["package_weight_g"] for lv in levels if lv["package_weight_g"]), None)
        dims = next(
            (
                (lv["package_length_cm"], lv["package_width_cm"], lv["package_height_cm"])
                for lv in levels
                if lv["package_length_cm"] and lv["package_width_cm"] and lv["package_height_cm"]
            ),
            None,
        )
        if weight and dims:
            result[p["pk"]] = Package(weight, *dims)
    return result
