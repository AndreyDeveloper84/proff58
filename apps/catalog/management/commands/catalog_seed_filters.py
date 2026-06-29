"""Посев фильтров на v2-корень: копировать CategoryAttribute с легаси-корня.

Характеризация (CategoryAttribute с is_filter/group/sort_order) в каталоге сидит на
ЛЕГАСИ-КОРНЯХ (напр. «Ручной инструмент» — 15 фильтров), а листья наследуют её
closest-wins (apps/catalog/queries.py:_category_filter_attributes). При миграции v2
листы уезжают под новый голый v2-корень и теряют наследование → фильтры пропадают.

Эта команда копирует строки CategoryAttribute с одного/нескольких легаси-корней на
v2-корень секции. Дальше все v2-листы наследуют фильтры автоматически (рендерятся по
факту наличия значений — пустые фасеты не показываются).

    ./manage.py catalog_seed_filters --section ruchnoy --from ruchnoy-instrument          # dry-run
    ./manage.py catalog_seed_filters --section ruchnoy --from ruchnoy-instrument --commit
    ./manage.py catalog_seed_filters --rollback var/restructure/seedfilters-<...>.json

Идемпотентно: если у v2-корня уже есть строка для атрибута — пропускается
(unique_together category+attribute). Запускать между build и swap; в отчёте/на витрине
сразу видно фильтры. Сбрасывает кэш фасетов/дерева на commit.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.category_tree import invalidate_category_tree_cache
from apps.catalog.facets import invalidate_facets_cache
from apps.catalog.models import Category, CategoryAttribute
from apps.catalog.semantic import SECTION_RULES, load_rules


class Command(BaseCommand):
    help = "Посеять фильтры на v2-корень: копировать CategoryAttribute с легаси-корня."

    def add_arguments(self, parser):
        parser.add_argument("--section", choices=sorted(SECTION_RULES))
        parser.add_argument(
            "--from",
            dest="from_slugs",
            default="",
            help="Slug'и легаси-корней-источников через запятую.",
        )
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--rollback", metavar="FILE")

    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        if options["rollback"]:
            return self._rollback(options["rollback"])
        section = options["section"]
        if not section:
            raise CommandError("Укажите --section или --rollback FILE.")
        doc, _ = load_rules(SECTION_RULES[section])
        v2 = Category.objects.filter(slug=doc["section_slug"]).first()
        if v2 is None:
            raise CommandError(
                f"v2-корень (slug={doc['section_slug']}) не найден — сначала постройте раздел."
            )
        src_slugs = [s.strip() for s in options["from_slugs"].split(",") if s.strip()]
        if not src_slugs:
            raise CommandError("Укажите --from <легаси-slug>[,<slug>...] (источник фильтров).")
        sources = list(Category.objects.filter(slug__in=src_slugs))
        missing = set(src_slugs) - {c.slug for c in sources}
        if missing:
            raise CommandError(f"Не найдены источники: {', '.join(sorted(missing))}")

        existing_attr_ids = set(v2.category_attributes.values_list("attribute_id", flat=True))
        plan: list[CategoryAttribute] = []
        planned_attr_ids = set(existing_attr_ids)
        for src in sources:
            for ca in src.category_attributes.select_related("attribute").all():
                if ca.attribute_id in planned_attr_ids:
                    continue  # уже есть на v2 или взято из более раннего источника
                planned_attr_ids.add(ca.attribute_id)
                plan.append(ca)

        self._report(v2, sources, existing_attr_ids, plan)

        if not options["commit"]:
            self.stdout.write(
                self.style.WARNING("\nDRY-RUN: ничего не создано. Применить — --commit.")
            )
            return
        self._commit(section, v2, plan)

    # ------------------------------------------------------------------ #
    def _report(self, v2, sources, existing_attr_ids, plan):
        w = self.stdout.write
        w(self.style.MIGRATE_HEADING(f"\n=== Посев фильтров на «{v2.name}» (slug={v2.slug}) ==="))
        w(f"Уже есть на v2-корне: {len(existing_attr_ids)} CategoryAttribute")
        for src in sources:
            n = src.category_attributes.count()
            nf = src.category_attributes.filter(is_filter=True).count()
            w(f"Источник {src.slug}: CategoryAttribute={n} (фильтров={nf})")
        w(self.style.SUCCESS(f"\nК копированию (новых): {len(plan)}"))
        for ca in plan[:40]:
            flag = "фильтр" if ca.is_filter else "—"
            w(f"  {ca.attribute.slug:28s} [{flag}] group={ca.group} sort={ca.sort_order}")

    def _commit(self, section, v2, plan):
        backup_dir = Path(settings.BASE_DIR) / "var" / "restructure"
        backup_dir.mkdir(parents=True, exist_ok=True)
        from django.utils import timezone

        ts = timezone.now().strftime("%Y%m%d-%H%M%S")
        backup_path = backup_dir / f"seedfilters-{section}-{ts}.json"
        created_ids: list[int] = []
        with transaction.atomic():
            for ca in plan:
                new = CategoryAttribute.objects.create(
                    category=v2,
                    attribute=ca.attribute,
                    is_required=ca.is_required,
                    is_filter=ca.is_filter,
                    group=ca.group,
                    is_seo_facet=ca.is_seo_facet,
                    sort_order=ca.sort_order,
                )
                created_ids.append(new.pk)
            backup_path.write_text(
                json.dumps({"section": section, "created": created_ids}, ensure_ascii=False)
            )
            transaction.on_commit(invalidate_facets_cache)
            transaction.on_commit(invalidate_category_tree_cache)
        self.stdout.write(
            self.style.SUCCESS(
                f"\nCOMMIT: создано CategoryAttribute {len(created_ids)} на v2-корне «{v2.name}». "
                f"Снимок отката: {backup_path}"
            )
        )

    # ------------------------------------------------------------------ #
    def _rollback(self, file_path: str):
        path = Path(file_path)
        if not path.exists():
            raise CommandError(f"Снимок не найден: {file_path}")
        try:
            data = json.loads(path.read_text())
        except ValueError as exc:
            raise CommandError(f"Битый JSON: {exc}") from exc
        ids = data.get("created", [])
        with transaction.atomic():
            n, _ = CategoryAttribute.objects.filter(id__in=ids).delete()
            transaction.on_commit(invalidate_facets_cache)
            transaction.on_commit(invalidate_category_tree_cache)
        self.stdout.write(self.style.SUCCESS(f"ROLLBACK: удалено CategoryAttribute из {len(ids)}."))
