"""План переноса товаров из мёртвых legacy-корней в живое дерево (DRF-1438).

Товар опубликован, активен, лежит на складе — и покупатель до него не дойдёт: его
категория снята с витрины. Это не дефект витрины, а потеря выручки на готовом товаре.

Целевой лист **не угадывается**. У подавляющего большинства застрявших товаров уже
проставлен ``tool_type``, а значит получателя можно вывести: взять живые товары того же
типа и посмотреть, в каком листе они лежат. Если тип уверенно живёт в одном листе —
туда и переносим, и в плане видно, чем решение обосновано. Если тип размазан по дереву
или живых товаров такого типа нет — это вопрос к человеку, и такой товар в план не
попадает.

Правило «нет корректного листа — не переносить» (`operations/recategorize.md`, stop)
здесь главнее полноты: положить «в ближайшее» значит закрепить новую ошибку.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .facet_audit import visible_categories, visible_leaves
from .filters import visible_products
from .models import Category, Product, ProductAttributeValue

TOOL_TYPE_SLUG = "tool_type"

#: Какую долю живых товаров типа должен держать лист-получатель. Ровно половина — это
#: монетка (при двух листьях так выходит всегда), поэтому берём с запасом: ниже порога
#: тип считается размазанным, и выбор листа становится догадкой.
MIN_SHARE = 0.6
#: Сколько живых товаров типа должно лежать в листе-получателе. Решать судьбу сотни
#: позиций по одному чужому товару нельзя.
MIN_LEAF_PRODUCTS = 3
#: Какую долю листа-получателя должен занимать переезжающий тип, чтобы считаться в нём
#: своим. Правило «где тип преобладает» наследует ошибки уже существующего дерева: если
#: шесть паяльников по недосмотру лежат в «Лампах», оно уверенно отправит туда все
#: паяльники. Тип, занимающий в листе считаные проценты, — гость, и такой перенос идёт
#: на сверку человеку, а не в автоматический план.
MIN_HOME_SHARE = 0.2


@dataclass
class Move:
    product: Product
    target: Category
    tool_type: str
    tool_type_name: str
    leaf_count: int
    total_count: int
    leaf_total: int = 0
    #: чем лист-получатель занят сейчас: (имя основного типа, сколько товаров)
    leaf_main_type: tuple[str, int] = ("—", 0)

    @property
    def share(self) -> float:
        """Доля живых товаров типа, лежащих в листе-получателе."""
        return self.leaf_count / self.total_count if self.total_count else 0.0

    @property
    def home_share(self) -> float:
        """Доля листа-получателя, занятая этим типом: свой тип или гость."""
        return self.leaf_count / self.leaf_total if self.leaf_total else 0.0

    @property
    def is_home(self) -> bool:
        return self.home_share >= MIN_HOME_SHARE

    @property
    def evidence(self) -> str:
        return (
            f"тип «{self.tool_type_name}»: {self.leaf_count} из {self.total_count} живых "
            f"товаров типа лежат в этом листе ({self.share:.0%}), "
            f"и занимают {self.home_share:.0%} листа"
        )


@dataclass
class Plan:
    moves: list[Move] = field(default_factory=list)
    #: перенос выводится, но тип для листа чужой — глазами, а не автоматом
    needs_review: list[Move] = field(default_factory=list)
    #: (slug типа, имя типа, товаров в пуле, причина отказа)
    unresolved: list[tuple] = field(default_factory=list)
    #: товары без tool_type — решение владельца, тип ради переноса не подставляем
    no_type: list[Product] = field(default_factory=list)
    pool_size: int = 0

    @property
    def by_target(self) -> dict[int, list[Move]]:
        out: dict[int, list[Move]] = defaultdict(list)
        for move in self.moves:
            out[move.target.id].append(move)
        return out


def stranded_products():
    """Опубликованные товары в наличии, лежащие вне видимого дерева."""
    vis_ids = {c.id for c in visible_categories()}
    return (
        visible_products()
        .filter(stock_quantity__gt=0)
        .exclude(category_id__in=vis_ids)
        .select_related("category")
        .order_by("-stock_quantity", "name")
    )


def _tool_types_of(product_ids) -> dict[int, tuple[str, str]]:
    """product_id → (slug типа, имя типа). Источник — PAV, а не attrs_cache.

    В ``attrs_cache`` лежит человекочитаемое значение, а не slug опции; сверка по нему
    молча даёт ноль совпадений.
    """
    rows = ProductAttributeValue.objects.filter(
        attribute__slug=TOOL_TYPE_SLUG,
        product_id__in=list(product_ids),
        value_option__isnull=False,
    ).values_list("product_id", "value_option__slug", "value_option__value")
    return {pid: (slug, value) for pid, slug, value in rows}


def _leaf_distribution(type_slugs) -> dict[str, Counter]:
    """slug типа → счётчик «видимый лист → сколько живых товаров этого типа в нём»."""
    leaf_ids = {c.id for c in visible_leaves(visible_categories())}
    rows = ProductAttributeValue.objects.filter(
        attribute__slug=TOOL_TYPE_SLUG,
        value_option__slug__in=list(type_slugs),
        product__in=visible_products(),
    ).values_list("value_option__slug", "product__category_id")
    dist: dict[str, Counter] = defaultdict(Counter)
    for type_slug, category_id in rows:
        if category_id in leaf_ids:
            dist[type_slug][category_id] += 1
    return dist


def _leaf_totals(leaf_ids) -> Counter:
    """Сколько живых товаров лежит в каждом видимом листе."""
    rows = (
        visible_products()
        .filter(category_id__in=list(leaf_ids))
        .values_list("category_id", flat=True)
    )
    return Counter(rows)


def _leaf_main_types(leaf_ids) -> dict[int, tuple[str, int]]:
    """Лист → (имя преобладающего в нём типа, сколько товаров). Подсказка для сверки:
    видно сразу, родня ли переезжающий тип содержимому листа или чужой ему."""
    rows = ProductAttributeValue.objects.filter(
        attribute__slug=TOOL_TYPE_SLUG,
        value_option__isnull=False,
        product__in=visible_products(),
        product__category_id__in=list(leaf_ids),
    ).values_list("product__category_id", "value_option__value")
    per_leaf: dict[int, Counter] = defaultdict(Counter)
    for category_id, value in rows:
        per_leaf[category_id][value] += 1
    return {cid: counter.most_common(1)[0] for cid, counter in per_leaf.items()}


def build_plan(
    *,
    min_share: float = MIN_SHARE,
    min_leaf: int = MIN_LEAF_PRODUCTS,
    min_home_share: float = MIN_HOME_SHARE,
) -> Plan:
    """Собрать план переноса: куда и почему едет каждый застрявший товар."""
    pool = list(stranded_products())
    plan = Plan(pool_size=len(pool))
    if not pool:
        return plan

    types = _tool_types_of([p.id for p in pool])
    plan.no_type = [p for p in pool if p.id not in types]

    by_type: dict[str, list[Product]] = defaultdict(list)
    names: dict[str, str] = {}
    for product in pool:
        if product.id in types:
            slug, value = types[product.id]
            by_type[slug].append(product)
            names[slug] = value

    dist = _leaf_distribution(by_type)
    categories = {c.id: c for c in Category.objects.all()}
    target_ids = {cid for counter in dist.values() for cid in counter}
    leaf_totals = _leaf_totals(target_ids)
    leaf_main = _leaf_main_types(target_ids)

    for type_slug, products in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        counter = dist.get(type_slug)
        name = names[type_slug]
        if not counter:
            plan.unresolved.append(
                (type_slug, name, len(products), "живых товаров этого типа в дереве нет")
            )
            continue
        (target_id, leaf_count), total = counter.most_common(1)[0], sum(counter.values())
        share = leaf_count / total
        if leaf_count < min_leaf:
            plan.unresolved.append(
                (
                    type_slug,
                    name,
                    len(products),
                    f"в лучшем листе всего {leaf_count} живых товаров типа — мало для решения",
                )
            )
            continue
        if share < min_share:
            plan.unresolved.append(
                (
                    type_slug,
                    name,
                    len(products),
                    f"тип размазан по {len(counter)} листьям, лучший — "
                    f"«{categories[target_id].name}» — держит только {share:.0%}",
                )
            )
            continue
        target = categories[target_id]
        for product in products:
            move = Move(
                product=product,
                target=target,
                tool_type=type_slug,
                tool_type_name=name,
                leaf_count=leaf_count,
                total_count=total,
                leaf_total=leaf_totals.get(target_id, 0),
                leaf_main_type=leaf_main.get(target_id, ("—", 0)),
            )
            (plan.moves if move.home_share >= min_home_share else plan.needs_review).append(move)
    return plan
