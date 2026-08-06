"""Загрузка словаря ``tool_type`` из canonical taxonomy manifest (Wave 7.1/H1).

``tool_type`` — это АТРИБУТ (вторая ось навигации / SEO-фасет), а не категория.
Раньше ``AttributeOption`` материализовались из ``data/tool_type_rules.json``;
теперь единственный источник operational taxonomy — canonical manifest
(``data/catalog_processing_rules/tool_type_taxonomy.v1.json``).
``tool_type_rules.json`` остаётся источником legacy extraction rules и
используется здесь ТОЛЬКО для привязки ``CategoryAttribute`` (его semantics
не меняется).

Seed-политика (H1 §6) + КОД-05:

- создаёт отсутствующие manifest options (ключ — slug);
- идемпотентен: повторный запуск — no-op;
- ничего не удаляет и не переслагивает существующие options;
- fail-closed при несовместимом slug/value mapping (включая значение manifest,
  уже существующее в БД под другим slug, — вне ``semantic_duplicate_allowlist``);
- ``sort_order`` существующих options обновляется только с ``--update-display``,
  иначе расхождение display metadata только сообщается;
- переименование display value (slug не меняется) применяется только с
  ``--apply-renames``; без флага сохраняется прежний CommandError;
- ``--dry-run`` показывает план (created/present/renamed/display_updated) и
  откатывает транзакцию, не оставляя изменений в БД;
- структурированный отчёт created/present/renamed/display_updated/display_mismatch.
"""

from __future__ import annotations

from collections import Counter

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
from apps.catalog.taxonomy_manifest import ManifestOption, load_manifest
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
        parser.add_argument(
            "--apply-renames",
            action="store_true",
            help="Переименовывать display value при совпадении slug",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Не вносить изменения в БД, только показать план",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            manifest = load_manifest(options["manifest"])
        except (ValueError, FileNotFoundError) as exc:
            raise CommandError(str(exc)) from exc

        apply_renames = options["apply_renames"]
        dry_run = options["dry_run"]
        update_display = options["update_display"]

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
        renamed = 0
        renamed_details: list[str] = []

        # Значение manifest, уже существующее в БД под другим slug, — это
        # несовместимый mapping: создание дубликата value запрещено
        # (кроме explicit allow-list manifest).
        db_options = {opt.slug: opt for opt in AttributeOption.objects.filter(attribute=attribute)}
        db_slug_by_value = {opt.value: opt.slug for opt in db_options.values()}
        allow = manifest.allow_pairs

        # Переименования откладываем: их target value может временно занимать
        # другая опция, которая тоже переименовывается в этом же манифесте.
        renames: list[tuple[AttributeOption, ManifestOption]] = []

        for mopt in manifest.options:
            opt = db_options.get(mopt.slug)
            if opt is None:
                existing_slug = db_slug_by_value.get(mopt.value)
                if existing_slug is not None and {existing_slug, mopt.slug} not in allow:
                    raise CommandError(
                        f"incompatible slug/value mapping: value {mopt.value!r} уже есть в БД "
                        f"под slug {existing_slug!r}, manifest предлагает {mopt.slug!r}"
                    )
                new_opt = AttributeOption.objects.create(
                    attribute=attribute,
                    slug=mopt.slug,
                    value=mopt.value,
                    sort_order=mopt.sort_order,
                )
                db_options[mopt.slug] = new_opt
                db_slug_by_value[mopt.value] = mopt.slug
                created += 1
            elif opt.value != mopt.value:
                if not apply_renames and not dry_run:
                    raise CommandError(
                        f"option slug conflicts with DB: {mopt.slug}: "
                        f"db={opt.value!r} vs manifest={mopt.value!r}"
                    )
                renames.append((opt, mopt))
            else:
                present += 1
                if opt.sort_order != mopt.sort_order:
                    if update_display:
                        opt.sort_order = mopt.sort_order
                        opt.save(update_fields=["sort_order"])
                        display_updated += 1
                    else:
                        display_mismatch.append(mopt.slug)

        if renames:
            renamed, display_updated, display_mismatch = self._apply_renames(
                renames,
                db_slug_by_value,
                update_display,
                dry_run,
                display_mismatch,
                renamed,
                renamed_details,
            )

        base = options["path"] or data_dir()
        rules = ToolTypeRules.from_file(f"{base}/tool_type_rules.json")
        for cat in rules.categories:
            self._bind_category(attribute, cat.category)

        if dry_run:
            transaction.set_rollback(True)

        for line in renamed_details:
            self.stdout.write(line)

        summary = (
            f"Атрибут tool_type готов (manifest v{manifest.manifest_version}, "
            f"{len(manifest.options)} options). created={created}, present={present}, "
            f"renamed={renamed}, display_updated={display_updated}, "
            f"display_mismatch={len(display_mismatch)}."
        )
        if dry_run:
            self.stdout.write(self.style.WARNING(f"{summary} (dry run)"))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
        if display_mismatch:
            self.stdout.write(
                self.style.WARNING(
                    "sort_order расходится с manifest (для синхронизации — --update-display): "
                    + ", ".join(display_mismatch[:20])
                )
            )
        return str(created)

    def _apply_renames(
        self,
        renames: list[tuple[AttributeOption, ManifestOption]],
        db_slug_by_value: dict[str, str],
        update_display: bool,
        dry_run: bool,
        display_mismatch: list[str],
        renamed: int,
        renamed_details: list[str],
    ) -> tuple[int, int, list[str]]:
        """Применить переименования, следя за уникальностью value и порядком.

        Главный подводный камень: индекс ``db_slug_by_value`` обязан обновляться
        после каждого переименования. Старые значения освобождаются, новые
        занимаются — иначе ложные срабатывания/пропуски при перекрёстных
        переименованиях.
        """
        display_updated = 0
        renamed_slugs = {mopt.slug for _, mopt in renames}

        target_counts = Counter(mopt.value for _, mopt in renames)
        for value, count in target_counts.items():
            if count > 1:
                raise CommandError(
                    f"rename target value duplicate: value {value!r} is targeted by multiple slugs"
                )

        for _, mopt in renames:
            existing_slug = db_slug_by_value.get(mopt.value)
            if (
                existing_slug is not None
                and existing_slug != mopt.slug
                and existing_slug not in renamed_slugs
            ):
                raise CommandError(
                    f"rename target value conflicts: slug {mopt.slug!r} cannot be renamed to "
                    f"value {mopt.value!r} because it is already used by slug {existing_slug!r}"
                )

        pending = list(renames)
        while pending:
            progress = False
            for item in pending[:]:
                opt, mopt = item
                existing_slug = db_slug_by_value.get(mopt.value)
                if existing_slug is not None and existing_slug != mopt.slug:
                    # Значение всё ещё занято опцией, которая не была обработана.
                    # Если она тоже переименовывается — подождём. Иначе ошибка
                    # уже проверена выше.
                    continue

                old_value = opt.value
                del db_slug_by_value[old_value]
                db_slug_by_value[mopt.value] = mopt.slug

                if not dry_run:
                    opt.value = mopt.value
                    opt.save(update_fields=["value"])
                    if update_display and opt.sort_order != mopt.sort_order:
                        opt.sort_order = mopt.sort_order
                        opt.save(update_fields=["sort_order"])
                        display_updated += 1
                    elif opt.sort_order != mopt.sort_order:
                        display_mismatch.append(mopt.slug)
                else:
                    if update_display and opt.sort_order != mopt.sort_order:
                        display_updated += 1
                    elif opt.sort_order != mopt.sort_order:
                        display_mismatch.append(mopt.slug)

                renamed += 1
                renamed_details.append(f"{mopt.slug}: '{old_value}' -> '{mopt.value}'")
                pending.remove(item)
                progress = True

            if not progress:
                raise CommandError(
                    f"circular rename dependency among slugs: "
                    f"{[mopt.slug for _, mopt in pending]}"
                )

        return renamed, display_updated, display_mismatch

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
