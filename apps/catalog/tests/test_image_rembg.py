"""Удаление фона нейросетью (ADR-0014, итерация 2): сервис celery-rembg.

rembg в образе проекта нет и не будет (тяжёлые зависимости живут только в образе
celery-rembg), поэтому нейросеть подменяется: `image_rembg.cut_out` возвращает
товар на прозрачном фоне. Проверяем всё вокруг неё — маршрут, статусы, решения.
"""

from __future__ import annotations

import hashlib
import io

import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command
from PIL import Image

from apps.catalog import image_autoprocess, image_processing, image_rembg
from apps.catalog.api.serializers import _image_url
from apps.catalog.models import (
    Category,
    ImageProcessingMode,
    ImageProcessingStatus,
    ImageSource,
    Product,
    ProductImage,
    ProductStatus,
)
from apps.catalog.tasks import remove_photo_background

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    (tmp_path / "media" / "products").mkdir(parents=True)
    return settings.MEDIA_ROOT


@pytest.fixture
def autoprocess_on(settings):
    settings.FEATURES = {**settings.FEATURES, image_autoprocess.FLAG: True}


def _fake_cutout(img):
    """Нейросеть «нашла» прямоугольник по центру кадра."""
    cut = Image.new("RGBA", img.size, (0, 0, 0, 0))
    w, h = img.size
    box = (w // 4, h // 4, 3 * w // 4, 3 * h // 4)
    cut.paste(img.crop(box).convert("RGBA"), box[:2])
    return cut


@pytest.fixture
def fake_rembg(monkeypatch):
    monkeypatch.setattr(image_rembg, "is_available", lambda: True)
    monkeypatch.setattr(image_rembg, "cut_out", _fake_cutout)


def _photo(slug="p1", bg=(0, 0, 0)):
    cat = Category.add_root(name=f"Категория {slug}", slug=f"cat-{slug}")
    product = Product.objects.create(
        category=cat, name="Бензопила", slug=slug, status=ProductStatus.IMPORTED, price="1000"
    )
    img = Image.new("RGB", (800, 600), bg)
    img.paste((230, 190, 20), (250, 200, 550, 400))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    image = ProductImage(
        product=product,
        source=ImageSource.HUTER,
        source_url=f"https://a.example/{slug}.png",
        checksum=hashlib.sha256(buf.getvalue()).hexdigest(),
    )
    image.image.save(f"products/{product.pk}/orig.png", ContentFile(buf.getvalue()), save=True)
    return image


def _queued(image):
    ProductImage.objects.filter(pk=image.pk).update(processing_status=ImageProcessingStatus.QUEUED)


def test_black_background_goes_to_storefront_right_away(autoprocess_on, fake_rembg):
    image = _photo(bg=(0, 0, 0))
    _queued(image)

    assert image_autoprocess.process_image(image.pk, rembg=True) == ImageProcessingStatus.DONE
    image.refresh_from_db()
    assert image.processing_mode == ImageProcessingMode.REMBG
    assert _image_url(image) == image.display.url
    corner = Image.open(image.display.path).convert("RGB").getpixel((5, 5))
    assert all(c >= 245 for c in corner)  # чёрный фон стал белым


def test_other_background_waits_for_manager(autoprocess_on, fake_rembg):
    image = _photo(bg=(128, 128, 128))
    _queued(image)

    assert (
        image_autoprocess.process_image(image.pk, rembg=True) == ImageProcessingStatus.NEEDS_REVIEW
    )
    image.refresh_from_db()
    assert image.display  # кандидат готов
    assert _image_url(image) == image.image.url  # но на витрине пока оригинал

    assert image_autoprocess.accept_review(image.pk) is True
    image.refresh_from_db()
    assert _image_url(image) == image.display.url


def test_empty_mask_goes_to_review_without_copy(autoprocess_on, monkeypatch):
    monkeypatch.setattr(image_rembg, "is_available", lambda: True)
    monkeypatch.setattr(image_rembg, "cut_out", lambda img: Image.new("RGBA", img.size))
    image = _photo()
    _queued(image)

    assert (
        image_autoprocess.process_image(image.pk, rembg=True) == ImageProcessingStatus.NEEDS_REVIEW
    )
    image.refresh_from_db()
    assert not image.display


def test_without_rembg_installed_photo_keeps_waiting(autoprocess_on, monkeypatch, _media):
    monkeypatch.setattr(image_rembg, "is_available", lambda: False)
    image = _photo()
    _queued(image)

    assert image_autoprocess.process_image(image.pk, rembg=True) == "rembg_unavailable"
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.NEEDS_REMBG
    assert not (_media / "products" / "display").exists()


def test_rembg_crash_marks_failed(autoprocess_on, monkeypatch):
    def crash(img):
        raise RuntimeError("onnxruntime упал")

    monkeypatch.setattr(image_rembg, "is_available", lambda: True)
    monkeypatch.setattr(image_rembg, "cut_out", crash)
    image = _photo()
    _queued(image)

    assert image_autoprocess.process_image(image.pk, rembg=True) == ImageProcessingStatus.FAILED


def test_regular_worker_never_calls_rembg(autoprocess_on, monkeypatch):
    def must_not_run(img):
        raise AssertionError("обычный воркер не должен запускать нейросеть")

    monkeypatch.setattr(image_rembg, "cut_out", must_not_run)
    image = _photo()
    assert image_autoprocess.process_image(image.pk) == ImageProcessingStatus.NEEDS_REMBG


def test_disabled_rembg_task_returns_photo_to_waiting():
    image = _photo()
    _queued(image)
    assert image_autoprocess.process_image(image.pk, rembg=True) == "disabled"
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.NEEDS_REMBG


def test_command_rembg_takes_only_waiting_photos(autoprocess_on, fake_rembg, capsys):
    waiting = _photo("p1")
    image_autoprocess.process_image(waiting.pk)  # обычный воркер: needs_rembg
    untouched = _photo("p2")  # none — не дело нейросети

    call_command("process_product_images", "--rembg")  # dev: Celery eager

    statuses = dict(ProductImage.objects.values_list("pk", "processing_status"))
    assert statuses[waiting.pk] == ImageProcessingStatus.DONE
    assert statuses[untouched.pk] == ImageProcessingStatus.NONE
    assert "--profile rembg up -d celery-rembg" in capsys.readouterr().out


def test_rembg_task_routed_to_its_own_queue(settings):
    assert remove_photo_background.name == "apps.catalog.tasks.remove_photo_background"
    assert settings.CELERY_TASK_ROUTES[remove_photo_background.name] == {"queue": "rembg"}
    assert remove_photo_background.acks_late is True
    # упавшее по памяти фото не возвращается в очередь и не роняет воркер по кругу
    assert remove_photo_background.reject_on_worker_lost is False


def test_render_crops_to_mask_and_fits_square(monkeypatch):
    monkeypatch.setattr(image_rembg, "cut_out", _fake_cutout)
    content = image_rembg.render(Image.new("RGB", (800, 600), (0, 0, 0)))
    img = Image.open(io.BytesIO(content))
    assert img.size == (image_processing.CANVAS, image_processing.CANVAS)
