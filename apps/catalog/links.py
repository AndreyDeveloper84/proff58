"""Взаимные связи товаров: «покупают вместе» и «аналоги».

Живут в той же таблице, что и совместимость (``ProductCompatibility``), но
ставятся иначе: не построчно в карточке, а галочками по списку кандидатов —
менеджер за раз проходит целую подгруппу. Здесь — операции над набором связей
одного товара; форма админки и management-команды пользуются только ими, чтобы
канонизация пар и уникальность жили в одном месте.

Оба вида симметричны (см. ``SYMMETRIC_COMPATIBILITY_KINDS``): ребро A→B и есть
ребро B→A, поэтому «снять» ищет связь по обоим концам.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Q

from .models import (
    SYMMETRIC_COMPATIBILITY_KINDS,
    CompatibilityKind,
    CompatibilityOrigin,
    Product,
    ProductCompatibility,
)

__all__ = ["linked_ids", "set_links", "add_links"]


def _check_symmetric(kind: str) -> None:
    if kind not in SYMMETRIC_COMPATIBILITY_KINDS:
        raise ValueError(f"{kind} — направленный вид связи, здесь работают только взаимные")


def linked_ids(product: Product, kind: str) -> set[int]:
    """Товары, связанные с данным (по обоим концам ребра)."""
    _check_symmetric(kind)
    pairs = ProductCompatibility.objects.filter(
        Q(source=product) | Q(target=product), kind=kind
    ).values_list("source_id", "target_id")
    return {s if t == product.pk else t for s, t in pairs}


@transaction.atomic
def set_links(
    product: Product,
    kind: str,
    target_ids: set[int] | list[int],
    *,
    origin: str = CompatibilityOrigin.MANUAL,
    scope_ids: set[int] | list[int] | None = None,
) -> tuple[int, int]:
    """Привести связи товара к переданному набору. Возвращает (добавлено, снято).

    ``scope_ids`` ограничивает снятие показанным списком кандидатов: страница
    подбора видит не весь каталог, и молча стирать связи, которых на экране не
    было, нельзя. None — снимать всё лишнее.
    """
    _check_symmetric(kind)
    wanted = {int(pid) for pid in target_ids} - {product.pk}
    current = linked_ids(product, kind)

    removable = current - wanted
    if scope_ids is not None:
        removable &= {int(pid) for pid in scope_ids}
    if removable:
        ProductCompatibility.objects.filter(
            Q(source=product, target_id__in=removable) | Q(source_id__in=removable, target=product),
            kind=kind,
        ).delete()

    created = 0
    for pid in sorted(wanted - current):
        source_id, target_id = ProductCompatibility.canonical_pair(product.pk, pid, kind)
        _, was_created = ProductCompatibility.objects.get_or_create(
            source_id=source_id,
            target_id=target_id,
            kind=kind,
            defaults={"origin": origin},
        )
        created += int(was_created)

    return created, len(removable)


def add_links(
    product: Product,
    kind: str,
    target_ids: set[int] | list[int],
    *,
    origin: str = CompatibilityOrigin.AI,
) -> int:
    """Дописать связи, ничего не снимая (прогон ИИ дополняет работу менеджера)."""
    _check_symmetric(kind)
    created, _ = set_links(
        product, kind, set(linked_ids(product, kind)) | set(map(int, target_ids)), origin=origin
    )
    return created


# Человекочитаемые подписи для админки и команд.
KIND_LABELS = {
    CompatibilityKind.CROSS_SELL: "Покупают вместе",
    CompatibilityKind.ANALOG: "Аналог",
}
