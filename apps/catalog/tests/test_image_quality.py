"""Проверка «кривых» фото при автообработке (ADR-0014): мелкие, пустые, повторы кадра.

Такие фото не уходят на витрину сами: получают статус «Ждёт проверки» и причину,
которую менеджер видит в админке.
"""

from __future__ import annotations

import hashlib
import io
import json

import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.urls import reverse
from PIL import Image, ImageFilter, ImageOps

from apps.catalog import image_autoprocess, image_processing, image_rembg
from apps.catalog.api.serializers import _image_url
from apps.catalog.models import (
    Category,
    ImageProcessingStatus,
    ImageReviewReason,
    ImageSource,
    Product,
    ProductImage,
    ProductStatus,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    (tmp_path / "media" / "products").mkdir(parents=True)
    return settings.MEDIA_ROOT


@pytest.fixture
def autoprocess_on(settings):
    """Флаг включён, ОБА маршрута уже проверены на выборке и публикуют без человека.

    Соответствует состоянию системы после калибровки (§5.4): большинство тестов
    этого файла проверяют полный автоматический путь до витрины. Наблюдение по
    умолчанию (маршрут не в `PRODUCT_IMAGE_AUTO_ACCEPT_ROUTES`, кандидат остаётся
    в `observed`) — отдельные тесты `test_image_quality.py::test_*_observed_by_default*`.
    """
    settings.FEATURES = {**settings.FEATURES, image_autoprocess.FLAG: True}
    settings.PRODUCT_IMAGE_AUTO_ACCEPT_ROUTES = {"trim", "rembg_black"}


@pytest.fixture
def autoprocess_observed(settings):
    """Как `autoprocess_on`, но маршруты ещё НЕ проверены — режим наблюдения."""
    settings.FEATURES = {**settings.FEATURES, image_autoprocess.FLAG: True}
    settings.PRODUCT_IMAGE_AUTO_ACCEPT_ROUTES = set()


def _shot(size=(800, 600), bg=(255, 255, 255), box=(100, 150, 700, 450)):
    """Кадр с товаром-градиентом: рисунок и мягкие края, как у настоящего снимка."""
    img = Image.new("RGB", (800, 600), bg)
    width, height = box[2] - box[0], box[3] - box[1]
    texture = Image.linear_gradient("L").rotate(90).resize((width, height)).convert("RGB")
    img.paste(ImageOps.colorize(texture.convert("L"), (180, 20, 20), (20, 20, 180)), box[:2])
    img = img.filter(ImageFilter.GaussianBlur(2))
    return img.resize(size, Image.LANCZOS) if size != img.size else img


def _encode(img, fmt="PNG"):
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _product(slug="p1"):
    cat = Category.add_root(name=f"Категория {slug}", slug=f"cat-{slug}")
    return Product.objects.create(
        category=cat, name="Товар", slug=slug, status=ProductStatus.IMPORTED, price="1000"
    )


def _photo(product, img=None, *, n=1, is_main=False):
    payload = _encode(_shot() if img is None else img)
    image = ProductImage(
        product=product,
        source=ImageSource.VSEINSTRUMENTI,
        source_url=f"https://a.example/{product.slug}/{n}.png",
        checksum=hashlib.sha256(payload).hexdigest(),
        is_main=is_main,
    )
    image.image.save(f"products/{product.pk}/{n}.png", ContentFile(payload), save=True)
    return image


def _run(image, **kw):
    status = image_autoprocess.process_image(image.pk, **kw)
    image.refresh_from_db()
    return status


# --- чистые функции ---------------------------------------------------------------


def test_same_shot_in_other_size_and_format_is_duplicate():
    a = image_processing.process(_encode(_shot())).fingerprint
    b = image_processing.process(_encode(_shot(size=(1000, 750)), "JPEG")).fingerprint
    assert len(a) == 64
    assert image_processing.is_duplicate(a, b)


def test_other_side_of_product_is_not_duplicate():
    a = image_processing.process(_encode(_shot())).fingerprint
    mirrored = image_processing.process(_encode(ImageOps.mirror(_shot()))).fingerprint
    assert not image_processing.is_duplicate(a, mirrored)
    assert image_processing.fingerprint_distance(a, mirrored) > image_processing.DUPLICATE_DISTANCE


def test_empty_fingerprint_is_never_duplicate():
    assert not image_processing.is_duplicate("", "")


def test_small_product_is_marked_small():
    tiny = image_processing.process(_encode(_shot(box=(100, 100, 160, 130))))
    big = image_processing.process(_encode(_shot()))
    assert tiny.square.small is True
    assert big.square.small is False


# --- автообработка ------------------------------------------------------------------


def test_small_photo_waits_for_review_with_reason(autoprocess_on):
    image = _photo(_product(), _shot(box=(100, 100, 160, 130)))

    assert _run(image) == ImageProcessingStatus.NEEDS_REVIEW
    assert image.review_reason == ImageReviewReason.SMALL
    assert image.candidate  # кандидат готов, но на витрине пока оригинал
    assert not image.display
    assert _image_url(image) == image.image.url

    accepted = image_autoprocess.accept_candidate(
        image.pk, expected_checksum=image.candidate_checksum, expected_revision=image.revision
    )
    assert accepted is True
    image.refresh_from_db()
    assert _image_url(image) == image.display.url


def test_good_photo_has_no_reason_and_keeps_fingerprint(autoprocess_on):
    image = _photo(_product())
    assert _run(image) == ImageProcessingStatus.DONE
    assert image.review_reason == ""
    assert image.duplicate_of_id is None
    assert len(image.fingerprint) == 64


def test_repeated_shot_goes_to_review_and_points_to_first(autoprocess_on):
    product = _product()
    first = _photo(product, is_main=True)
    second = _photo(product, _shot(size=(1000, 750)), n=2)

    assert _run(first) == ImageProcessingStatus.DONE
    assert _run(second) == ImageProcessingStatus.NEEDS_REVIEW
    assert second.review_reason == ImageReviewReason.DUPLICATE
    assert second.duplicate_of_id == first.pk
    assert second.candidate  # кандидат есть: менеджер может принять или отклонить
    assert not second.display  # витрину дубль не трогает без решения человека

    # повторная обработка первого кадра не делает дублем и его
    ProductImage.objects.filter(pk=first.pk).update(processing_status=ImageProcessingStatus.NONE)
    assert _run(first) == ImageProcessingStatus.DONE
    assert first.duplicate_of_id is None


def test_other_sides_of_product_are_not_duplicates(autoprocess_on):
    product = _product()
    front = _photo(product)
    back = _photo(product, ImageOps.mirror(_shot()), n=2)
    assert _run(front) == ImageProcessingStatus.DONE
    assert _run(back) == ImageProcessingStatus.DONE


def test_same_shot_of_different_products_is_not_duplicate(autoprocess_on):
    # серия товаров под одним фото — законна
    first = _photo(_product("p1"))
    second = _photo(_product("p2"))
    assert _run(first) == ImageProcessingStatus.DONE
    assert _run(second) == ImageProcessingStatus.DONE


def test_repeated_dark_shot_is_not_sent_to_rembg(autoprocess_on, monkeypatch):
    def must_not_run(img):
        raise AssertionError("повтор кадра не нужно гонять через нейросеть")

    monkeypatch.setattr(image_rembg, "is_available", lambda: True)
    monkeypatch.setattr(image_rembg, "cut_out", must_not_run)
    product = _product()
    first = _photo(product, _shot(bg=(0, 0, 0)))
    second = _photo(product, _shot(size=(1000, 750), bg=(0, 0, 0)), n=2)

    assert _run(first) == ImageProcessingStatus.NEEDS_REMBG
    ProductImage.objects.filter(pk=second.pk).update(
        processing_status=ImageProcessingStatus.NEEDS_REMBG
    )
    assert _run(second, rembg=True) == ImageProcessingStatus.NEEDS_REVIEW
    assert second.review_reason == ImageReviewReason.DUPLICATE
    assert not second.display


def test_blank_photo_reason_is_empty(autoprocess_on):
    """Пустой результат — достоверный технический брак: контролёр отклоняет
    кандидата сам, без человека (§5.4)."""
    image = _photo(_product(), Image.new("RGB", (500, 500), (255, 255, 255)))
    assert _run(image) == ImageProcessingStatus.CANDIDATE_REJECTED
    assert image.review_reason == ImageReviewReason.EMPTY
    assert image.qc_decision == "auto_reject_candidate"


def _cut_center(img):
    cut = Image.new("RGBA", img.size, (0, 0, 0, 0))
    w, h = img.size
    box = (w // 8, h // 8, 7 * w // 8, 7 * h // 8)
    cut.paste(img.crop(box).convert("RGBA"), box[:2])
    return cut


@pytest.mark.parametrize(
    ("bg", "status", "reason"),
    [
        ((0, 0, 0), ImageProcessingStatus.DONE, ""),
        ((128, 128, 128), ImageProcessingStatus.SKIPPED, ""),
    ],
    ids=["black", "other"],
)
def test_rembg_reasons(autoprocess_on, monkeypatch, bg, status, reason):
    monkeypatch.setattr(image_rembg, "is_available", lambda: True)
    monkeypatch.setattr(image_rembg, "cut_out", _cut_center)
    image = _photo(_product(), _shot(bg=bg))
    ProductImage.objects.filter(pk=image.pk).update(processing_status=ImageProcessingStatus.QUEUED)

    assert _run(image, rembg=True) == status
    assert image.review_reason == reason


def test_rembg_small_cutout_waits_for_review(autoprocess_on, monkeypatch):
    def tiny_cut(img):
        cut = Image.new("RGBA", img.size, (0, 0, 0, 0))
        cut.paste((200, 30, 30, 255), (10, 10, 40, 30))
        return cut

    monkeypatch.setattr(image_rembg, "is_available", lambda: True)
    monkeypatch.setattr(image_rembg, "cut_out", tiny_cut)
    image = _photo(_product(), _shot(bg=(0, 0, 0)))
    ProductImage.objects.filter(pk=image.pk).update(processing_status=ImageProcessingStatus.QUEUED)

    assert _run(image, rembg=True) == ImageProcessingStatus.NEEDS_REVIEW
    assert image.review_reason == ImageReviewReason.SMALL


def test_replacing_file_clears_review_reason(autoprocess_on):
    product = _product()
    first = _photo(product)
    second = _photo(product, _shot(size=(1000, 750)), n=2)
    _run(first)
    _run(second)
    assert second.duplicate_of_id == first.pk

    second.image.save("products/new.png", ContentFile(_encode(ImageOps.mirror(_shot()))))
    second.refresh_from_db()
    assert (second.review_reason, second.duplicate_of_id, second.fingerprint) == ("", None, "")


def test_deleting_first_shot_keeps_duplicate(autoprocess_on):
    product = _product()
    first = _photo(product)
    second = _photo(product, _shot(size=(1000, 750)), n=2)
    _run(first)
    _run(second)
    first.delete()
    second.refresh_from_db()
    assert second.duplicate_of_id is None
    assert second.review_reason == ImageReviewReason.DUPLICATE


# --- админка и отчёт ------------------------------------------------------------------


def test_admin_shows_reason_and_link_to_first_shot(admin_client, autoprocess_on):
    product = _product()
    first = _photo(product)
    second = _photo(product, _shot(size=(1000, 750)), n=2)
    small = _photo(_product("p2"), _shot(box=(100, 100, 160, 130)))
    for image in (first, second, small):
        _run(image)

    changelist = reverse("admin:catalog_productimage_changelist")
    resp = admin_client.get(changelist, {"review_reason__exact": "duplicate"})
    html = resp.content.decode()
    assert resp.status_code == 200
    assert "Такой же кадр у товара уже есть" in html
    assert reverse("admin:catalog_productimage_change", args=[first.pk]) in html

    resp = admin_client.get(changelist)
    assert "Мелкое фото" in resp.content.decode()
    page = admin_client.get(reverse("admin:catalog_productimage_change", args=[second.pk]))
    assert page.status_code == 200


def test_dry_run_reports_quality_problems(capsys, tmp_path):
    product = _product("p1")
    first = _photo(product, is_main=True)
    second = _photo(product, _shot(size=(1000, 750)), n=2)
    _photo(product, ImageOps.mirror(_shot()), n=3)
    no_main = _product("p2")
    _photo(no_main, _shot(box=(100, 100, 160, 130)))
    out = tmp_path / "report.json"

    call_command("process_product_images", "--dry-run", "--out", str(out))

    lines = {
        line.strip().rsplit(" ", 1)[0].strip(): line.rsplit(" ", 1)[1]
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("  ")
    }
    assert lines["мелкие (товар меньше половины квадрата)"] == "1"
    assert lines["повтор кадра того же товара"] == "1"
    report = json.loads(out.read_text(encoding="utf-8"))
    assert (report["small"], report["duplicates"]) == (1, 1)
    assert report["products_without_main"] == [no_main.pk]
    items = {row["id"]: row for row in report["items"]}
    assert items[second.pk]["duplicate_of"] == first.pk
    assert not ProductImage.objects.exclude(processing_status=ImageProcessingStatus.NONE).exists()
