"""Заполнение ``AttributeOption.slug`` для SELECT-характеристик (P2, slug-URL).

Для каждого фильтруемого SELECT-атрибута собирает distinct-значения из ``attrs_cache``
ВИДИМЫХ товаров (тот же набор, что и каталог/фасеты — ``visible_products()``), при
необходимости создаёт недостающие ``AttributeOption`` и заполняет ТОЛЬКО пустые ``slug``
(транслит кириллицы → латиница). Идемпотентна: непустые slug не перезаписываются.

Уникальность slug гарантируется В ПРЕДЕЛАХ атрибута (суффикс ``-2/-3`` при коллизии).
Пустые значения (None/""/пробелы) пропускаются — мусорные опции не создаются.

Порядок выката на staging (строго):
    backfill_option_slugs --attribute tool_type --dry-run
    backfill_option_slugs --attribute tool_type
    backfill_option_slugs --dry-run
    backfill_option_slugs
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models.fields.json import KeyTextTransform

from apps.catalog.filters import visible_products
from apps.catalog.management.commands.load_tool_types import TOOL_TYPE_SLUG
from apps.catalog.models import Attribute, AttributeOption, AttributeType
from apps.catalog.taxonomy_manifest import load_options_index
from apps.catalog.translit import slugify_value


class Command(BaseCommand):
    help = "Заполнить пустые AttributeOption.slug для SELECT-характеристик (P2, slug-URL)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Только отчёт, без записи в БД.")
        parser.add_argument(
            "--attribute", default=None, help="Slug одного атрибута (по умолчанию — все SELECT)."
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        only = options["attribute"]

        attrs = Attribute.objects.filter(attribute_type=AttributeType.SELECT, is_filterable=True)
        if only:
            attrs = attrs.filter(slug=only)
        attrs = list(attrs.order_by("slug"))

        # Wave 7.1/H1: для tool_type новые options не создаются — materialization
        # только через canonical taxonomy manifest + seed (load_tool_types).
        manifest_options = None
        if any(a.slug == TOOL_TYPE_SLUG for a in attrs):
            manifest_options = load_options_index()

        totals = {
            "scanned": 0,
            "created": 0,
            "filled": 0,
            "collisions": 0,
            "already": 0,
            "skipped_empty": 0,
            "missing_in_db": 0,
            "outside_manifest": 0,
        }

        with transaction.atomic():
            for attr in attrs:
                totals["scanned"] += 1
                self._process_attribute(attr, dry_run, totals, manifest_options)
            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                "{tag}Attributes scanned: {scanned} | Options created: {created} | "
                "Slugs filled: {filled} | Collisions resolved: {collisions} | "
                "Options already had slug: {already} | Skipped empty values: {skipped_empty} | "
                "Manifest options missing in DB (run seed): {missing_in_db} | "
                "Values outside manifest (not created): {outside_manifest}".format(
                    tag="[dry-run] " if dry_run else "", **totals
                )
            )
        )
        return str(totals["filled"])

    def _process_attribute(
        self, attr: Attribute, dry_run: bool, totals: dict, manifest_options=None
    ) -> None:
        # Существующие опции атрибута: карта value→option + множество занятых slug (все непустые).
        options = {o.value: o for o in attr.options.all()}
        used_slugs = {o.slug for o in options.values() if o.slug}

        values = (
            visible_products()
            .annotate(_fv=KeyTextTransform(attr.slug, "attrs_cache"))
            .filter(_fv__isnull=False)
            .values_list("_fv", flat=True)
            .distinct()
        )

        for value in values:
            if value is None or not str(value).strip():
                totals["skipped_empty"] += 1
                continue

            option = options.get(value)
            if option is None:
                if attr.slug == TOOL_TYPE_SLUG:
                    # Wave 7.1/H1 guard: tool_type options не создаются в runtime.
                    # Manifest-значение, отсутствующее в БД, — задача seed;
                    # значение вне manifest — игнорируется (отчёт), не создаётся.
                    if manifest_options is not None and manifest_options.by_normalized_value(value):
                        totals["missing_in_db"] += 1
                    else:
                        totals["outside_manifest"] += 1
                    continue
                totals["created"] += 1
                option = AttributeOption(attribute=attr, value=value)
                options[value] = option
                if not dry_run:
                    option.save()

            if option.slug:
                totals["already"] += 1
                continue

            slug = self._unique_slug(value, used_slugs, totals)
            used_slugs.add(slug)
            option.slug = slug
            totals["filled"] += 1
            if not dry_run:
                option.save(update_fields=["slug"])

    @staticmethod
    def _unique_slug(value: str, used_slugs: set, totals: dict) -> str:
        base = slugify_value(value) or "option"
        slug = base
        i = 2
        if slug in used_slugs:
            totals["collisions"] += 1
        while slug in used_slugs:
            slug = f"{base}-{i}"
            i += 1
        return slug
