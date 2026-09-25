"""Бэкофилл флага is_site_v2 на существующих v2-деревьях.

Помечает ``is_site_v2=True`` поддеревья корней-разделов (slug из SECTION_RULES),
которые ЧИСТЫЕ (без кодов 1С в поддереве). Корни, под чьим slug сидит легаси
(зеркало группы 1С с external_id_1c) — ПРОПУСКАЕТ и предупреждает: такой раздел
надо пересобрать (resolve_v2_root теперь отдаст slug под отдельный v2-корень).

    ./manage.py catalog_mark_v2            # dry-run
    ./manage.py catalog_mark_v2 --commit    # пометить
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.catalog.models import Category
from apps.catalog.semantic import SECTION_RULES


class Command(BaseCommand):
    help = "Пометить is_site_v2=True на чистых v2-деревьях (бэкофилл)."

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true")

    def handle(self, *args, **options):
        w = self.stdout.write
        marked_total = 0
        skipped = []
        for slug in SECTION_RULES:
            root = Category.objects.filter(slug=slug).first()
            if root is None:
                continue
            ids = [root.id] + list(root.get_descendants().values_list("id", flat=True))
            has_legacy = Category.objects.filter(id__in=ids, external_id_1c__isnull=False).exists()
            if has_legacy:
                skipped.append((slug, root.pk, len(ids)))
                continue
            n = Category.objects.filter(id__in=ids, is_site_v2=False).count()
            marked_total += n
            w(f"  {slug:14s} id={root.pk} — пометить узлов: {n} (всего {len(ids)})")
            if options["commit"]:
                Category.objects.filter(id__in=ids).update(is_site_v2=True)

        if skipped:
            w(self.style.ERROR("\n⚠ Пропущены (под slug сидит ЛЕГАСИ с кодами 1С — пересобрать):"))
            for slug, pk, n in skipped:
                w(f"   {slug} (id={pk}, узлов {n})")
            w(
                "   Лечение: catalog_build_skeleton --rollback <снимок> → "
                "catalog_build_skeleton --commit (создаст отдельный v2-корень)."
            )

        if options["commit"]:
            w(self.style.SUCCESS(f"\nCOMMIT: помечено is_site_v2 узлов {marked_total}."))
        else:
            w(self.style.WARNING("\nDRY-RUN: ничего не помечено. Применить — --commit."))
