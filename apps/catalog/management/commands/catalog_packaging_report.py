"""Отчёт по упаковке для доставки СДЭК (DRF-2299), только чтение.

    manage.py catalog_packaging_report            # разделы и покрытие опубликованных товаров
    manage.py catalog_packaging_report --missing  # только разделы, где у товаров нет упаковки

Показывает по разделам верхнего уровня: сколько опубликованных товаров, у скольких
упаковка определяется (своя или унаследованная), и что задано у самого раздела.
Нужен, чтобы заполнить типовые коробки один раз и видеть, где ещё пусто.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.catalog.models import Category, Product, ProductStatus
from apps.catalog.packaging import package_for


class Command(BaseCommand):
    help = "Покрытие опубликованных товаров упаковкой для доставки СДЭК по разделам."

    def add_arguments(self, parser):
        parser.add_argument("--missing", action="store_true", help="Только разделы с пробелами")

    def handle(self, *args, **options):
        published = list(
            Product.objects.filter(status=ProductStatus.PUBLISHED, is_active=True).values_list(
                "pk", "category__path"
            )
        )
        packages = package_for(pk for pk, _ in published)
        steplen = Category.steplen
        roots = {c.path: c for c in Category.objects.filter(depth=1).order_by("sort_order", "name")}
        stats: dict[str, list[int]] = {path: [0, 0] for path in roots}
        without_category = [0, 0]
        for pk, path in published:
            bucket = stats.get((path or "")[:steplen], without_category)
            bucket[0] += 1
            bucket[1] += packages.get(pk) is not None

        total = sum(v[0] for v in stats.values()) + without_category[0]
        covered = sum(v[1] for v in stats.values()) + without_category[1]
        self.stdout.write(f"Опубликовано товаров: {total}, с упаковкой: {covered}")
        self.stdout.write("")
        for path, category in roots.items():
            count, ok = stats[path]
            if options["missing"] and ok == count:
                continue
            own = []
            if category.package_weight_g:
                own.append(f"{category.package_weight_g} г")
            dims = (
                category.package_length_cm,
                category.package_width_cm,
                category.package_height_cm,
            )
            if all(dims):
                own.append("×".join(map(str, dims)) + " см")
            self.stdout.write(
                f"{category.name} (id {category.pk}): {ok}/{count} товаров; "
                f"у раздела: {', '.join(own) or 'не задано'}"
            )
        if without_category[0]:
            self.stdout.write(f"Без категории: {without_category[1]}/{without_category[0]}")
