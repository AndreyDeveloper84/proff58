"""Публичный контракт AI-возможностей: ``recommend()`` (capability-срез).

V1 ``recommend`` — это ДЕТЕРМИНИРОВАННЫЙ EAV-движок БЕЗ LLM: подбор «похожих по
характеристикам» товаров по денормализованному ``Product.attrs_cache`` (источник —
EAV, который заполняет каталог). Контракт зафиксирован сейчас, внутренность
заменяема: сегодня правила по характеристикам, завтра — гибрид с LLM поверх того
же отобранного набора (см. ``docs/ARCHITECTURE-AI.md`` §3–4, сценарий Б).

Направление зависимости: ``apps.ai → apps.catalog`` (каталог о нас не знает).

Наблюдаемость (``AiCallLog`` из ``docs/ARCHITECTURE-AI.md`` §6) намеренно НЕ
добавлена: в V1 нет ни внешних, ни LLM-вызовов — журналировать нечего. Журнал
появится вместе с первым LLM-провайдером за портом (там и возникнут стоимость,
латентность и деградации, ради которых журнал существует).
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.catalog.filters import visible_products

DEFAULT_LIMIT = 8
MAX_LIMIT = 24
CANDIDATE_CAP = 300


@dataclass(frozen=True)
class Recommendation:
    """Одна рекомендация: id товара, человекочитаемая причина и тех. оценка.

    ``score`` — внутренняя релевантность подбора (чем выше, тем релевантнее);
    стабилен в рамках одного движка, но не является публичным числом для UI.
    """

    product_id: int
    reason: str
    score: float = 0.0


def recommend(*, query=None, context=None, limit: int = DEFAULT_LIMIT) -> list[Recommendation]:
    """ЕДИНЫЙ публичный контракт подбора рекомендаций (capability-срез).

    Вход → выход: ``query``/``context`` → ``list[Recommendation]``. В V1 якорь
    подбора берётся из ``context["product_id"]``; ``query`` зарезервирован под
    текстовый/LLM-движок и пока не используется. Внутренность (сейчас —
    детерминированный EAV ``_similar_by_eav``) заменяема без изменения сигнатуры.

    Возвращает ``[]`` на любом «нет данных»: пустой/невалидный context, неизвестный
    или скрытый якорь, ``limit <= 0``.
    """
    if limit <= 0:
        return []
    limit = min(limit, MAX_LIMIT)

    context = context or {}
    product_id = context.get("product_id")
    if not product_id:
        return []

    anchor = (
        visible_products()
        .filter(pk=product_id)
        .only("id", "category_id", "brand", "attrs_cache")
        .first()
    )
    if anchor is None:
        return []

    return _similar_by_eav(anchor, limit)


def _norm(value):
    """Нормализовать значение характеристики для сравнения.

    str → ``strip().lower()``; bool/int/float → как есть (boolean ``False`` НЕ
    теряется — это валидное значение); list → ``frozenset`` нормализованных
    непустых элементов; None/"" → ``None`` (маркер «пусто», в сравнении игнор).
    """
    if value is None:
        return None
    if isinstance(value, bool):  # до int — bool это подкласс int
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        return v or None
    if isinstance(value, int | float):
        return value
    if isinstance(value, list | tuple | set):
        normed = {n for n in (_norm(item) for item in value) if n is not None}
        return frozenset(normed) or None
    return value


def _overlap(anchor_attrs: dict, cand_attrs: dict) -> int:
    """Число совпадений характеристик якоря и кандидата по общим slug.

    Скаляры — равенство нормализованных значений (1 совпадение). Списки — размер
    пересечения нормализованных множеств. Пустые значения (None/"") не считаются.
    """
    if not anchor_attrs or not cand_attrs:
        return 0
    total = 0
    for slug, a_raw in anchor_attrs.items():
        if slug not in cand_attrs:
            continue
        a = _norm(a_raw)
        b = _norm(cand_attrs[slug])
        if a is None or b is None:
            continue
        if isinstance(a, frozenset) or isinstance(b, frozenset):
            a_set = a if isinstance(a, frozenset) else frozenset({a})
            b_set = b if isinstance(b, frozenset) else frozenset({b})
            total += len(a_set & b_set)
        elif a == b:
            total += 1
    return total


def _same_brand(anchor_brand, cand_brand) -> bool:
    """Совпадение брендов (регистронезависимо) и оба непустые."""
    a = (anchor_brand or "").strip().lower()
    b = (cand_brand or "").strip().lower()
    return bool(a) and a == b


def _in_stock(cand) -> bool:
    """В наличии: по остатку (>0), с фолбэком на stock_status, если остатка нет."""
    qty = cand.get("stock_quantity")
    if qty is not None:
        return qty > 0
    return cand.get("stock_status") == "in_stock"


def _similar_by_eav(product, limit: int) -> list[Recommendation]:
    """Детерминированный подбор «похожих» в той же категории по EAV-характеристикам.

    Кандидаты: видимые товары той же категории (кроме самого якоря), не более
    ``CANDIDATE_CAP`` по возрастанию id. Кандидат включается ТОЛЬКО при наличии
    сигнала (``overlap > 0`` или тот же бренд) — иначе это шум «просто та же
    категория». Сортировка детерминирована: по убыванию score, затем по id.
    """
    anchor_attrs = product.attrs_cache or {}
    anchor_brand = product.brand

    candidates = (
        visible_products()
        .filter(category_id=product.category_id)
        .exclude(pk=product.pk)
        .values("id", "brand", "stock_status", "stock_quantity", "attrs_cache")
        .order_by("id")[:CANDIDATE_CAP]
    )

    scored: list[Recommendation] = []
    for cand in candidates:
        overlap = _overlap(anchor_attrs, cand.get("attrs_cache") or {})
        same_brand = _same_brand(anchor_brand, cand.get("brand"))
        if overlap <= 0 and not same_brand:
            continue  # ни характеристик, ни бренда — отсекаем шум

        in_stock = _in_stock(cand)
        score = overlap * 10 + (3 if same_brand else 0) + (1 if in_stock else 0)
        if overlap > 0:
            reason = f"Похож по характеристикам: {overlap} совпадений"
        else:
            reason = "Та же категория, тот же бренд"
        scored.append(Recommendation(product_id=cand["id"], reason=reason, score=float(score)))

    scored.sort(key=lambda r: (-r.score, r.product_id))
    return scored[:limit]
