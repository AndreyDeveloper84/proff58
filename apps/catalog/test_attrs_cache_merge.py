"""Запись attrs_cache из enrich не должна затирать чужие ключи (#5 код-ревью).

enrich-команды читают attrs_cache в память (iterator) и в конце bulk_update'ят
весь словарь. Параллельный 1С-импорт/админ/сигнал между чтением и записью меняет
attrs_cache того же товара → bulk_update откатывал чужие ключи. flush_attrs_cache_
merged перечитывает строку под select_for_update и накладывает ТОЛЬКО дельту
управляемых ключей, сохраняя остальные.
"""

from decimal import Decimal

import pytest
from django.db import transaction

from apps.catalog.attrs_cache import flush_attrs_cache_merged
from apps.catalog.models import Product, ProductStatus


@pytest.mark.django_db
def test_flush_preserves_concurrent_foreign_keys():
    p = Product.objects.create(
        name="t",
        slug="acm-1",
        price=Decimal("1.00"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
        attrs_cache={"keep": "Y", "tool_type": "old"},
    )

    # in-memory копия команды: вычислила новый managed-ключ tool_type=new.
    in_mem = Product(id=p.id)
    in_mem.attrs_cache = {"keep": "Y", "tool_type": "new"}

    # параллельный процесс ДОБАВИЛ чужой ключ в БД после чтения командой.
    Product.objects.filter(id=p.id).update(
        attrs_cache={"keep": "Y", "tool_type": "old", "concurrent": "Z"}
    )

    with transaction.atomic():
        flush_attrs_cache_merged([in_mem], lambda _p: {"tool_type"})

    p.refresh_from_db()
    # managed-ключ применён, чужой concurrent сохранён, прочее не тронуто.
    assert p.attrs_cache == {"keep": "Y", "tool_type": "new", "concurrent": "Z"}


@pytest.mark.django_db
def test_flush_removes_managed_key_absent_in_memory():
    p = Product.objects.create(
        name="t2",
        slug="acm-2",
        price=Decimal("1.00"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
        attrs_cache={"keep": "Y", "tool_type": "old", "concurrent": "Z"},
    )
    in_mem = Product(id=p.id)
    in_mem.attrs_cache = {"keep": "Y"}  # tool_type «выпилен» (prune)

    with transaction.atomic():
        flush_attrs_cache_merged([in_mem], lambda _p: {"tool_type"})

    p.refresh_from_db()
    assert p.attrs_cache == {"keep": "Y", "concurrent": "Z"}
