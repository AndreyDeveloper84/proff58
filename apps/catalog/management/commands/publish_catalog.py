"""Массовая публикация товаров для витрины/API.

Витрина и API показывают только видимые товары (`Product.is_visible` →
`is_active=True, status=published`). После импорта из 1С товары в статусе `imported`,
поэтому категории пустые. Команда переводит выбранные товары в `published` + `is_active`.
Зеркалит логику `ProductAdmin.action_publish`, но для массовой/CLI-публикации.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.category_tree import invalidate_category_tree_cache
from apps.catalog.models import Category, Product, ProductStatus


class Command(BaseCommand):
    help = "Опубликовать товары (status=published, is_active=True): --all или --category <slug>."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Все непубликованные товары.")
        parser.add_argument("--category", help="Slug категории (включая потомков).")
        parser.add_argument(
            "--from-status",
            default="imported,needs_review",
            help="Исходные статусы через запятую (по умолчанию imported,needs_review).",
        )
        parser.add_argument("--limit", type=int, help="Ограничить число публикуемых товаров.")
        parser.add_argument(
            "--dry-run", action="store_true", help="Только посчитать, без изменения БД."
        )

    def handle(self, *args, **opts):
        if not opts["all"] and not opts["category"]:
            raise CommandError("Укажите --all или --category <slug>.")

        from_statuses = [s.strip() for s in opts["from_status"].split(",") if s.strip()]
        valid = set(ProductStatus.values)
        unknown = [s for s in from_statuses if s not in valid]
        if unknown:
            raise CommandError(
                f"Неизвестные статусы: {', '.join(unknown)}. Допустимо: {', '.join(sorted(valid))}."
            )

        # Уже опубликованные и активные — пропускаем.
        qs = Product.objects.exclude(status=ProductStatus.PUBLISHED, is_active=True)
        if from_statuses:
            qs = qs.filter(status__in=from_statuses)

        if opts["category"]:
            try:
                cat = Category.objects.get(slug=opts["category"])
            except Category.DoesNotExist as exc:
                raise CommandError(f"Категория не найдена: {opts['category']}") from exc
            ids = [cat.pk, *cat.get_descendants().values_list("pk", flat=True)]
            qs = qs.filter(category_id__in=ids)

        total = qs.count()
        no_category = qs.filter(category__isnull=True).count()

        if opts["limit"]:
            picked = list(qs.values_list("pk", flat=True)[: opts["limit"]])
            qs = Product.objects.filter(pk__in=picked)
            planned = len(picked)
        else:
            planned = total

        if opts["dry_run"]:
            self.stdout.write(f"[dry-run] К публикации: {planned} (всего подходящих: {total}).")
            if no_category:
                self.stdout.write(
                    self.style.WARNING(
                        f"Без категории: {no_category} — не попадут в категорийную выдачу."
                    )
                )
            return

        updated = qs.update(status=ProductStatus.PUBLISHED, is_active=True)
        # bulk update минует сигналы → инвалидируем кэш дерева/счётчиков каталога вручную.
        invalidate_category_tree_cache()

        self.stdout.write(self.style.SUCCESS(f"Опубликовано: {updated}."))
        if no_category:
            self.stdout.write(
                self.style.WARNING(
                    f"Без категории: {no_category} — видны в общем списке, но не в категориях."
                )
            )
