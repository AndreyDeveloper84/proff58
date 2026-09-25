"""Готовность товара к витрине — чек-лист «что осталось сделать».

Зачем отдельно от `Product.publication_errors()`: тот отвечает на вопрос
«можно ли публиковать» (категория + обязательные характеристики) и служит
защитой. Здесь — более широкий человеческий вопрос «чего товару не хватает,
чтобы хорошо выглядеть на сайте»: фото и описание публикацию не блокируют, но
без них карточка пустая.

Список одинаковый и в карточке товара, и в любом будущем счётчике, поэтому
живёт здесь, а не в admin.py.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    """Один пункт чек-листа: что проверяем, выполнено ли, и что делать если нет."""

    label: str
    ok: bool
    hint: str = ""
    blocks_publication: bool = False


def product_checks(product) -> list[Check]:
    """Чек-лист готовности товара. Порядок — от важного к косметике."""
    has_images = product.pk is not None and product.images.exists()
    has_main_image = product.pk is not None and product.images.filter(is_main=True).exists()
    missing_attrs = product.missing_required_attributes() if product.category_id else []
    description = (product.description or "").strip() or (product.short_description or "").strip()

    checks = [
        Check(
            "Название заполнено",
            bool((product.name or "").strip()),
            "Без названия товар не показать",
        ),
        Check(
            "Категория выбрана",
            product.category_id is not None,
            "Без категории товар не попадёт ни в один раздел каталога",
            blocks_publication=True,
        ),
        Check(
            "Цена получена из 1С",
            bool(product.price),
            "Цену присылает 1С — если её нет, проверьте номенклатуру в учётной системе",
        ),
    ]

    if missing_attrs:
        checks.append(
            Check(
                f"Обязательные характеристики: не хватает {', '.join(missing_attrs)}",
                False,
                "Заполните их в блоке «Характеристики» ниже",
                blocks_publication=True,
            )
        )
    elif product.category_id:
        checks.append(Check("Обязательные характеристики заполнены", True))

    checks.append(Check("Есть фотография", has_images, "Карточка без фото плохо продаёт"))
    if has_images:
        checks.append(
            Check(
                "Выбрано главное фото",
                has_main_image,
                "Отметьте «Главное фото» — оно показывается в списке товаров",
            )
        )
    checks.append(
        Check("Есть описание", bool(description), "Хотя бы короткое описание для карточки")
    )
    return checks


def readiness_percent(checks: list[Check]) -> int:
    """Доля выполненных пунктов, целые проценты. Пустой список — 0."""
    if not checks:
        return 0
    return round(100 * sum(1 for c in checks if c.ok) / len(checks))


def blocking_checks(checks: list[Check]) -> list[Check]:
    """Невыполненные пункты, из-за которых публикация не пройдёт."""
    return [c for c in checks if c.blocks_publication and not c.ok]
