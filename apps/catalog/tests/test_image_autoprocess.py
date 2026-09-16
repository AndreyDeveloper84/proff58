"""Автообработка фото без нейросети (ADR-0014): байты → витринная копия → запуск.

Три уровня: чистая обработка картинки (`image_processing`), запись копии в
`ProductImage` с требованиями ADR-0014 (`image_autoprocess`) и то, как это
запускается — сигнал, задача, очередь, команда бэкфилла.
"""

from __future__ import annotations

import hashlib
import io

import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from PIL import Image, ImageChops

from apps.catalog import image_autoprocess, image_processing
from apps.catalog.api.serializers import _image_url
from apps.catalog.image_processing import ImageKind, UnreadableImage
from apps.catalog.models import (
    Category,
    ImageProcessingMode,
    ImageProcessingStatus,
    ImageSource,
    Product,
    ProductImage,
    ProductStatus,
)
from apps.catalog.tasks import process_product_image


@pytest.fixture(autouse=True)
def _media(tmp_path, settings):
    """Своё MEDIA_ROOT на тест: копии пишутся в реальные файлы."""
    settings.MEDIA_ROOT = tmp_path / "media"
    (tmp_path / "media" / "products").mkdir(parents=True)
    return settings.MEDIA_ROOT


@pytest.fixture
def autoprocess_on(settings):
    settings.FEATURES = {**settings.FEATURES, image_autoprocess.FLAG: True}


def _encode(img, fmt="PNG"):
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _scene(bg=(255, 255, 255), size=(800, 600), box=(100, 150, 300, 250), color=(200, 30, 30)):
    """Товар-прямоугольник `box` на однотонном фоне."""
    img = Image.new("RGB", size, bg)
    img.paste(color, box)
    return img


def _transparent(size=(400, 300), box=(50, 50, 150, 120)):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    img.paste((200, 30, 30, 255), box)
    return img


def _content_bbox(webp: bytes):
    """Рамка всего, что заметно отличается от белого."""
    img = Image.open(io.BytesIO(webp)).convert("RGB")
    diff = ImageChops.difference(img, Image.new("RGB", img.size, (255, 255, 255))).convert("L")
    return img.size, diff.point(lambda v: 255 if v > 40 else 0).getbbox()


# --- обработка байтов -------------------------------------------------------------


@pytest.mark.parametrize(
    ("img", "kind"),
    [
        (_scene(), ImageKind.WHITE),
        (_scene(bg=(0, 0, 0)), ImageKind.BLACK),
        (_scene(bg=(128, 128, 128)), ImageKind.OTHER),
        (Image.linear_gradient("L").convert("RGB").resize((600, 600)), ImageKind.OTHER),
        (_transparent(), ImageKind.ALPHA),
        (_scene().convert("RGBA"), ImageKind.WHITE),  # альфа-канал есть, но всё непрозрачно
    ],
    ids=["white", "black", "gray", "gradient", "alpha", "opaque-rgba"],
)
def test_classify_by_frame_border(img, kind):
    assert image_processing.classify(image_processing.open_image(_encode(img))) == kind


def test_white_background_trimmed_and_centered_in_square():
    # товар 600×300: вписывается увеличением ×1,72 — меньше предела MAX_UPSCALE
    result = image_processing.process(_encode(_scene(size=(1400, 1000), box=(200, 300, 800, 600))))
    size, (left, top, right, bottom) = _content_bbox(result.content)

    assert result.kind == ImageKind.WHITE
    assert size == (image_processing.CANVAS, image_processing.CANVAS)
    inner = round(image_processing.CANVAS * (1 - 2 * image_processing.MARGIN))
    assert abs((right - left) - inner) <= 4  # длинная сторона заполняет квадрат без полей
    assert abs(left - (image_processing.CANVAS - right)) <= 3  # по центру по горизонтали
    assert abs(top - (image_processing.CANVAS - bottom)) <= 3  # и по вертикали


def test_small_product_is_not_upscaled_beyond_limit():
    result = image_processing.process(_encode(_scene(box=(100, 100, 140, 120))))  # 40×20
    _size, (left, _top, right, _bottom) = _content_bbox(result.content)
    assert abs((right - left) - 40 * image_processing.MAX_UPSCALE) <= 3


def test_transparent_background_becomes_white():
    result = image_processing.process(_encode(_transparent()))
    img = Image.open(io.BytesIO(result.content)).convert("RGB")
    assert result.kind == ImageKind.ALPHA
    assert all(c >= 245 for c in img.getpixel((5, 5)))


@pytest.mark.parametrize("bg", [(0, 0, 0), (128, 128, 128)], ids=["black", "gray"])
def test_black_and_other_backgrounds_wait_for_rembg(bg):
    assert image_processing.process(_encode(_scene(bg=bg))).content is None


def test_cmyk_jpeg_is_processed():
    cmyk = Image.new("CMYK", (500, 400), (0, 0, 0, 0))
    cmyk.paste((0, 200, 200, 0), (100, 100, 200, 200))
    assert image_processing.process(_encode(cmyk, "JPEG")).content is not None


def test_unreadable_bytes_rejected():
    with pytest.raises(UnreadableImage):
        image_processing.process(b"not an image")


def test_decompression_bomb_rejected(monkeypatch):
    monkeypatch.setattr(image_processing, "MAX_PIXELS", 1000)
    with pytest.raises(UnreadableImage):
        image_processing.process(_encode(_scene()))


# --- запись копии -------------------------------------------------------------


def _product(slug="p1", **kw):
    cat = Category.add_root(name=f"Категория {slug}", slug=f"cat-{slug}")
    return Product.objects.create(
        category=cat,
        name="Товар",
        slug=slug,
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
        **kw,
    )


def _photo(product, img=None, *, url="https://a.example/1.png"):
    payload = _encode(img or _scene())
    image = ProductImage(
        product=product,
        source=ImageSource.RESANTA,
        source_url=url,
        checksum=hashlib.sha256(payload).hexdigest(),
    )
    image.image.save(f"products/{product.pk}/orig.png", ContentFile(payload), save=True)
    return image


def _display_files(media):
    root = media / "products" / "display"
    return sorted(p.name for p in root.rglob("*") if p.is_file()) if root.exists() else []


@pytest.mark.django_db
def test_disabled_flag_changes_nothing():
    image = _photo(_product())
    assert image_autoprocess.process_image(image.pk) == "disabled"
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.NONE and not image.display


@pytest.mark.django_db
def test_white_photo_gets_display_and_original_untouched(autoprocess_on, _media):
    image = _photo(_product())
    original = (image.image.name, image.checksum, (_media / image.image.name).read_bytes())

    assert image_autoprocess.process_image(image.pk) == ImageProcessingStatus.DONE
    image.refresh_from_db()

    version = image_processing.PROCESSING_VERSION
    assert image.display.name.startswith(f"products/display/{image.product_id}/")
    assert image.display.name.endswith(f"-v{version}.webp")
    display_bytes = (_media / image.display.name).read_bytes()
    assert image.display_checksum == hashlib.sha256(display_bytes).hexdigest()
    assert image.processing_mode == ImageProcessingMode.TRIM
    assert image.processing_version == version
    assert image.processed_at is not None
    assert original == (
        image.image.name,
        image.checksum,
        (_media / image.image.name).read_bytes(),
    )
    assert _image_url(image) == image.display.url


@pytest.mark.django_db
def test_black_photo_waits_for_rembg(autoprocess_on, _media):
    image = _photo(_product(), _scene(bg=(0, 0, 0)))
    assert image_autoprocess.process_image(image.pk) == ImageProcessingStatus.NEEDS_REMBG
    image.refresh_from_db()
    assert not image.display
    assert _display_files(_media) == []


@pytest.mark.django_db
def test_second_run_is_noop(autoprocess_on, _media):
    image = _photo(_product())
    image_autoprocess.process_image(image.pk)
    assert image_autoprocess.process_image(image.pk) == "up_to_date"
    assert len(_display_files(_media)) == 1


@pytest.mark.django_db
def test_rejected_and_locked_are_left_alone(autoprocess_on):
    rejected = _photo(_product("p1"))
    ProductImage.objects.filter(pk=rejected.pk).update(
        processing_status=ImageProcessingStatus.REJECTED
    )
    locked = _photo(_product("p2", content_locked=True))

    assert image_autoprocess.process_image(rejected.pk) == "rejected"
    assert image_autoprocess.process_image(locked.pk) == "content_locked"


@pytest.mark.django_db
def test_missing_original_marks_failed(autoprocess_on, _media):
    image = _photo(_product())
    (_media / image.image.name).unlink()
    assert image_autoprocess.process_image(image.pk) == ImageProcessingStatus.FAILED


@pytest.mark.django_db
def test_photo_replaced_during_processing_is_not_overwritten(autoprocess_on, _media, monkeypatch):
    image = _photo(_product())
    real_process = image_processing.process

    def replace_then_process(raw):
        ProductImage.objects.filter(pk=image.pk).update(image="products/replaced.png")
        return real_process(raw)

    monkeypatch.setattr(image_processing, "process", replace_then_process)
    assert image_autoprocess.process_image(image.pk) == "stale"
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.NONE and not image.display
    assert _display_files(_media) == []  # свой файл убран


@pytest.mark.django_db
def test_photo_deleted_during_processing_is_not_resurrected(autoprocess_on, _media, monkeypatch):
    image = _photo(_product())
    real_process = image_processing.process

    def delete_then_process(raw):
        ProductImage.objects.filter(pk=image.pk).delete()
        return real_process(raw)

    monkeypatch.setattr(image_processing, "process", delete_then_process)
    assert image_autoprocess.process_image(image.pk) == "stale"
    assert not ProductImage.objects.filter(pk=image.pk).exists()
    assert _display_files(_media) == []


@pytest.mark.django_db
def test_new_parameters_version_replaces_copy(
    autoprocess_on, _media, monkeypatch, django_capture_on_commit_callbacks
):
    image = _photo(_product())
    image_autoprocess.process_image(image.pk)
    image.refresh_from_db()
    old = _media / image.display.name

    monkeypatch.setattr(image_processing, "PROCESSING_VERSION", 2)
    with django_capture_on_commit_callbacks(execute=True):
        assert image_autoprocess.process_image(image.pk) == ImageProcessingStatus.DONE
    image.refresh_from_db()
    assert image.display.name.endswith("-v2.webp")
    assert not old.exists()


# --- запуск: сигнал, задача, очередь ---------------------------------------------


@pytest.mark.django_db
def test_new_photo_processed_after_commit(autoprocess_on, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        image = _photo(_product())
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.DONE  # dev: Celery eager


@pytest.fixture
def scheduled(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(
        image_autoprocess, "schedule", lambda image_id, **kw: calls.append(image_id)
    )
    return calls


@pytest.mark.django_db
def test_editing_alt_does_not_enqueue(autoprocess_on, scheduled):
    image = _photo(_product())
    scheduled.clear()
    image = ProductImage.objects.get(pk=image.pk)
    image.alt = "Перфоратор"
    image.save()
    assert scheduled == []


@pytest.mark.django_db
def test_replacing_file_enqueues(autoprocess_on, scheduled):
    image = ProductImage.objects.get(pk=_photo(_product()).pk)
    scheduled.clear()
    image.image.save("new.png", ContentFile(_encode(_scene(color=(0, 0, 255)))), save=True)
    assert scheduled == [image.pk]


@pytest.mark.django_db
def test_flag_off_does_not_enqueue(scheduled):
    _photo(_product())
    assert scheduled == []


def test_task_is_routed_to_images_queue(settings):
    assert process_product_image.name == "apps.catalog.tasks.process_product_image"
    assert settings.CELERY_TASK_ROUTES[process_product_image.name] == {"queue": "images"}


# --- команда бэкфилла ------------------------------------------------------------


@pytest.mark.django_db
def test_dry_run_counts_and_writes_nothing(_media, capsys, tmp_path):
    _photo(_product("p1"))
    _photo(_product("p2"), _scene(bg=(0, 0, 0)))
    out = tmp_path / "report.json"

    call_command("process_product_images", "--dry-run", "--out", str(out))

    text = capsys.readouterr().out
    assert "белый фон (обработается сразу)" in text and "чёрный фон (ждёт нейросеть)" in text
    assert out.exists()
    assert not ProductImage.objects.exclude(processing_status=ImageProcessingStatus.NONE).exists()
    assert _display_files(_media) == []


@pytest.mark.django_db
def test_command_refuses_when_disabled():
    _photo(_product())
    with pytest.raises(CommandError):
        call_command("process_product_images")


@pytest.mark.django_db
def test_command_enqueues_and_eager_worker_processes(
    autoprocess_on, django_capture_on_commit_callbacks
):
    image = _photo(_product())
    with django_capture_on_commit_callbacks(execute=True):
        call_command("process_product_images")
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.DONE


@pytest.mark.django_db
def test_command_outdated_rebuilds_old_version(
    autoprocess_on, monkeypatch, django_capture_on_commit_callbacks
):
    image = _photo(_product())
    image_autoprocess.process_image(image.pk)
    monkeypatch.setattr(image_processing, "PROCESSING_VERSION", 2)

    with django_capture_on_commit_callbacks(execute=True):
        call_command("process_product_images")  # без --outdated готовые не трогаем
    image.refresh_from_db()
    assert image.processing_version == 1

    with django_capture_on_commit_callbacks(execute=True):
        call_command("process_product_images", "--outdated")
    image.refresh_from_db()
    assert image.processing_version == 2


@pytest.mark.django_db
def test_command_never_overrides_manager_rejection(autoprocess_on):
    image = _photo(_product())
    ProductImage.objects.filter(pk=image.pk).update(
        processing_status=ImageProcessingStatus.REJECTED
    )
    with pytest.raises(CommandError):
        call_command("process_product_images", "--status", "rejected")
    call_command("process_product_images", "--status", "none", "--outdated")
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.REJECTED


# --- замечания ревью: граничные случаи ---------------------------------------------


def test_gray_floor_with_three_white_sides_is_not_white():
    img = Image.new("RGB", (800, 600), (255, 255, 255))
    img.paste((235, 235, 235), (0, 540, 800, 600))  # однотонный серый пол
    img.paste((200, 30, 30), (300, 200, 500, 400))
    assert image_processing.classify(image_processing.open_image(_encode(img))) == ImageKind.OTHER


def test_opaque_dark_background_with_one_translucent_pixel_is_not_alpha():
    img = Image.new("RGBA", (400, 300), (0, 0, 0, 255))
    img.paste((200, 30, 30, 255), (100, 100, 200, 200))
    img.putpixel((150, 150), (200, 30, 30, 254))
    assert image_processing.classify(image_processing.open_image(_encode(img))) == ImageKind.BLACK


@pytest.mark.parametrize("mode", ["P", "LA"])
def test_palette_and_gray_transparency_count_as_alpha(mode):
    if mode == "P":
        img = Image.new("P", (400, 300), 0)
        img.putpalette([0, 0, 0, 200, 30, 30])
        img.paste(1, (100, 100, 200, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG", transparency=0)
        raw = buf.getvalue()
    else:
        img = Image.new("LA", (400, 300), (0, 0))
        img.paste((90, 255), (100, 100, 200, 200))
        raw = _encode(img)
    result = image_processing.process(raw)
    assert result.kind == ImageKind.ALPHA and result.content is not None


def test_16bit_grayscale_is_not_turned_into_blank_square():
    # до исправления convert("RGB") обрезал всё выше 255 — и фон, и товар становились белыми
    img = Image.new("I;16", (400, 300), 65535)
    img.paste(15000, (100, 100, 300, 200))
    result = image_processing.process(_encode(img))
    assert result.kind == ImageKind.WHITE
    assert result.content is not None
    size, bbox = _content_bbox(result.content)
    assert bbox is not None  # товар виден, а не белый квадрат


def test_all_white_picture_needs_review_not_storefront():
    result = image_processing.process(_encode(Image.new("RGB", (500, 500), (255, 255, 255))))
    assert (result.kind, result.content) == (ImageKind.BLANK, None)


@pytest.mark.django_db
def test_blank_photo_goes_to_review(autoprocess_on):
    image = _photo(_product(), Image.new("RGB", (500, 500), (255, 255, 255)))
    assert image_autoprocess.process_image(image.pk) == ImageProcessingStatus.NEEDS_REVIEW


@pytest.mark.django_db
def test_unexpected_error_marks_failed(autoprocess_on, monkeypatch):
    image = _photo(_product())

    def boom(raw):
        raise RuntimeError("сбой")

    monkeypatch.setattr(image_processing, "process", boom)
    assert image_autoprocess.process_image(image.pk) == ImageProcessingStatus.FAILED
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.FAILED


@pytest.mark.django_db
def test_failure_while_rebuilding_keeps_existing_copy(autoprocess_on, _media, monkeypatch):
    image = _photo(_product())
    image_autoprocess.process_image(image.pk)
    image.refresh_from_db()
    copy = _media / image.display.name

    monkeypatch.setattr(image_processing, "PROCESSING_VERSION", 2)
    ProductImage.objects.filter(pk=image.pk).update(processing_status=ImageProcessingStatus.QUEUED)
    (_media / image.image.name).unlink()  # временный сбой чтения исходника

    assert image_autoprocess.process_image(image.pk) == ImageProcessingStatus.FAILED
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.DONE
    assert image.display and copy.exists()
    assert _image_url(image) == image.display.url


@pytest.mark.django_db
@pytest.mark.parametrize("reason", ["disabled", "content_locked"])
def test_early_exit_releases_queued_status(settings, reason):
    locked = reason == "content_locked"
    if locked:
        settings.FEATURES = {**settings.FEATURES, image_autoprocess.FLAG: True}
    image = _photo(_product(content_locked=locked))
    ProductImage.objects.filter(pk=image.pk).update(processing_status=ImageProcessingStatus.QUEUED)

    assert image_autoprocess.process_image(image.pk) == reason
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.NONE


@pytest.mark.django_db
def test_signal_skips_locked_product(autoprocess_on, scheduled):
    _photo(_product(content_locked=True))
    assert scheduled == []


@pytest.mark.django_db
def test_copy_from_older_version_does_not_overwrite_newer(autoprocess_on, _media):
    image = _photo(_product())
    ProductImage.objects.filter(pk=image.pk).update(processing_version=99)
    assert image_autoprocess.process_image(image.pk) == "stale"
    assert _display_files(_media) == []


@pytest.mark.django_db
def test_rejection_during_processing_wins(autoprocess_on, _media, monkeypatch):
    image = _photo(_product())
    real_process = image_processing.process

    def reject_then_process(raw):
        ProductImage.objects.filter(pk=image.pk).update(
            processing_status=ImageProcessingStatus.REJECTED
        )
        return real_process(raw)

    monkeypatch.setattr(image_processing, "process", reject_then_process)
    assert image_autoprocess.process_image(image.pk) == "stale"
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.REJECTED
    assert _display_files(_media) == []


@pytest.mark.django_db
def test_broker_failure_restores_status_and_is_reported(autoprocess_on, monkeypatch, capsys):
    image = _photo(_product())

    def broker_down(*args, **kwargs):
        raise ConnectionError("redis недоступен")

    monkeypatch.setattr(process_product_image, "delay", broker_down)
    assert image_autoprocess.enqueue(image.pk) is False
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.NONE

    call_command("process_product_images")
    assert "Не поставлено: 1" in capsys.readouterr().out


def test_task_survives_worker_kill():
    assert process_product_image.acks_late is True
    assert process_product_image.reject_on_worker_lost is True


@pytest.mark.django_db
def test_command_source_and_limit(autoprocess_on, django_capture_on_commit_callbacks):
    first = _photo(_product("p1"))
    second = _photo(_product("p2"), url="https://a.example/2.png")
    ProductImage.objects.filter(pk=second.pk).update(source=ImageSource.VIHR)
    third = _photo(_product("p3"), url="https://a.example/3.png")

    call_command("process_product_images", "--source", ImageSource.VIHR)
    call_command("process_product_images", "--source", ImageSource.RESANTA, "--limit", "1")

    statuses = dict(ProductImage.objects.values_list("pk", "processing_status"))
    assert statuses[second.pk] == ImageProcessingStatus.DONE
    assert statuses[first.pk] == ImageProcessingStatus.DONE
    assert statuses[third.pk] == ImageProcessingStatus.NONE
