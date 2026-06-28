# apps/ai/tests/test_admin_moderation.py
import pytest

from apps.ai.admin import ModerationQueueAdmin
from apps.catalog.models import Category, EnrichStatus, ModerationProduct, Product, ProductStatus


def _p():
    cat = Category.add_root(name="Перф", slug="perf")
    return Product.objects.create(
        category=cat,
        name="X",
        slug="x",
        description="d",
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
        enrich_status=EnrichStatus.MODERATION,
        content_confidence=0.5,
    )


@pytest.mark.django_db
def test_approve_locks_and_marks_done():
    p = _p()
    admin = ModerationQueueAdmin(ModerationProduct, None)
    admin.approve_content(None, ModerationProduct.objects.filter(pk=p.pk))
    p.refresh_from_db()
    assert p.enrich_status == EnrichStatus.DONE and p.content_locked is True


@pytest.mark.django_db
def test_queue_shows_only_moderation():
    moderation_p = _p()
    cat = moderation_p.category

    # Товар со статусом PENDING
    pending_p = Product.objects.create(
        category=cat,
        name="Y",
        slug="y",
        description="d",
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
        enrich_status=EnrichStatus.PENDING,
    )

    # Товар со статусом DONE
    done_p = Product.objects.create(
        category=cat,
        name="Z",
        slug="z",
        description="d",
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
        enrich_status=EnrichStatus.DONE,
    )

    admin = ModerationQueueAdmin(ModerationProduct, None)
    qs = admin.get_queryset(type("R", (), {"GET": {}})())

    # Очередь содержит ровно один товар (MODERATION)
    assert qs.count() == 1

    # Товар MODERATION присутствует в очереди
    assert qs.filter(pk=moderation_p.pk).exists()

    # Товары PENDING и DONE исключены из очереди
    assert not qs.filter(pk=pending_p.pk).exists()
    assert not qs.filter(pk=done_p.pk).exists()
