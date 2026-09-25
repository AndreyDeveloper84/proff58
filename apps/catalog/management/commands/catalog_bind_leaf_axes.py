"""Точечная привязка осей к листьям по манифесту (DRF-1428, A2).

Массовый перенос привязок вниз замер отверг: фасет рендерится там, где у товаров
есть значения, а не там, где привязан атрибут. Но точечные случаи существуют — ось
заполнена, а фасета нет. Эта команда закрывает именно их, по явному списку, а не
широким правилом.

Главное здесь — порог покрытия. Фасет поверх редко заполненной оси не сужает выдачу,
а **прячет** её: покупатель выбирает «6 мм» и видит 5 товаров вместо 100, потому что
у остальных 95 поле просто не заполнено — а выглядит это как «такого нет в наличии».
Та же болезнь, что у пустого бренда. Поэтому ось привязывается, только если она
заполнена хотя бы у ``min_coverage`` товаров листа и имеет минимум два значения;
пройти мимо порога можно лишь явным ``force`` с письменным ``reason``.

    ./manage.py catalog_bind_leaf_axes                   # dry-run по манифесту
    ./manage.py catalog_bind_leaf_axes --commit          # применить + снимок отката
    ./manage.py catalog_bind_leaf_axes --rollback FILE   # вернуть как было

Манифест — ``data/catalog_leaf_filters.json``. Идемпотентна: уже привязанное
пропускается.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.category_tree import invalidate_category_tree_cache
from apps.catalog.facets import invalidate_facets_cache
from apps.catalog.filters import visible_products
from apps.catalog.models import Attribute, Category, CategoryAttribute
from apps.catalog.queries import _category_filter_attributes, _subtree_ids

MANIFEST = "catalog_leaf_filters.json"
#: Доля товаров листа, у которых ось должна быть заполнена. Ниже — фасет не сужает
#: выдачу, а прячет непроставленное.
DEFAULT_MIN_COVERAGE = 0.5


@dataclass
class Candidate:
    category: Category
    attribute: Attribute
    values: int
    filled: int
    total: int
    forced: bool
    reason: str

    @property
    def coverage(self) -> float:
        return self.filled / self.total if self.total else 0.0

    def verdict(self, min_coverage: float) -> str:
        """Пусто — привязываем; иначе текст отказа."""
        if self.values < 2:
            return f"значение одно ({self.values}) — выбор ничего не сужает"
        if self.coverage < min_coverage:
            return (
                f"заполнена у {self.filled} из {self.total} товаров "
                f"({self.coverage:.0%}) — фасет спрячет остальные"
            )
        return ""


class Command(BaseCommand):
    help = "Привязать оси к листьям по манифесту data/catalog_leaf_filters.json."

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--rollback", metavar="FILE")
        parser.add_argument("--manifest", metavar="FILE", help="Свой путь к манифесту.")

    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        if options["rollback"]:
            return self._rollback(options["rollback"])

        doc = self._load(options["manifest"])
        min_coverage = float(doc.get("min_coverage", DEFAULT_MIN_COVERAGE))
        ready, refused, already = [], [], []

        for entry in doc.get("bindings", []):
            category = Category.objects.filter(slug=entry["category"]).first()
            if category is None:
                raise CommandError(f"Нет категории со slug={entry['category']}")
            forced = bool(entry.get("force"))
            reason = entry.get("reason", "")
            if forced and not reason:
                raise CommandError(
                    f"{entry['category']}: force без reason. Обход порога положено объяснять."
                )
            bound = {a.slug for a in _category_filter_attributes(category)}
            products = visible_products().filter(category_id__in=_subtree_ids(category))
            total = products.count()
            counts = self._axis_counts(products)

            for slug in entry["attributes"]:
                attribute = Attribute.objects.filter(slug=slug).first()
                if attribute is None:
                    raise CommandError(f"Нет характеристики со slug={slug}")
                if slug in bound:
                    already.append((category, attribute))
                    continue
                values, filled = counts.get(slug, (0, 0))
                cand = Candidate(category, attribute, values, filled, total, forced, reason)
                verdict = cand.verdict(min_coverage)
                (ready if not verdict or forced else refused).append((cand, verdict))

        self._report(ready, refused, already, min_coverage)
        if not ready:
            self.stdout.write(self.style.WARNING("\nПривязывать нечего."))
            return
        if not options["commit"]:
            self.stdout.write(
                self.style.WARNING("\nDRY-RUN: ничего не записано. Применить — --commit.")
            )
            return
        self._commit([c for c, _v in ready])

    # ------------------------------------------------------------------ #
    def _load(self, override) -> dict:
        path = Path(override) if override else Path(settings.BASE_DIR) / "data" / MANIFEST
        if not path.exists():
            raise CommandError(f"Манифест не найден: {path}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise CommandError(f"Битый JSON манифеста: {exc}") from exc

    def _axis_counts(self, products) -> dict[str, tuple[int, int]]:
        """slug оси → (разных значений, товаров со значением) по attrs_cache листа."""
        seen: dict[str, set] = {}
        filled: dict[str, int] = {}
        for cache in products.values_list("attrs_cache", flat=True):
            for key, value in (cache or {}).items():
                if isinstance(value, list | dict):
                    continue  # массивы фасетами не поддерживаются (#282)
                seen.setdefault(key, set()).add(value)
                filled[key] = filled.get(key, 0) + 1
        return {slug: (len(values), filled[slug]) for slug, values in seen.items()}

    # ------------------------------------------------------------------ #
    def _report(self, ready, refused, already, min_coverage):
        w = self.stdout.write
        w(self.style.MIGRATE_HEADING("\n=== Точечная привязка осей к листьям ==="))
        w(f"Порог покрытия: {min_coverage:.0%} товаров листа, минимум 2 значения.\n")
        if already:
            w(f"Уже привязано (пропуск): {len(already)}")
            for category, attribute in already:
                w(f"  {category.slug} / {attribute.slug}")
        w(self.style.SUCCESS(f"\nК привязке: {len(ready)}"))
        for cand, _verdict in ready:
            mark = " [FORCE: " + cand.reason + "]" if cand.forced else ""
            w(
                f"  {cand.category.slug} / {cand.attribute.slug}: "
                f"{cand.values} знач. у {cand.filled} из {cand.total} ({cand.coverage:.0%}){mark}"
            )
        if refused:
            w(self.style.WARNING(f"\nОтклонено порогом: {len(refused)}"))
            for cand, verdict in refused:
                w(f"  {cand.category.slug} / {cand.attribute.slug}: {verdict}")

    def _commit(self, candidates):
        backup_dir = Path(settings.BASE_DIR) / "var" / "restructure"
        backup_dir.mkdir(parents=True, exist_ok=True)
        path = backup_dir / f"bind-leaf-axes-{timezone.now():%Y%m%d-%H%M%S}.json"
        with transaction.atomic():
            created = [
                CategoryAttribute.objects.create(
                    category=cand.category, attribute=cand.attribute, is_filter=True
                ).pk
                for cand in candidates
            ]
            path.write_text(
                json.dumps({"created": created}, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            transaction.on_commit(invalidate_facets_cache)
            transaction.on_commit(invalidate_category_tree_cache)
        self.stdout.write(
            self.style.SUCCESS(f"\nCOMMIT: создано {len(created)}. Снимок отката: {path}")
        )

    def _rollback(self, file_path: str):
        path = Path(file_path)
        if not path.exists():
            raise CommandError(f"Снимок не найден: {file_path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        with transaction.atomic():
            n, _ = CategoryAttribute.objects.filter(id__in=data.get("created", [])).delete()
            transaction.on_commit(invalidate_facets_cache)
            transaction.on_commit(invalidate_category_tree_cache)
        self.stdout.write(self.style.SUCCESS(f"ROLLBACK: удалено привязок {n}."))
