"""Замер фильтров каталога: круг «фасет → фильтр», сайдбар по листьям, привязки.

Только чтение. Отвечает на три вопроса, которые иначе меряются руками по URL-ам и
каждый раз по-разному:

1. **Круг сходится?** Фасет сказал «этих 12» — фильтр по тому же значению обязан
   вернуть ровно 12. Расхождение значит, что счётчики в сайдбаре врут, и это
   регрессия, а не косметика.
2. **Есть ли чем фильтровать в листе?** Привязка атрибута к категории сама по себе
   сайдбара не делает: фасет рендерится только там, где у товаров есть значения.
   Поэтому лист меряется не наличием привязки, а числом фасетов, у которых
   набралось хотя бы два разных значения (один вариант ничего не сужает).
3. **Куда привязки вообще смотрят?** Привязка на категории вне витрины не работает
   ни на кого, атрибут без единой привязки не попадает в фильтр никогда.

Замер намеренно живёт отдельным модулем, а не внутри команды: так его вызывают и
тесты, и команда, и (при надобности) shell.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from django.db.models import Count

from .facets import apply_product_attr_filters, build_facets
from .filters import visible_products
from .models import Attribute, Category, CategoryAttribute, ProductImage
from .queries import _category_filter_attributes, _subtree_ids

TOOL_TYPE_SLUG = "tool_type"

#: Фасет с одним значением выбор не сужает — считаем рабочим от двух значений.
MIN_USEFUL_VALUES = 2


# --------------------------------------------------------------------------- #
#  Видимое дерево
# --------------------------------------------------------------------------- #
def visible_categories() -> list[Category]:
    """Категории, до которых покупатель может дойти по дереву.

    Витрина отдаёт корни с ``is_active``+``on_site`` и спускается вниз, поэтому
    один выключенный предок прячет всё поддерево — проверять флаги только у самой
    категории недостаточно. Идём по ``path`` (MP_Node): префиксы длиной, кратной
    ``steplen``, — это ровно цепочка предков.
    """
    step = Category.steplen
    by_path = {c.path: c for c in Category.objects.all()}
    out = []
    for cat in by_path.values():
        chain = (by_path.get(cat.path[:i]) for i in range(step, len(cat.path) + 1, step))
        if all(a is not None and a.is_active and a.on_site for a in chain):
            out.append(cat)
    return sorted(out, key=lambda c: c.path)


def visible_leaves(visible: list[Category] | None = None) -> list[Category]:
    """Видимые категории без видимых детей — страницы, куда приходит покупатель."""
    visible = visible if visible is not None else visible_categories()
    step = Category.steplen
    paths = {c.path for c in visible}
    return [
        c
        for c in visible
        if not any(p.startswith(c.path) and len(p) == len(c.path) + step for p in paths)
    ]


def _root_name(cat: Category, by_path: dict[str, Category]) -> str:
    return by_path[cat.path[: Category.steplen]].name


# --------------------------------------------------------------------------- #
#  1. Круг «фасет → фильтр»
# --------------------------------------------------------------------------- #
@dataclass
class CircleResult:
    pairs: int = 0
    categories: int = 0
    drift: list[tuple] = field(
        default_factory=list
    )  # (slug кат., slug атр., значение, ожид., факт)


def check_circle(categories: list[Category], *, values_per_facet: int = 3) -> CircleResult:
    """Сверить счётчик фасета с числом товаров, которое вернёт фильтр по нему.

    Проверяем ровно то, что видит покупатель: значение фасета отдаётся в URL тем же
    токеном (``slug`` для select-атрибутов, иначе сырое значение), что и уходит в
    ``attr_<slug>=``. Поэтому расхождение здесь — это расхождение на витрине, а не
    в теории.
    """
    res = CircleResult()
    for cat in categories:
        data = build_facets(cat)
        facets = [f for f in data["facets"] if not f.get("is_nav")]
        if not facets:
            continue
        res.categories += 1
        base = visible_products().filter(category_id__in=_subtree_ids(cat))
        for facet in facets:
            for entry in facet["values"][:values_per_facet]:
                token = entry.get("slug") or entry["value"]
                actual = apply_product_attr_filters(base, {facet["slug"]: [str(token)]}, {}).count()
                res.pairs += 1
                if actual != entry["count"]:
                    res.drift.append((cat.slug, facet["slug"], token, entry["count"], actual))
    return res


# --------------------------------------------------------------------------- #
#  2. Сайдбар по листьям
# --------------------------------------------------------------------------- #
@dataclass
class LeafReport:
    category: Category
    section: str
    total: int
    in_stock: int
    usable_facets: list[str]
    empty_facets: list[str]
    type_panel: int
    brands: int
    unbound_axes: list[tuple]  # (slug, значений, товаров) — данные есть, фасета нет

    @property
    def has_sidebar(self) -> bool:
        """Есть ли покупателю чем сузить выдачу.

        Панель типов инструмента — тоже способ сузить, поэтому лист с живой панелью
        не считается пустым, даже если ни один атрибутный фасет не набрался.
        """
        return bool(self.usable_facets) or self.type_panel >= MIN_USEFUL_VALUES


def audit_sidebars(leaves: list[Category], *, min_axis_products: int = 10) -> list[LeafReport]:
    """Для каждого листа — что реально показывается в сайдбаре и чего не хватает.

    ``unbound_axes`` — оси, по которым значения у товаров листа уже есть, а фасета
    нет (атрибут не привязан). Это единственный случай, когда сайдбар чинится
    привязкой; всё остальное чинится наполнением характеристик.
    """
    by_path = {c.path: c for c in Category.objects.all()}
    known = {a.slug for a in Attribute.objects.all()}
    out = []
    for cat in leaves:
        data = build_facets(cat)
        attr_facets = [f for f in data["facets"] if not f.get("is_nav")]
        panel = next((f for f in data["facets"] if f.get("is_nav")), None)
        qs = visible_products().filter(category_id__in=_subtree_ids(cat))

        bound = {a.slug for a in _category_filter_attributes(cat)}
        seen: dict[str, Counter] = defaultdict(Counter)
        for cache in qs.values_list("attrs_cache", flat=True):
            for key, value in (cache or {}).items():
                if not isinstance(value, list | dict):  # массивы фасетами не считаются (#282)
                    seen[key][value] += 1
        unbound = sorted(
            (
                (slug, len(counter), sum(counter.values()))
                for slug, counter in seen.items()
                if slug in known
                and slug not in bound
                and slug != TOOL_TYPE_SLUG
                and len(counter) >= MIN_USEFUL_VALUES
                and sum(counter.values()) >= min_axis_products
            ),
            key=lambda row: -row[2],
        )
        out.append(
            LeafReport(
                category=cat,
                section=_root_name(cat, by_path),
                total=qs.count(),
                in_stock=qs.filter(stock_quantity__gt=0).count(),
                usable_facets=[
                    f["slug"] for f in attr_facets if len(f["values"]) >= MIN_USEFUL_VALUES
                ],
                empty_facets=[
                    f["slug"] for f in attr_facets if len(f["values"]) < MIN_USEFUL_VALUES
                ],
                type_panel=len(panel["values"]) if panel else 0,
                brands=len(data["brands"]),
                unbound_axes=unbound,
            )
        )
    return out


# --------------------------------------------------------------------------- #
#  3. Привязки
# --------------------------------------------------------------------------- #
@dataclass
class BindingsReport:
    total: int
    dead: list[CategoryAttribute]
    dead_only: list[str]  # slug'и атрибутов, живущих ТОЛЬКО на мёртвых категориях
    depth_histogram: dict[int, int]
    orphan_attributes: list[Attribute]


def audit_bindings(visible: list[Category]) -> BindingsReport:
    """Привязки, которые никого не обслуживают, и атрибуты, которые никуда не привязаны.

    ``dead_only`` отвечает на вопрос «не пропал ли фасет из живой категории потому,
    что висит на её выключенном двойнике»: если атрибут встречается только на
    невидимых категориях, его действительно никто не увидит.
    """
    vis_ids = {c.id for c in visible}
    all_bindings = list(CategoryAttribute.objects.select_related("category", "attribute"))
    dead = [ca for ca in all_bindings if ca.category_id not in vis_ids]
    live_attr_ids = {ca.attribute_id for ca in all_bindings if ca.category_id in vis_ids}
    dead_only = sorted({ca.attribute.slug for ca in dead if ca.attribute_id not in live_attr_ids})
    hist = Counter(ca.category.depth for ca in all_bindings if ca.category_id in vis_ids)
    return BindingsReport(
        total=len(all_bindings),
        dead=dead,
        dead_only=dead_only,
        depth_histogram=dict(sorted(hist.items())),
        orphan_attributes=list(Attribute.objects.filter(category_attributes__isnull=True)),
    )


# --------------------------------------------------------------------------- #
#  4. Заполненность (часть B)
# --------------------------------------------------------------------------- #
@dataclass
class FillReport:
    published: int
    in_tree: int
    outside: int
    outside_in_stock: int
    outside_top: list[tuple]  # (id категории, имя, товаров)
    in_stock: int
    no_photo: int
    no_attrs: int
    no_tool_type: int
    no_brand: int


def audit_fill(visible: list[Category]) -> FillReport:
    """Что у каталога с данными — вход для трека наполнения, а не для правки фильтров."""
    vis_ids = {c.id for c in visible}
    published = visible_products()
    outside = published.exclude(category_id__in=vis_ids)
    top = (
        outside.values("category_id", "category__name").annotate(n=Count("id")).order_by("-n")[:10]
    )
    in_stock = published.filter(stock_quantity__gt=0)
    return FillReport(
        published=published.count(),
        in_tree=published.filter(category_id__in=vis_ids).count(),
        outside=outside.count(),
        outside_in_stock=outside.filter(stock_quantity__gt=0).count(),
        outside_top=[(r["category_id"], r["category__name"], r["n"]) for r in top],
        in_stock=in_stock.count(),
        no_photo=in_stock.exclude(id__in=ProductImage.objects.values("product_id")).count(),
        no_attrs=in_stock.filter(attribute_values__isnull=True).count(),
        no_tool_type=in_stock.exclude(attribute_values__attribute__slug=TOOL_TYPE_SLUG).count(),
        no_brand=in_stock.filter(brand="").count(),
    )
