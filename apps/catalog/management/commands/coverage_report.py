"""Coverage-отчёт по tool_type и характеристикам — вход для гейтинга Фазы 2 (#225, §17, §10.4).

Read-only. Считает, насколько РЕАЛЬНО заполнены технические атрибуты у товаров каждого
типа инструмента, чтобы решить, какой фильтр показывать как основной, какой в
«Дополнительные», а какой скрыть до обогащения.

Метрика (§17.1):
    coverage(attribute, tool_type) = товаров типа с непустым значением атрибута / всего товаров типа

Источник «заполненности» — ``attrs_cache`` (денормализованный JSONB, по которому и работают
фасеты/фильтры витрины). Берём именно его, а не сырой ``ProductAttributeValue``: отчёт должен
мерить то же, что увидит фильтр на витрине (ключ есть и значение не JSON null — как в facets).

Правило включения (§10.4) учитывает И процент, И абсолют:
    основной:       coverage >= 30%  И abs >= --min-abs   ИЛИ кураторское закрепление;
    дополнительный: 5%..30% И abs >= --min-abs   ИЛИ abs >= --large-abs (много штук при низком %);
    скрыть:         иначе.
Кураторское закрепление пока не имеет отдельного поля — как прокси берём
``CategoryAttribute.is_seo_facet=True`` (тот же «второй оси навигации» флаг, что и is_nav в A1).

    python manage.py coverage_report
    python manage.py coverage_report --tool-type perforatory
    python manage.py coverage_report --top 5 --format md
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.db.models.fields.json import KeyTextTransform

from apps.catalog.filters import visible_products
from apps.catalog.models import Attribute, Category, CategoryAttribute
from apps.catalog.queries import TOOL_TYPE_SLUG, _category_filter_attributes

# Пороги (§10.4) — ориентиры, уточняются по данным; абсолют перекрывается флагами.
MAIN_PCT = 30
EXTRA_PCT = 5
DEFAULT_MIN_ABS = 10  # минимум заполненных штук, иначе фильтр бессмыслен (§10.4: «20×10% = 2 шт»)
DEFAULT_LARGE_ABS = 100  # много штук даже при низком % → хотя бы «доп» (§10.4: «10000×4% = 400 шт»)
DEFAULT_TOP = 3

REC_MAIN = "основной"
REC_EXTRA = "дополнительный"
REC_HIDE = "скрыть"


def recommend(pct: float, abs_filled: int, pinned: bool, min_abs: int, large_abs: int) -> str:
    """Рекомендация по §10.4 на ТОЧНОМ проценте (не округлённом — иначе 29.5% уехало бы в 30%).

    ``large_abs`` — самостоятельный «спасательный» гейт: много заполненных штук даже при
    низком % → хотя бы «дополнительный» (§10.4: 10000×4% = 400 шт). Осмыслен при
    ``large_abs >= min_abs`` (так по дефолтам); иначе вызывающий сам отвечает за согласованность.
    """
    if pinned:
        return REC_MAIN
    if pct >= MAIN_PCT and abs_filled >= min_abs:
        return REC_MAIN
    if pct >= EXTRA_PCT and abs_filled >= min_abs:
        return REC_EXTRA
    if abs_filled >= large_abs:  # низкий %, но абсолютно много — не скрываем
        return REC_EXTRA
    return REC_HIDE


def _type_base(slug: str):
    """Видимые товары tool_type — relational, как ``ProductFilter.filter_tool_type``."""
    return visible_products().filter(
        attribute_values__attribute__slug=TOOL_TYPE_SLUG,
        attribute_values__value_option__slug=slug,
    )


def _relevant_attributes(cat_ids: list[int], all_attrs: bool) -> list:
    """Filterable-атрибуты, релевантные типу: объединение _category_filter_attributes по
    категориям товаров типа (с наследованием). tool_type исключаем. Фолбэк/`--all-attrs` —
    все is_filterable. Сортировка по slug — детерминизм вывода.

    Опирается на ``Attribute.is_filterable`` (внутри _category_filter_attributes), НЕ на
    ``CategoryAttribute.is_filter`` — отчёт мерит покрытие ВСЕХ filterable-кандидатов, а
    is_filter (включён ли фасет для категории) — отдельный гейт показа, не данных.

    N+1: _category_filter_attributes дёргает get_ancestors() на категорию, т.е. запросов
    ~O(числа РАЗНЫХ категорий типа). Для tool_type это обычно 1–несколько категорий, а
    команда офлайновая (разовый запуск) — приемлемо; батчить предков не усложняем.
    """
    if not all_attrs and cat_ids:
        by_slug: dict[str, Attribute] = {}
        for c in Category.objects.filter(id__in=cat_ids):
            for a in _category_filter_attributes(c):
                by_slug.setdefault(a.slug, a)
        attrs = [a for a in by_slug.values() if a.slug != TOOL_TYPE_SLUG]
        if attrs:
            return sorted(attrs, key=lambda a: a.slug)
    return list(
        Attribute.objects.filter(is_filterable=True).exclude(slug=TOOL_TYPE_SLUG).order_by("slug")
    )


def _pinned_slugs(cat_ids: list[int]) -> set[str]:
    """Кураторски закреплённые атрибуты для категорий типа (прокси: is_seo_facet)."""
    return set(
        CategoryAttribute.objects.filter(category_id__in=cat_ids, is_seo_facet=True).values_list(
            "attribute__slug", flat=True
        )
    )


def _coverage_rows(base, attrs, min_abs, large_abs, pinned):
    """total + filled по каждому атрибуту ОДНИМ aggregate (group-by, без N+1).

    «Заполнен» = ключ в attrs_cache есть и значение не JSON null — через
    ``KeyTextTransform(...).isnull=False`` (та же семантика, что у фасетов A1).
    """
    qs = base
    agg = {"_total": Count("id", distinct=True)}
    for i, a in enumerate(attrs):
        col = f"_v{i}"
        qs = qs.annotate(**{col: KeyTextTransform(a.slug, "attrs_cache")})
        agg[f"f{i}"] = Count("id", distinct=True, filter=Q(**{f"{col}__isnull": False}))
    data = qs.aggregate(**agg)
    total = data["_total"] or 0
    rows = []
    for i, a in enumerate(attrs):
        filled = data[f"f{i}"] or 0
        exact = filled * 100 / total if total else 0.0  # точный % для решения; round — для вывода
        rec = recommend(exact, filled, a.slug in pinned, min_abs, large_abs)
        rows.append(
            {"slug": a.slug, "name": a.name, "pct": round(exact), "abs": filled, "rec": rec}
        )
    return total, rows


def _md(s: str) -> str:
    """Экранировать '|' для markdown-таблицы (значения из 1С могут его содержать)."""
    return str(s).replace("|", "\\|")


class Command(BaseCommand):
    help = "Coverage-отчёт: заполненность характеристик по типам инструмента (read-only, #225)."

    def add_arguments(self, parser):
        parser.add_argument("--tool-type", default=None, help="slug типа; без него — топ-N типов")
        parser.add_argument(
            "--top", type=int, default=DEFAULT_TOP, help="сколько типов (без --tool-type)"
        )
        parser.add_argument("--min-abs", type=int, default=DEFAULT_MIN_ABS)
        parser.add_argument("--large-abs", type=int, default=DEFAULT_LARGE_ABS)
        parser.add_argument(
            "--all-attrs", action="store_true", help="все is_filterable вместо категорийных"
        )
        parser.add_argument("--format", choices=["text", "md"], default="text")

    def handle(self, *args, **opts):
        types = self._resolve_types(opts["tool_type"], opts["top"])
        if not types:
            self.stdout.write(
                self.style.WARNING(
                    "Товаров с tool_type не найдено — сначала импорт и enrich_tool_type."
                )
            )
            return
        emit = self._emit_md if opts["format"] == "md" else self._emit_text
        for slug, label, total in types:
            base = _type_base(slug)
            cat_ids = list(base.values_list("category_id", flat=True).distinct())  # один раз на тип
            attrs = _relevant_attributes(cat_ids, opts["all_attrs"])
            pinned = _pinned_slugs(cat_ids)
            total, rows = _coverage_rows(base, attrs, opts["min_abs"], opts["large_abs"], pinned)
            emit(slug, label, total, rows)

    def _resolve_types(self, tool_type, top):
        """[(slug, label, total)] — заданный тип или топ-N по числу видимых товаров."""
        grp = (
            visible_products()
            .filter(
                attribute_values__attribute__slug=TOOL_TYPE_SLUG,
                attribute_values__value_option__isnull=False,
            )
            .values("attribute_values__value_option__slug", "attribute_values__value_option__value")
            .annotate(c=Count("id", distinct=True))
            .order_by("-c")
        )
        if tool_type:
            grp = grp.filter(attribute_values__value_option__slug=tool_type)
        else:
            grp = grp[:top]
        return [
            (
                r["attribute_values__value_option__slug"],
                r["attribute_values__value_option__value"],
                r["c"],
            )
            for r in grp
        ]

    # --- вывод ---
    def _emit_text(self, slug, label, total, rows):
        self.stdout.write(f"\ntool_type = {slug} ({label}): товаров {total}")
        if not total:
            return
        self.stdout.write(f"  {'атрибут':22}{'cov':>5}{'abs':>12}   рекомендация")
        for r in rows:
            abs_str = f"{r['abs']}/{total}"
            self.stdout.write(f"  {r['slug']:22}{r['pct']:>4}%{abs_str:>12}   {r['rec']}")

    def _emit_md(self, slug, label, total, rows):
        # label/slug приходят из 1С (произвольный текст) → экранируем '|', иначе ломает таблицу.
        self.stdout.write(f"\n**{_md(slug)}** ({_md(label)}) — товаров: {total}\n")
        if not total:
            return
        self.stdout.write("| Атрибут | Coverage % | Abs | Рекомендация |")
        self.stdout.write("|---|---:|---:|---|")
        for r in rows:
            self.stdout.write(
                f"| {_md(r['slug'])} | {r['pct']}% | {r['abs']}/{total} | {r['rec']} |"
            )
