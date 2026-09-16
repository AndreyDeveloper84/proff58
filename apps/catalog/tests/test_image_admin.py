"""Админка автообработки фото (ADR-0014): «было / стало» и решения менеджера.

Стиль — как в test_admin_recategorize.py: эффект проверяем в БД через реальный POST
на changelist (admin_client — суперпользователь из pytest-django).
"""

from __future__ import annotations

import hashlib
import io

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from PIL import Image

from apps.catalog import image_autoprocess
from apps.catalog.models import (
    Category,
    ImageProcessingStatus,
    ImageSource,
    Product,
    ProductImage,
    ProductStatus,
)
from apps.catalog.tasks import process_product_image

CHANGELIST = "admin:catalog_productimage_changelist"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    (tmp_path / "media" / "products").mkdir(parents=True)
    return settings.MEDIA_ROOT


@pytest.fixture
def autoprocess_on(settings):
    settings.FEATURES = {**settings.FEATURES, image_autoprocess.FLAG: True}


def _png(bg=(255, 255, 255)):
    img = Image.new("RGB", (800, 600), bg)
    img.paste((200, 30, 30), (200, 150, 600, 450))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _photo(slug="p1", bg=(255, 255, 255)):
    cat = Category.add_root(name=f"Категория {slug}", slug=f"cat-{slug}")
    product = Product.objects.create(
        category=cat, name="Перфоратор", slug=slug, status=ProductStatus.IMPORTED, price="1000"
    )
    payload = _png(bg)
    image = ProductImage(
        product=product,
        source=ImageSource.RESANTA,
        source_url=f"https://a.example/{slug}.png",
        checksum=hashlib.sha256(payload).hexdigest(),
    )
    image.image.save(f"products/{product.pk}/orig.png", ContentFile(payload), save=True)
    return image


def _processed(slug="p1"):
    image = _photo(slug)
    image_autoprocess.process_image(image.pk)
    image.refresh_from_db()
    return image


def _action(admin_client, action, *images):
    return admin_client.post(
        reverse(CHANGELIST),
        {"action": action, "_selected_action": [i.pk for i in images]},
        follow=True,
    )


# --- страницы -----------------------------------------------------------------------


def test_changelist_filter_and_change_page_load(admin_client, autoprocess_on):
    done = _processed("p1")
    _photo("p2")

    assert admin_client.get(reverse(CHANGELIST)).status_code == 200
    filtered = admin_client.get(reverse(CHANGELIST), {"processing_status__exact": "done"})
    assert filtered.status_code == 200
    assert done.display.url.encode() in filtered.content

    page = admin_client.get(reverse("admin:catalog_productimage_change", args=[done.pk]))
    assert page.status_code == 200


def test_product_card_shows_before_and_after(admin_client, autoprocess_on):
    image = _processed()
    resp = admin_client.get(reverse("admin:catalog_product_change", args=[image.product_id]))
    assert resp.status_code == 200
    assert image.image.url.encode() in resp.content
    assert image.display.url.encode() in resp.content


def test_photos_are_added_only_from_product_card(admin_client):
    assert admin_client.get(reverse("admin:catalog_productimage_add")).status_code == 403


# --- действия -----------------------------------------------------------------------


def test_reprocess_action_processes_photo(admin_client, autoprocess_on):
    image = _photo()
    _action(admin_client, "action_reprocess", image)
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.DONE  # dev: Celery eager


def test_reprocess_overrides_previous_rejection(admin_client, autoprocess_on):
    image = _photo()
    image_autoprocess.revert_to_original(image.pk)
    _action(admin_client, "action_reprocess", image)
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.DONE


def test_reprocess_action_when_disabled_changes_nothing(admin_client):
    image = _photo()
    resp = _action(admin_client, "action_reprocess", image)
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.NONE
    assert "Автообработка выключена" in resp.content.decode()


def test_reprocess_restores_status_when_broker_is_down(autoprocess_on, monkeypatch):
    image = _photo()
    image_autoprocess.revert_to_original(image.pk)

    def broker_down(*args, **kwargs):
        raise ConnectionError("redis недоступен")

    monkeypatch.setattr(process_product_image, "delay", broker_down)
    assert image_autoprocess.reprocess(image.pk) is False
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.REJECTED


def test_revert_to_original_removes_copy_and_sticks(
    admin_client, autoprocess_on, _media, django_capture_on_commit_callbacks
):
    image = _processed()
    copy = _media / image.display.name

    with django_capture_on_commit_callbacks(execute=True):
        _action(admin_client, "action_revert_to_original", image)

    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.REJECTED
    assert not image.display and not copy.exists()
    # автоматика решение не перебивает
    assert image_autoprocess.process_image(image.pk) == "rejected"


def test_accept_only_review_candidates_with_copy(admin_client, autoprocess_on, _media):
    candidate = _processed("p1")
    ProductImage.objects.filter(pk=candidate.pk).update(
        processing_status=ImageProcessingStatus.NEEDS_REVIEW
    )
    blank = _photo("p2")
    ProductImage.objects.filter(pk=blank.pk).update(
        processing_status=ImageProcessingStatus.NEEDS_REVIEW
    )

    resp = _action(admin_client, "action_accept", candidate, blank)

    statuses = dict(ProductImage.objects.values_list("pk", "processing_status"))
    assert statuses[candidate.pk] == ImageProcessingStatus.DONE
    assert statuses[blank.pk] == ImageProcessingStatus.NEEDS_REVIEW
    assert "Не принято: 1" in resp.content.decode()
