"""Что автообработка НЕ трогает и когда забирает работу у нейросети (ADR-0014).

Прочий фон — это не подложка, а часть кадра: карточка с характеристиками, товар
в кейсе, съёмка в работе. Нейросеть вырезала бы оттуда один инструмент и выбросила
текст с комплектацией (просмотр 45 копий стенда 20.09.2026), поэтому такие фото
остаются как есть. А там, где фон снимать можно — на чёрном, — результат проверяется
на разрыв: съеденная карточка распадается на обрывки букв.
"""

from __future__ import annotations

import hashlib
import io

import pytest
from django.core.files.base import ContentFile
from django.core.management import CommandError, call_command
from PIL import Image, ImageDraw, ImageFilter

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


def _scene(bg=(128, 128, 128)):
    """Кадр на цветной подложке — так выглядит съёмка в работе или карточка."""
    img = Image.new("RGB", (800, 600), bg)
    ImageDraw.Draw(img).rectangle((150, 120, 650, 480), fill=(200, 40, 40))
    return img.filter(ImageFilter.GaussianBlur(2))


def _encode(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _photo(product, img, n=1):
    payload = _encode(img)
    image = ProductImage(
        product=product,
        source=ImageSource.VSEINSTRUMENTI,
        source_url=f"https://a.example/{product.slug}/{n}.png",
        checksum=hashlib.sha256(payload).hexdigest(),
    )
    image.image.save(f"products/{product.pk}/{n}.png", ContentFile(payload), save=True)
    return image


def _product(slug="p1"):
    cat = Category.add_root(name=f"Категория {slug}", slug=f"cat-{slug}")
    return Product.objects.create(
        category=cat, name="Товар", slug=slug, status=ProductStatus.IMPORTED, price="1000"
    )


def _run(image, **kw):
    status = image_autoprocess.process_image(image.pk, **kw)
    image.refresh_from_db()
    return status


# --- метрика разрыва ----------------------------------------------------------------


def _square_with(pieces: list[tuple[int, int, int, int]]) -> Image.Image:
    canvas = Image.new("RGB", (1200, 1200), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    for box in pieces:
        draw.rectangle(box, fill=(30, 30, 30))
    return canvas


def test_whole_product_is_one_piece():
    whole = _square_with([(200, 200, 1000, 1000)])
    assert image_processing.largest_piece_share(whole) == 1.0


def test_scattered_scraps_lower_the_share():
    scraps = _square_with(
        [(100, 100, 260, 260), (900, 120, 1060, 280), (120, 900, 280, 1060), (880, 880, 1040, 1040)]
    )
    assert image_processing.largest_piece_share(scraps) == pytest.approx(0.25, abs=0.05)
    assert image_processing.largest_piece_share(scraps) < image_processing.MIN_PIECE_SHARE


def test_thin_diagonal_link_keeps_product_whole():
    """Тонкая штанга триммера идёт по диагонали — куски по ней не считаем разными."""
    canvas = _square_with([(200, 200, 400, 400), (800, 800, 1000, 1000)])
    ImageDraw.Draw(canvas).line((400, 400, 800, 800), fill=(30, 30, 30), width=6)
    assert image_processing.largest_piece_share(canvas) == 1.0


def test_blank_square_has_no_pieces():
    assert image_processing.largest_piece_share(Image.new("RGB", (600, 600), (255, 255, 255))) == 0


# --- прочий фон не трогаем ------------------------------------------------------------


def test_scene_is_left_alone_without_copy(autoprocess_on):
    image = _photo(_product(), _scene())

    assert _run(image) == ImageProcessingStatus.SKIPPED
    assert not image.display
    assert image.review_reason == ""
    assert image.processing_mode == ""
    assert image.fingerprint  # отпечаток нужен: по нему ищутся повторы кадра
    assert _image_url(image) == image.image.url


def test_scene_is_not_queued_for_rembg(autoprocess_on):
    image = _photo(_product(), _scene())
    _run(image)
    assert image.processing_status != ImageProcessingStatus.NEEDS_REMBG


def test_rembg_only_takes_needs_rembg(autoprocess_on):
    """--rembg с другим статусом запрещён: иначе фото вернулось бы в «ждёт нейросеть»."""
    with pytest.raises(CommandError, match="needs_rembg"):
        call_command("process_product_images", "--rembg", "--status", "skipped")


def test_settled_scene_is_not_picked_up_again(autoprocess_on):
    image = _photo(_product(), _scene())
    _run(image)
    call_command("process_product_images")
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.SKIPPED


# --- разорванная вырезка --------------------------------------------------------------


def _torn_cut(img):
    """Так выглядит съеденная нейросетью карточка: обрывки букв по всему кадру."""
    cut = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(cut)
    for x in range(60, 700, 120):
        draw.rectangle((x, 100, x + 40, 160), fill=(20, 20, 20, 255))
        draw.rectangle((x, 380, x + 40, 440), fill=(20, 20, 20, 255))
    return cut


def _whole_cut(img):
    cut = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(cut).rectangle((150, 120, 650, 480), fill=(180, 30, 30, 255))
    return cut


def test_torn_cutout_goes_to_review(autoprocess_on, monkeypatch):
    monkeypatch.setattr(image_rembg, "is_available", lambda: True)
    monkeypatch.setattr(image_rembg, "cut_out", _torn_cut)
    image = _photo(_product(), _scene(bg=(0, 0, 0)))
    ProductImage.objects.filter(pk=image.pk).update(processing_status=ImageProcessingStatus.QUEUED)

    assert _run(image, rembg=True) == ImageProcessingStatus.NEEDS_REVIEW
    assert image.review_reason == ImageReviewReason.TORN
    assert image.candidate  # кандидат есть: менеджер решает сам
    assert not image.display
    assert _image_url(image) == image.image.url  # на витрине пока оригинал


def test_whole_cutout_goes_to_storefront(autoprocess_on, monkeypatch):
    monkeypatch.setattr(image_rembg, "is_available", lambda: True)
    monkeypatch.setattr(image_rembg, "cut_out", _whole_cut)
    image = _photo(_product(), _scene(bg=(0, 0, 0)))
    ProductImage.objects.filter(pk=image.pk).update(processing_status=ImageProcessingStatus.QUEUED)

    assert _run(image, rembg=True) == ImageProcessingStatus.DONE
    assert image.review_reason == ""
    assert _image_url(image) == image.display.url


def test_torn_beats_small_as_a_reason(autoprocess_on, monkeypatch):
    """У рвани уцелевший огрызок мелкий, но менеджеру важна причина поважнее."""

    def tiny_scraps(img):
        cut = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(cut)
        draw.rectangle((100, 100, 150, 130), fill=(20, 20, 20, 255))
        draw.rectangle((600, 450, 650, 480), fill=(20, 20, 20, 255))
        return cut

    monkeypatch.setattr(image_rembg, "is_available", lambda: True)
    monkeypatch.setattr(image_rembg, "cut_out", tiny_scraps)
    image = _photo(_product(), _scene(bg=(0, 0, 0)))
    ProductImage.objects.filter(pk=image.pk).update(processing_status=ImageProcessingStatus.QUEUED)

    assert _run(image, rembg=True) == ImageProcessingStatus.NEEDS_REVIEW
    assert image.review_reason == ImageReviewReason.TORN


# --- «вернуть оригинал» чистит вопросы к копии -----------------------------------------


def test_revert_clears_review_reason(autoprocess_on, monkeypatch):
    monkeypatch.setattr(image_rembg, "is_available", lambda: True)
    monkeypatch.setattr(image_rembg, "cut_out", _torn_cut)
    image = _photo(_product(), _scene(bg=(0, 0, 0)))
    ProductImage.objects.filter(pk=image.pk).update(processing_status=ImageProcessingStatus.QUEUED)
    _run(image, rembg=True)
    assert image.review_reason == ImageReviewReason.TORN

    assert image_autoprocess.revert_to_original(image.pk) is True
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.REJECTED
    assert image.review_reason == ""
    assert not image.display


def test_revert_keeps_duplicate_mark(autoprocess_on):
    """Повтор кадра — свойство оригинала: отметка переживает отказ от копии.

    Иначе запись вернулась бы в поиск дублей и на проверку уехал бы первый кадр.
    """
    product = _product()
    first = _photo(product, _scene(bg=(255, 255, 255)), n=1)
    second = _photo(product, _scene(bg=(255, 255, 255)).resize((1000, 750)), n=2)
    _run(first)
    _run(second)
    assert second.review_reason == ImageReviewReason.DUPLICATE

    image_autoprocess.revert_to_original(second.pk)
    second.refresh_from_db()
    assert second.review_reason == ImageReviewReason.DUPLICATE
    assert second.duplicate_of_id == first.pk
