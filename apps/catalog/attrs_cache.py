"""Безопасная запись Product.attrs_cache из пакетных enrich-команд (#5).

Проблема: enrich читает attrs_cache в память (iterator) и в конце делает
bulk_update(["attrs_cache"]) всем словарём. Параллельный 1С-импорт/админ/сигнал
rebuild_attrs_cache между чтением и записью меняет attrs_cache того же товара —
и bulk_update молча откатывает чужие ключи (товар пропадает из фасета).

Решение: перед записью перечитать строку под select_for_update и наложить ТОЛЬКО
дельту ключей, которыми владеет команда (managed), сохранив остальные.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from .models import Product

BATCH = 1000


def flush_attrs_cache_merged(
    products: Iterable[Product],
    managed_for: Callable[[Product], set[str]],
    *,
    batch_size: int = BATCH,
) -> int:
    """Записать attrs_cache товаров, слив дельту управляемых ключей с актуальной БД.

    products — объекты Product с уже вычисленным in-memory ``attrs_cache``.
    managed_for(product) — множество ключей, которыми владеет команда: ключ из
    in-memory словаря записывается, отсутствующий managed-ключ удаляется; все
    прочие ключи берутся из СВЕЖЕЙ (перечитанной под блокировкой) строки.

    Вызывать внутри transaction.atomic() — нужно для select_for_update. Возвращает
    число записанных строк.
    """
    by_id = {p.id: p for p in products}
    if not by_id:
        return 0

    locked = Product.objects.select_for_update().filter(id__in=list(by_id)).order_by("id")
    to_write: list[Product] = []
    for row in locked:
        our = by_id[row.id].attrs_cache or {}
        fresh = dict(row.attrs_cache or {})
        for slug in managed_for(by_id[row.id]):
            if slug in our:
                fresh[slug] = our[slug]
            else:
                fresh.pop(slug, None)
        row.attrs_cache = fresh
        to_write.append(row)

    Product.objects.bulk_update(to_write, ["attrs_cache"], batch_size=batch_size)
    return len(to_write)
