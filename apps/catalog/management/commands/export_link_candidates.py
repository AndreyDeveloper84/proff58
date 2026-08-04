"""Выгрузка товаров подгруппы для разбора связей («покупают вместе», аналоги).

Разбор делает человек или модель — команда лишь готовит вход: имя, бренд, цена,
характеристики. Обратный ход — ``apply_product_links``.

    python manage.py export_link_candidates --tool-type "Шлифовальные машины" \
        --out /tmp/shlif.json
    python manage.py export_link_candidates --category elektroinstrument --limit 300
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import Category, Product


class Command(BaseCommand):
    help = "Выгрузить товары подгруппы в JSON для разбора связей товар↔товар"

    def add_arguments(self, parser):
        parser.add_argument("--tool-type", dest="tool_type", help="Значение attrs_cache.tool_type")
        parser.add_argument("--category", help="Slug категории сайта")
        parser.add_argument("--out", help="Файл для записи (по умолчанию — stdout)")
        parser.add_argument("--limit", type=int, default=0, help="Ограничить число товаров")
        parser.add_argument(
            "--only-visible",
            action="store_true",
            help="Только товары, доступные покупателю (по умолчанию — все)",
        )

    def handle(self, *args, **opts):
        if not opts["tool_type"] and not opts["category"]:
            raise CommandError("Нужен --tool-type или --category")

        qs = Product.objects.all()
        if opts["tool_type"]:
            qs = qs.filter(attrs_cache__tool_type=opts["tool_type"])
        if opts["category"]:
            category = Category.objects.filter(slug=opts["category"]).first()
            if category is None:
                raise CommandError(f"Категория «{opts['category']}» не найдена")
            qs = qs.filter(category=category)
        if opts["only_visible"]:
            qs = qs.filter(is_active=True, status="published")

        qs = qs.select_related("category").order_by("name")
        if opts["limit"]:
            qs = qs[: opts["limit"]]

        products = [
            {
                "id": p.pk,
                "name": p.name,
                "brand": p.brand,
                "article": p.article,
                "price": float(p.price) if p.price is not None else None,
                "category": p.category.name if p.category else None,
                "visible": p.is_visible,
                "attrs": p.attrs_cache or {},
            }
            for p in qs
        ]

        payload = json.dumps({"products": products}, ensure_ascii=False, indent=1)
        if opts["out"]:
            with open(opts["out"], "w", encoding="utf-8") as fh:
                fh.write(payload)
            self.stdout.write(self.style.SUCCESS(f"Товаров: {len(products)} → {opts['out']}"))
        else:
            self.stdout.write(payload)
