"""ADR-0014: витринная копия фото рядом с неизменным оригиналом.

Проверяем контракт, на который опираются автообработка и контур обратимости
ИЗО-02: витрина берёт копию только в статусе done, снимок и аудит считают
копию своей, откат удаляет оба файла, а дедуп сбора держится на оригинале.
"""

from __future__ import annotations

import hashlib
import io

import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command
from PIL import Image

from apps.catalog.api.serializers import _image_url
from apps.catalog.image_pipeline import ImagePipeline
from apps.catalog.image_reversibility import (
    RollbackRefused,
    apply_rollback,
    audit,
    build_rollback_plan,
    build_snapshot,
)
from apps.catalog.models import (
    Category,
    ImageProcessingStatus,
    ImageSource,
    Product,
    ProductImage,
    ProductStatus,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _media(tmp_path, settings):
    """Своё MEDIA_ROOT на тест: сверка БД↔файлы не должна видеть чужие файлы."""
    settings.MEDIA_ROOT = tmp_path / "media"
    (tmp_path / "media" / "products").mkdir(parents=True)
    return settings.MEDIA_ROOT


def _png_bytes(color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (300, 300), color).save(buf, format="PNG")
    return buf.getvalue()


def _product(slug="p1"):
    cat = Category.add_root(name=f"Категория {slug}", slug=f"cat-{slug}")
    return Product.objects.create(
        category=cat,
        name="Товар",
        slug=slug,
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
    )


def _image(product, *, source=ImageSource.RESANTA, url="https://a.example/1.png"):
    payload = _png_bytes()
    image = ProductImage(
        product=product,
        source=source,
        source_url=url,
        checksum=hashlib.sha256(payload).hexdigest(),
    )
    image.image.save(f"products/{product.pk}/orig.png", ContentFile(payload), save=True)
    return image


def _add_display(image, *, status=ImageProcessingStatus.DONE, version=1, color=(255, 255, 255)):
    payload = _png_bytes(color)
    image.display.save(f"{image.pk}-v{version}.png", ContentFile(payload), save=False)
    image.display_checksum = hashlib.sha256(payload).hexdigest()
    image.processing_status = status
    image.processing_version = version
    image.save()
    return image


# --- хранение и витрина ------------------------------------------------------


def test_display_lives_in_separate_subtree_and_original_untouched():
    image = _image(_product())
    original_name, original_checksum = image.image.name, image.checksum
    _add_display(image)
    image.refresh_from_db()
    assert image.display.name.startswith(f"products/display/{image.product_id}/")
    assert (image.image.name, image.checksum) == (original_name, original_checksum)


@pytest.mark.parametrize(
    ("status", "shows_display"),
    [
        (ImageProcessingStatus.DONE, True),
        (ImageProcessingStatus.NONE, False),
        (ImageProcessingStatus.QUEUED, False),
        (ImageProcessingStatus.NEEDS_REMBG, False),
        (ImageProcessingStatus.NEEDS_REVIEW, False),
        (ImageProcessingStatus.REJECTED, False),
        (ImageProcessingStatus.FAILED, False),
    ],
)
def test_storefront_shows_display_only_when_done(status, shows_display):
    image = _add_display(_image(_product()), status=status)
    expected = image.display.url if shows_display else image.image.url
    assert _image_url(image) == expected


def test_storefront_falls_back_to_original_when_done_without_file():
    image = _image(_product())
    image.processing_status = ImageProcessingStatus.DONE
    image.save()
    assert _image_url(image) == image.image.url


# --- снимок и аудит ----------------------------------------------------------


def test_snapshot_treats_display_as_referenced_not_orphan():
    image = _add_display(_image(_product()))
    snap = build_snapshot()
    assert snap["files_total"] == 2
    assert snap["orphan_files"] == []
    row = snap["records"][0]
    assert row["file"] == image.image.name  # старые ключи на месте
    assert row["display_file"] == image.display.name
    assert row["display_file_checksum"] == row["display_db_checksum"] == image.display_checksum


def test_audit_clean_with_display():
    _add_display(_image(_product()))
    report = audit()
    assert report["orphan_files_total"] == 0
    assert report["checksum_mismatch_total"] == 0
    assert report["missing_display_file_total"] == 0
    assert report["display_checksum_mismatch_total"] == 0


def test_audit_reports_display_drift_and_missing(_media):
    drifted = _add_display(_image(_product("p1")))
    gone = _add_display(_image(_product("p2")))
    (_media / drifted.display.name).write_bytes(b"other bytes")
    (_media / gone.display.name).unlink()

    report = audit()
    assert [r["id"] for r in report["display_checksum_mismatch"]] == [drifted.pk]
    assert [r["id"] for r in report["missing_display_file"]] == [gone.pk]
    # оригиналы не пострадали — их счётчики чистые
    assert report["checksum_mismatch_total"] == 0
    assert report["missing_file_total"] == 0


# --- откат -------------------------------------------------------------------


def test_rollback_removes_original_and_display(_media):
    image = _add_display(_image(_product()))
    original, display = _media / image.image.name, _media / image.display.name

    plan = build_rollback_plan(source=ImageSource.RESANTA)
    assert plan["files_to_delete"] == 2
    assert plan["display_files_to_delete"] == 1

    result = apply_rollback(plan)
    assert result["files_deleted"] == 2
    assert result["display_files_deleted"] == 1
    assert not original.exists() and not display.exists()
    assert audit()["orphan_files_total"] == 0


def test_rollback_conflict_when_display_replaced_after_plan():
    image = _add_display(_image(_product()))
    plan = build_rollback_plan(source=ImageSource.RESANTA)
    _add_display(image, version=2)  # обработка успела пересоздать копию
    with pytest.raises(RollbackRefused):
        apply_rollback(plan)
    assert ProductImage.objects.filter(pk=image.pk).exists()


def test_rollback_plan_from_before_adr_still_removes_display(_media):
    """План, снятый до ADR-0014, ключей копии не знает — откат всё равно чистит её."""
    image = _add_display(_image(_product()))
    display = _media / image.display.name
    plan = build_rollback_plan(source=ImageSource.RESANTA)
    for target in plan["targets"]:
        for key in [k for k in target if k.startswith("display_") or k == "processing_status"]:
            del target[key]

    apply_rollback(plan)
    assert not display.exists()


# --- дедуп сбора не зависит от копии -------------------------------------------


def test_collector_dedup_holds_after_display_added(monkeypatch):
    product = _product()
    pipe = ImagePipeline(throttle_interval=0)
    payload = _png_bytes()
    monkeypatch.setattr(pipe, "_download", lambda url: payload)

    first = pipe.process_url(product, "https://a.example/1.png", source=ImageSource.RESANTA)
    _add_display(first)

    same_url = pipe.process_url(product, "https://a.example/1.png", source=ImageSource.RESANTA)
    same_bytes = pipe.process_url(product, "https://cdn.example/1.png", source=ImageSource.RESANTA)
    assert same_url.pk == same_bytes.pk == first.pk
    assert product.images.count() == 1


# --- check_product_images ------------------------------------------------------


def test_check_product_images_reports_broken_display_without_touching_record(_media, capsys):
    image = _add_display(_image(_product()))
    (_media / image.display.name).write_bytes(b"not an image")

    call_command("check_product_images", "--list")
    out = capsys.readouterr().out
    assert "КОПИЯ ПОВРЕЖДЕНА" in out
    assert "Повреждённых:   0" in out  # оригинал цел
    assert ProductImage.objects.filter(pk=image.pk).exists()


# --- замена оригинала сбрасывает копию -------------------------------------------


def test_replacing_original_drops_display(_media, django_capture_on_commit_callbacks):
    image = _add_display(_image(_product()))
    old_display = _media / image.display.name
    image = ProductImage.objects.get(pk=image.pk)

    with django_capture_on_commit_callbacks(execute=True):
        image.image.save("new.png", ContentFile(_png_bytes((0, 0, 255))), save=True)

    image.refresh_from_db()
    assert not image.display
    assert image.display_checksum == ""
    assert image.processing_status == ImageProcessingStatus.NONE
    assert image.processing_version == 0
    assert _image_url(image) == image.image.url
    assert not old_display.exists()


def test_replacing_original_via_update_fields_drops_display(django_capture_on_commit_callbacks):
    image = ProductImage.objects.get(pk=_add_display(_image(_product())).pk)
    image.image = "products/other.png"
    with django_capture_on_commit_callbacks(execute=True):
        image.save(update_fields=["image"])
    image.refresh_from_db()
    assert not image.display
    assert image.processing_status == ImageProcessingStatus.NONE


def test_saving_other_fields_keeps_display():
    image = ProductImage.objects.get(pk=_add_display(_image(_product())).pk)
    image.alt = "Перфоратор"
    image.save()
    image.refresh_from_db()
    assert image.display
    assert image.processing_status == ImageProcessingStatus.DONE


def test_display_path_requires_product():
    from apps.catalog.models import product_image_display_path

    with pytest.raises(ValueError):
        product_image_display_path(ProductImage(), "x.webp")


# --- граничные случаи отката и аудита -------------------------------------------


def test_rollback_conflict_when_display_appeared_after_plan():
    image = _image(_product())
    plan = build_rollback_plan(source=ImageSource.RESANTA)
    _add_display(image)
    with pytest.raises(RollbackRefused):
        apply_rollback(plan)


def test_rollback_conflict_when_display_cleared_after_plan():
    image = _add_display(_image(_product()))
    plan = build_rollback_plan(source=ImageSource.RESANTA)
    image.display = ""
    image.processing_status = ImageProcessingStatus.REJECTED
    image.save()
    with pytest.raises(RollbackRefused):
        apply_rollback(plan)


def test_rollback_counts_missing_display_file(_media):
    image = _add_display(_image(_product()))
    (_media / image.display.name).unlink()

    plan = build_rollback_plan(source=ImageSource.RESANTA)
    assert plan["files_to_delete"] == 1
    assert plan["display_files_missing"] == 1

    result = apply_rollback(plan)
    assert result["files_deleted"] == 1
    assert result["files_absent"] == 1
    assert result["display_files_deleted"] == 0


def test_audit_flags_display_without_checksum():
    image = _add_display(_image(_product()))
    image.display_checksum = ""
    image.save()
    assert [r["id"] for r in audit()["display_checksum_mismatch"]] == [image.pk]


# --- check_product_images: удаляются только битые оригиналы -----------------------


def test_check_product_images_reports_missing_display(_media, capsys):
    image = _add_display(_image(_product()))
    (_media / image.display.name).unlink()
    call_command("check_product_images", "--list")
    assert "НЕТ КОПИИ" in capsys.readouterr().out


def test_delete_broken_keeps_record_with_only_broken_display(_media, monkeypatch):
    display_broken = _add_display(_image(_product("p1")))
    (_media / display_broken.display.name).write_bytes(b"not an image")
    original_broken = _image(_product("p2"), url="https://a.example/2.png")
    (_media / original_broken.image.name).write_bytes(b"not an image")

    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    call_command("check_product_images", "--delete-broken")

    assert ProductImage.objects.filter(pk=display_broken.pk).exists()
    assert not ProductImage.objects.filter(pk=original_broken.pk).exists()
