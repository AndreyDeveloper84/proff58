"""Наполнение карточки товара контентом из JSON (описание/фото/характеристики/видео).

Идемпотентно: повторный запуск не плодит дубли фото и значений характеристик.
Контент готовится отдельно (ресёрч); фото заранее скачиваются в --images-dir.

Пример:
    python manage.py catalog_enrich_product 00015935 \
        --json var/enrich/content.json --images-dir var/enrich

Формат JSON:
    {
      "description": "...", "short_description": "...",
      "video_url": "https://www.youtube.com/watch?v=...",
      "images": ["1.jpg", "2.jpg"],
      "attributes": [
        {"slug": "load_capacity", "name": "Грузоподъёмность", "unit": "т",
         "type": "decimal", "value": "2"}
      ]
    }
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import (
    Attribute,
    AttributeType,
    Product,
    ProductAttributeValue,
    Source,
)

# Поле значения по типу характеристики. SELECT/MULTISELECT здесь не поддерживаем
# (нужны AttributeOption) — для демо достаточно text/integer/decimal/boolean.
_VALUE_FIELDS = ("value_text", "value_integer", "value_decimal", "value_boolean", "value_option")


class Command(BaseCommand):
    help = "Наполнить карточку товара контентом из JSON (описание/фото/характеристики/видео)."

    def add_arguments(self, parser):
        parser.add_argument("slug", help="slug товара (catalog.Product.slug)")
        parser.add_argument("--json", required=True, help="путь к JSON с контентом")
        parser.add_argument(
            "--images-dir", default="", help="каталог с заранее скачанными фото (для images[])"
        )

    def handle(self, *args, **opts):
        product = Product.objects.filter(slug=opts["slug"]).first()
        if product is None:
            raise CommandError(f"Товар со slug «{opts['slug']}» не найден.")

        data = json.loads(Path(opts["json"]).read_text(encoding="utf-8"))
        images_dir = Path(opts["images_dir"]) if opts["images_dir"] else None

        with transaction.atomic():
            self._set_text(product, data)
            imgs = self._add_images(product, data.get("images", []), images_dir)
            attrs = self._set_attributes(product, data.get("attributes", []))

        self.stdout.write(
            self.style.SUCCESS(f"Готово: {product.slug} — фото +{imgs}, характеристик {attrs}.")
        )

    def _set_text(self, product: Product, data: dict) -> None:
        product.description = data.get("description", product.description)
        product.short_description = data.get("short_description", product.short_description)
        product.video_url = data.get("video_url", product.video_url)
        product.save(update_fields=["description", "short_description", "video_url", "updated_at"])

    def _add_images(self, product: Product, names: list[str], images_dir: Path | None) -> int:
        if not names:
            return 0
        if images_dir is None:
            raise CommandError("В JSON есть images[], но не задан --images-dir.")
        existing = set(product.images.values_list("alt", flat=True))
        has_main = product.images.filter(is_main=True).exists()
        added = 0
        for i, name in enumerate(names):
            if name in existing:  # дедуп по alt=имя файла → идемпотентность
                continue
            path = images_dir / name
            if not path.exists():
                self.stderr.write(f"  пропуск: файл не найден — {path}")
                continue
            with path.open("rb") as fh:
                product.images.create(
                    image=File(fh, name=name),
                    alt=name,
                    is_main=(not has_main and added == 0),
                    sort_order=i,
                )
            added += 1
        return added

    def _set_attributes(self, product: Product, attrs: list[dict]) -> int:
        for a in attrs:
            slug = a.get("slug") or slugify(a.get("name", ""))
            if not slug:
                raise CommandError(f"Характеристике нужен slug или ASCII-имя: {a}")
            attr_type = a.get("type", AttributeType.TEXT)
            if attr_type not in AttributeType.values:
                raise CommandError(f"Неизвестный тип характеристики: {attr_type}")
            attribute, _ = Attribute.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": a.get("name", slug),
                    "attribute_type": attr_type,
                    "unit": a.get("unit", ""),
                },
            )
            ProductAttributeValue.objects.update_or_create(
                product=product,
                attribute=attribute,
                defaults={**self._typed_value(attr_type, a.get("value")), "source": Source.MANUAL},
            )
        return len(attrs)

    def _typed_value(self, attr_type: str, raw) -> dict:
        """Значение в нужное поле; остальные value_* сбрасываем (без устаревших)."""
        values = dict.fromkeys(_VALUE_FIELDS, None)
        values["value_text"] = ""
        if attr_type == AttributeType.INTEGER:
            values["value_integer"] = int(raw)
        elif attr_type == AttributeType.DECIMAL:
            try:
                values["value_decimal"] = Decimal(str(raw))
            except InvalidOperation as exc:
                raise CommandError(f"Не число для decimal: {raw!r}") from exc
        elif attr_type == AttributeType.BOOLEAN:
            values["value_boolean"] = bool(raw)
        else:  # text (и нераспознанное)
            values["value_text"] = str(raw)
        return values
