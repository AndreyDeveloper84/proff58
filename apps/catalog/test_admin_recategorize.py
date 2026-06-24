"""Тесты bulk-действия админки «Перепривязать выбранные товары в категорию».

Проверяют ключевую гарантию ADR-0007: ручная перепривязка ставит
``category_is_manual=True`` (защита от авторазбора/переимпорта 1С), а пустой
выбор категории — no-op.

Стиль — как в test_moderation_queue.py: эффект проверяем в БД через реальный
POST на changelist (admin_client — суперпользователь из pytest-django).
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.catalog.models import Category, Product

CHANGELIST = "admin:catalog_product_changelist"


@pytest.mark.django_db
def test_bulk_recategorize_sets_category_and_manual(admin_client):
    src = Category.add_root(name="Старая", slug="rc-old")
    dst = Category.add_root(name="Перфораторы", slug="rc-perf")
    p1 = Product.objects.create(name="Перф 1", slug="rc-p1", category=src)
    p2 = Product.objects.create(name="Перф 2", slug="rc-p2", category=None)

    resp = admin_client.post(
        reverse(CHANGELIST),
        {
            "action": "action_set_category",
            "target_category": dst.pk,
            "_selected_action": [p1.pk, p2.pk],
        },
        follow=True,
    )
    assert resp.status_code == 200

    p1.refresh_from_db()
    p2.refresh_from_db()
    assert p1.category_id == dst.pk and p1.category_is_manual is True
    assert p2.category_id == dst.pk and p2.category_is_manual is True


@pytest.mark.django_db
def test_bulk_recategorize_without_target_is_noop(admin_client):
    src = Category.add_root(name="Старая2", slug="rc-old2")
    p = Product.objects.create(name="X", slug="rc-x", category=src)

    admin_client.post(
        reverse(CHANGELIST),
        {
            "action": "action_set_category",
            "target_category": "",  # категория не выбрана
            "_selected_action": [p.pk],
        },
        follow=True,
    )

    p.refresh_from_db()
    # Категория не изменилась, ручной флаг не выставлен.
    assert p.category_id == src.pk
    assert p.category_is_manual is False
