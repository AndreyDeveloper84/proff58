"""Загрузка словаря ``tool_type`` из canonical taxonomy manifest (Wave 7.1/H1).

``tool_type`` — это АТРИБУТ (вторая ось навигации / SEO-фасет), а не категория.
Раньше ``AttributeOption`` материализовались из ``data/tool_type_rules.json``;
теперь единственный источник operational taxonomy — canonical manifest
(``data/catalog_processing_rules/tool_type_taxonomy.v1.json``).
``tool_type_rules.json`` остаётся источником legacy extraction rules и
используется здесь ТОЛЬКО для привязки ``CategoryAttribute`` (его semantics
не меняется).

Seed-политика (H1 §6):

- создаёт отсутствующие manifest options (ключ — slug);
- идемпотентен: повторный запуск — no-op;
- ничего не удаляет и не переслагивает существующие options;
- fail-closed при несовместимом slug/value mapping (включая значение manifest,
  уже существующее в БД под другим slug, — вне ``semantic_duplicate_allowlist``);
- ``sort_order`` существующих options обновляется только с ``--update-display``,
  иначе расхождение display metadata только сообщается;
- структурированный отчёт created/present/display_updated/display_mismatch.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.ingest import data_dir
from apps.catalog.models import (
    Attribute,
    AttributeOption,
    AttributeType,
    Category,
    CategoryAttribute,
)
from apps.catalog.taxonomy_manifest import load_manifest
from apps.catalog.tool_type import ToolTypeRules

TOOL_TYPE_SLUG = "tool_type"
TOOL_TYPE_NAME = "Тип инструмента"


class Command(BaseCommand):
    help = "Создать Attribute(tool_type) и его варианты из canonical taxonomy manifest."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default=None,
            help="Каталог с tool_type_rules.json (только для привязки CategoryAttribute)",
        )
        parser.add_argument(
            "--manifest",
            default=None,
            help="Путь к taxonomy manifest (default: canonical tool_type_taxonomy.v1.json)",
        )
        parser.add_argument(
            "--update-display",
            action="store_true",
            help="Обновлять sort_order существующих options по manifest (иначе только отчёт)",
        )

    def handle(self, *args, **options):
        try:
            manifest = load_manifest(options["manifest"])
        except (ValueError, FileNotFoundError) as exc:
            raise CommandError(str(exc)) from exc

        with transaction.atomic():
            attribute, _ = Attribute.objects.get_or_create(
                slug=TOOL_TYPE_SLUG,
                defaults=dict(
                    name=TOOL_TYPE_NAME,
                    attribute_type=AttributeType.SELECT,
                    is_filterable=True,
                    is_comparable=False,
                ),
            )

            created = 0
            present = 0
            display_updated = 0
            display_mismatch: list[str] = []
            # Значение manifest, уже существующее в БД под другим slug, — это
            # несовместимый mapping: создание дубликата value запрещено
            # (кроме explicit allow-list manifest).
            db_slug_by_value = {
                opt.value: opt.slug for opt in AttributeOption.objects.filter(attribute=attribute)
            }
            allow = manifest.allow_pairs

            for mopt in manifest.options:
                opt = AttributeOption.objects.filter(attribute=attribute, slug=mopt.slug).first()
                if opt is None:
                    existing_slug = db_slug_by_value.get(mopt.value)
                    if existing_slug is not None and {existing_slug, mopt.slug} not in allow:
                        raise CommandError(
                            f"incompatible slug/value mapping: value {mopt.value!r} уже есть в БД "
                            f"под slug {existing_slug!r}, manifest предлагает {mopt.slug!r}"
                        )
                    AttributeOption.objects.create(
                        attribute=attribute,
                        slug=mopt.slug,
                        value=mopt.value,
                        sort_order=mopt.sort_order,
                    )
                    db_slug_by_value[mopt.value] = mopt.slug
                    created += 1
                elif opt.value != mopt.value:
                    raise CommandError(
                        f"option slug conflicts with DB: {mopt.slug}: "
                        f"db={opt.value!r} vs manifest={mopt.value!r}"
                    )
                else:
                    present += 1
                    if opt.sort_order != mopt.sort_order:
                        if options["update_display"]:
                            opt.sort_order = mopt.sort_order
                            opt.save(update_fields=["sort_order"])
                            display_updated += 1
                        else:
                            display_mismatch.append(mopt.slug)

            base = options["path"] or data_dir()
            rules = ToolTypeRules.from_file(f"{base}/tool_type_rules.json")
            for cat in rules.categories:
                self._bind_category(attribute, cat.category)

        self.stdout.write(
            self.style.SUCCESS(
                f"Атрибут tool_type готов (manifest v{manifest.manifest_version}, "
                f"{len(manifest.options)} options). created={created}, present={present}, "
                f"display_updated={display_updated}, display_mismatch={len(display_mismatch)}."
            )
        )
        if display_mismatch:
            self.stdout.write(
                self.style.WARNING(
                    "sort_order расходится с manifest (для синхронизации — --update-display): "
                    + ", ".join(display_mismatch[:20])
                )
            )
        return str(created)

    def _bind_category(self, attribute: Attribute, category_name: str) -> None:
        """Привязать tool_type к категории верхнего уровня (если она есть в дереве)."""
        top = Category.objects.filter(depth=1, name=category_name).first()
        if top is None:
            self.stdout.write(
                self.style.WARNING(
                    f"  категория верхнего уровня «{category_name}» не найдена — "
                    f"сначала выполните build_categories."
                )
            )
            return
        CategoryAttribute.objects.update_or_create(
            category=top,
            attribute=attribute,
            defaults=dict(is_filter=True, is_seo_facet=True),
        )
