"""Аудит публичной таксономии каталога (read-only, без ORM).

Чистая логика: на вход — содержимое файлов ``data/`` (маппинг групп 1С, дерево
1С, правила ``tool_type`` и характеристик), на выход — структурированный отчёт о
проблемах публичного дерева категорий. БД не нужна: считаем объёмы по реальному
дампу ``catalog_fixed.json`` и сверяем три оси (категория / tool_type / атрибут).

Назначение — Фаза 1 редизайна таксономии (``docs/plans/catalog-taxonomy-redesign.md``):
дать фактуру для отчётов в ``docs/reports/`` без изменения данных. Никаких записей
в БД, файлы ``data/`` только читаются.

Терминология осей (см. ADR-0001):

* **категория** — узел дерева ``Category`` (одна основная на товар);
* **tool_type** — EAV-атрибут (вторая ось навигации / SEO-фасет), НЕ узел дерева;
* **характеристика** — EAV-атрибут/опция (фасет/фильтр);
* **бренд** — поле ``Product.brand`` (никогда не категория).

Эвристики находок намеренно консервативны: задача — подсветить кандидатов для
ручного решения владельца, а не автоматически перекраивать дерево.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from apps.catalog.ingest import group_index, iter_products
from apps.catalog.tool_type import normalize

# --- Пороги эвристик (товаров) ----------------------------------------------
GIANT_LEAF = 1500  # корень-лист или одиночный лист такого размера — недифференцирован
BIG_LEAF = 800  # крупный лист: кандидат на дробление по tool_type

# --- Лексика находок ---------------------------------------------------------
# Узлы-бренды в дереве (бренд должен жить в Product.brand, не в категории).
BRAND_TOKENS = (
    "hitachi",
    "хитачи",
    "зубр",
    "эхо",
    "echo",
    "makita",
    "макита",
    "bosch",
    "бош",
    "dewalt",
    "metabo",
    "метабо",
    "интерскол",
    "patriot",
    "ryobi",
)
# Мусорные/смешанные листья («свалки»).
GARBAGE_TOKENS = ("проч", "разное", "прочая", "прочие", "прочее")
# Деление по питанию вместо типа товара (питание — это фасет power_source).
POWER_SPLIT_NAMES = ("аккумуляторный инструмент", "сетевой инструмент")


@dataclass
class CategoryStat:
    """Публичная категория (site_path) и число привязанных товаров."""

    path: tuple[str, ...]
    count: int

    @property
    def depth(self) -> int:
        return len(self.path)

    @property
    def leaf(self) -> str:
        return self.path[-1] if self.path else ""

    @property
    def root(self) -> str:
        return self.path[0] if self.path else ""


@dataclass
class Finding:
    """Одна находка аудита: код, заголовок, затронутые узлы, рекомендация."""

    code: str
    title: str
    severity: str  # high | medium | low
    rows: list[tuple[str, int]] = field(default_factory=list)  # (узел, товаров)
    recommendation: str = ""


@dataclass
class AuditResult:
    total_products: int
    mapped_onsite: int
    offsite: int
    unmapped: int
    categories: list[CategoryStat]  # on_site, по убыванию count
    roots: list[tuple[str, int, int]]  # (раздел, товаров, число подкатегорий)
    depth_hist: dict[int, int]
    offsite_rows: list[tuple[str, int]]
    findings: list[Finding]
    designed_axes: dict  # сводка осей tool_type/атрибутов из правил


def _has_token(name: str, tokens) -> bool:
    n = normalize(name)
    return any(t in n for t in tokens)


def analyze(
    mapping: list[dict],
    tree: list[dict],
    tool_type_rules: dict,
    attribute_rules: dict,
) -> AuditResult:
    """Посчитать объёмы и собрать находки по публичной таксономии."""
    gindex = group_index(mapping)

    path_counts: Counter[tuple[str, ...]] = Counter()
    offsite_counts: Counter[str] = Counter()
    unmapped_counts: Counter[str] = Counter()
    total = 0

    for _product, parent_gid in iter_products(tree):
        total += 1
        row = gindex.get(str(parent_gid)) if parent_gid is not None else None
        if row is None:
            unmapped_counts[str(parent_gid)] += 1
            continue
        if not row.get("on_site", True):
            offsite_counts[row.get("group_1c") or str(parent_gid)] += 1
            continue
        path = tuple(row.get("site_path") or [])
        if not path:
            offsite_counts[row.get("group_1c") or str(parent_gid)] += 1
            continue
        path_counts[path] += 1

    categories = sorted(
        (CategoryStat(path=p, count=c) for p, c in path_counts.items()),
        key=lambda s: s.count,
        reverse=True,
    )

    # Разделы верхнего уровня: товаров в поддереве + число под-категорий.
    root_products: Counter[str] = Counter()
    root_children: defaultdict[str, set[tuple[str, ...]]] = defaultdict(set)
    for s in categories:
        root_products[s.root] += s.count
        if s.depth >= 2:
            root_children[s.root].add(s.path[1:])
    roots = sorted(
        ((r, root_products[r], len(root_children[r])) for r in root_products),
        key=lambda t: t[1],
        reverse=True,
    )

    depth_hist = dict(Counter(s.depth for s in categories))

    findings = _collect_findings(categories, tool_type_rules, mapping)

    return AuditResult(
        total_products=total,
        mapped_onsite=sum(path_counts.values()),
        offsite=sum(offsite_counts.values()),
        unmapped=sum(unmapped_counts.values()),
        categories=categories,
        roots=roots,
        depth_hist=depth_hist,
        offsite_rows=offsite_counts.most_common(),
        findings=findings,
        designed_axes=_designed_axes(tool_type_rules, attribute_rules),
    )


def _collect_findings(
    categories: list[CategoryStat],
    tool_type_rules: dict,
    mapping: list[dict],
) -> list[Finding]:
    findings: list[Finding] = []
    by_path = {s.path: s for s in categories}

    # F1 — деление по питанию вместо типа товара.
    power_rows = [
        (" / ".join(s.path), s.count) for s in categories if normalize(s.leaf) in POWER_SPLIT_NAMES
    ]
    if power_rows:
        findings.append(
            Finding(
                "F1",
                "Электроинструмент разбит по ПИТАНИЮ, а не по типу товара",
                "high",
                power_rows,
                "Перестроить на узлы по типу (Перфораторы, Дрели и шуруповёрты, УШМ, "
                "Лобзики, Пилы, Шлифмашины…); питание вынести в фасет power_source.",
            )
        )

    # F2 — корни-листья гиганты (товары лежат прямо в разделе верхнего уровня).
    root_leaf = [(s.root, s.count) for s in categories if s.depth == 1 and s.count >= GIANT_LEAF]
    if root_leaf:
        findings.append(
            Finding(
                "F2",
                "Недифференцированные корни-листья (товары прямо в корне раздела)",
                "high",
                root_leaf,
                "Завести листовые категории/типы внутри раздела; крупные однородные "
                "буккеты дробить по tool_type, а не оставлять единым списком.",
            )
        )

    # F3 — мусорные/смешанные листья («Прочее», «Прочая оснастка»).
    garbage = [
        (" / ".join(s.path), s.count) for s in categories if _has_token(s.leaf, GARBAGE_TOKENS)
    ]
    if garbage:
        findings.append(
            Finding(
                "F3",
                "Мусорные/смешанные листья-«свалки»",
                "medium",
                garbage,
                "Расклассифицировать по типам; остаток скрыть под скрытый корень "
                "(on_site:false) до ручной разметки, не показывать «Прочее» на витрине.",
            )
        )

    # F4 — узлы-бренды в дереве.
    brand_nodes = [
        (" / ".join(s.path), s.count)
        for s in categories
        if any(_has_token(part, BRAND_TOKENS) for part in s.path)
    ]
    if brand_nodes:
        findings.append(
            Finding(
                "F4",
                "Бренды просочились в дерево категорий",
                "high",
                brand_nodes,
                "Бренд → Product.brand (+ фасет совместимости). Узлы-бренды убрать; "
                "запчасти структурировать по типу запчасти, не по производителю.",
            )
        )

    # F5 — дубль сущности: категория-лист совпадает со значением tool_type.
    tt_values = _tool_type_value_norms(tool_type_rules)
    dup = []
    for s in categories:
        nleaf = normalize(s.leaf)
        # строго: имя листа точно совпадает со значением tool_type (без нечётких подстрок)
        if nleaf and nleaf in tt_values:
            dup.append((" / ".join(s.path), s.count))
    if dup:
        findings.append(
            Finding(
                "F5",
                "Дубль оси: категория-лист дублирует значение tool_type",
                "medium",
                dup,
                "Решить осознанно: либо это категория (узел дерева), либо tool_type "
                "(вторая ось). Не держать одну сущность в обеих осях одновременно.",
            )
        )

    # F6 — крупные одиночные листья: кандидаты на дробление по tool_type.
    roots_with_tt = _roots_with_tool_type(tool_type_rules)
    big_single = [
        (" / ".join(s.path), s.count)
        for s in categories
        if s.count >= BIG_LEAF
        and not _has_children(s.path, by_path)
        and not _has_token(s.leaf, GARBAGE_TOKENS)
        and normalize(s.leaf) not in POWER_SPLIT_NAMES
        and s.root in roots_with_tt
    ]
    if big_single:
        findings.append(
            Finding(
                "F6",
                "Крупные однородные листья — кандидаты на навигацию через TypePanel",
                "medium",
                big_single,
                "Внутри раздела с tool_type использовать вторую ось (TypePanel) вместо "
                "единого длинного списка; узлы дерева не плодить.",
            )
        )

    # F7 — tool_type-категории без приёмника в публичном дереве.
    root_names = {normalize(r.get("site_path", [None])[0]) for r in mapping if r.get("site_path")}
    recat_targets = _recategorize_targets(tool_type_rules)
    missing = [(t, 0) for t in recat_targets if normalize(t) not in root_names]
    if missing:
        findings.append(
            Finding(
                "F7",
                "Цели recategorize из tool_type_rules без раздела-приёмника в дереве",
                "low",
                missing,
                "Завести/уточнить разделы-приёмники (Сварка, Электрика и освещение и т.п.) "
                "или убрать висячие recategorize-правила.",
            )
        )

    return findings


def _has_children(path: tuple[str, ...], by_path: dict) -> bool:
    return any(p[: len(path)] == path and len(p) > len(path) for p in by_path)


def _tool_type_value_norms(rules: dict) -> set[str]:
    out: set[str] = set()
    for cat in rules.get("categories", []):
        for rule in cat.get("rules", []):
            if rule.get("action") == "recategorize":
                continue
            v = rule.get("tool_type")
            if v:
                out.add(normalize(v))
    return out


def _roots_with_tool_type(rules: dict) -> set[str]:
    return {cat.get("category") for cat in rules.get("categories", []) if cat.get("category")}


def _recategorize_targets(rules: dict) -> list[str]:
    out: list[str] = []
    for cat in rules.get("categories", []):
        for rule in cat.get("rules", []):
            if rule.get("action") == "recategorize":
                # tool_type вида «В категорию «Сварка»» — вытащим имя в кавычках.
                label = rule.get("tool_type", "")
                inner = label.split("«")[-1].split("»")[0] if "«" in label else label
                if inner:
                    out.append(inner)
    return out


def _designed_axes(tool_type_rules: dict, attribute_rules: dict) -> dict:
    """Сводка спроектированных осей (из правил) для coverage-отчёта."""
    tt_by_cat = {
        cat.get("category"): len(
            [r for r in cat.get("rules", []) if r.get("action") != "recategorize"]
        )
        for cat in tool_type_rules.get("categories", [])
    }
    attrs_by_type = {}
    for t in attribute_rules.get("tool_types", []):
        attrs = t.get("attributes", [])
        attrs_by_type[t.get("tool_type")] = {
            "category": t.get("category"),
            "total": len(attrs),
            "filter": len([a for a in attrs if a.get("is_filter")]),
            "seo": len([a for a in attrs if a.get("is_seo_facet")]),
        }
    return {"tool_types_per_category": tt_by_cat, "attributes_per_tool_type": attrs_by_type}
