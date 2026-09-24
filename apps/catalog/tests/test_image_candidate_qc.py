"""Доработка контролёра качества фото: то, чего не было в исходном ADR-0014.

Кандидат отдельно от принятой копии, архив отклонённых, применение по манифесту
и откат прогона обработки (не сбора), точечные действия человека (главное фото,
назначение кадра, ручной rembg). Обычная обрезка/классификация/rembg-контракт —
в test_image_autoprocess.py, test_image_quality.py, test_image_scenes.py,
test_image_rembg.py — эти файлы уже обновлены под новую модель полей.
"""

from __future__ import annotations

import hashlib
import io
import json

import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from PIL import Image

from apps.catalog import image_autoprocess
from apps.catalog.models import (
    Category,
    ImageProcessingStatus,
    ImagePurpose,
    ImageSource,
    Product,
    ProductImage,
    ProductImageEvent,
    ProductStatus,
    RejectedImageCandidate,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private_media"
    (tmp_path / "media" / "products").mkdir(parents=True)
    return settings.MEDIA_ROOT


@pytest.fixture
def autoprocess_on(settings):
    settings.FEATURES = {**settings.FEATURES, image_autoprocess.FLAG: True}
    settings.PRODUCT_IMAGE_AUTO_ACCEPT_ROUTES = {"trim", "rembg_black"}


def _shot(size=(800, 600), box=(100, 150, 700, 450), color=(200, 30, 30), bg=(255, 255, 255)):
    img = Image.new("RGB", size, bg)
    img.paste(color, box)
    return img


def _small_shot():
    return _shot(box=(370, 280, 430, 320))  # товар меньше половины квадрата


def _product(slug="p1", *, content_locked=False):
    cat = Category.add_root(name=f"Категория {slug}", slug=f"cat-{slug}")
    return Product.objects.create(
        category=cat,
        name="Перфоратор",
        slug=slug,
        status=ProductStatus.IMPORTED,
        price="1000",
        content_locked=content_locked,
    )


def _photo(product, img=None, *, url=None):
    img = img or _shot()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    payload = buf.getvalue()
    image = ProductImage(
        product=product,
        source=ImageSource.RESANTA,
        source_url=url
        or f"https://a.example/{product.pk}-{hashlib.sha1(payload).hexdigest()[:8]}.png",
        checksum=hashlib.sha256(payload).hexdigest(),
    )
    image.image.save(f"products/{product.pk}/orig.png", ContentFile(payload), save=True)
    return image


def _run(image, **kw):
    status = image_autoprocess.process_image(image.pk, **kw)
    image.refresh_from_db()
    return status


# --- архив отклонённых кандидатов (§7.1) ----------------------------------------


def test_reject_candidate_archives_bytes_and_is_idempotent_on_repeat(autoprocess_on):
    image = _photo(_product(), _small_shot())
    assert _run(image) == ImageProcessingStatus.NEEDS_REVIEW
    checksum, revision = image.candidate_checksum, image.revision

    ok = image_autoprocess.reject_candidate(
        image.pk, expected_checksum=checksum, expected_revision=revision, reason_text="мелкое"
    )
    assert ok is True
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.CANDIDATE_REJECTED
    assert not image.candidate
    assert not image.display  # витрина не менялась ни на каком шаге

    archived = RejectedImageCandidate.objects.get(image_ref=image.pk)
    assert archived.checksum == checksum
    assert archived.product_snapshot["product_id"] == image.product_id
    assert archived.file.read()  # байты реально сохранены, не только статус

    # Повтор обработки того же исходника с теми же параметрами — тот же кандидат;
    # повторное отклонение не плодит вторую запись архива (§7.1).
    assert image_autoprocess.reprocess(image.pk) is True
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.NEEDS_REVIEW
    assert image.candidate_checksum == checksum  # тот же render_key → тот же файл
    ok2 = image_autoprocess.reject_candidate(
        image.pk, expected_checksum=image.candidate_checksum, expected_revision=image.revision
    )
    assert ok2 is True
    assert RejectedImageCandidate.objects.filter(image_ref=image.pk).count() == 1


def test_revert_to_original_archives_pending_candidate(autoprocess_on):
    """«Оставить оригинал» при ожидающем кандидате — это тоже его отклонение,
    просто с другим итоговым статусом записи (REJECTED, не CANDIDATE_REJECTED)."""
    image = _photo(_product(), _small_shot())
    assert _run(image) == ImageProcessingStatus.NEEDS_REVIEW
    candidate_checksum = image.candidate_checksum

    assert image_autoprocess.revert_to_original(image.pk) is True
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.REJECTED
    assert not image.candidate and not image.display
    assert RejectedImageCandidate.objects.filter(
        image_ref=image.pk, checksum=candidate_checksum
    ).exists()


def test_empty_result_auto_rejected_without_archive_entry(autoprocess_on):
    """Пустой результат — байтов нет, значит и архивной записи нет (§7.1: сбой до
    создания файла не изображается сохранённым фото)."""
    image = _photo(_product(), Image.new("RGB", (400, 400), (255, 255, 255)))
    assert _run(image) == ImageProcessingStatus.CANDIDATE_REJECTED
    assert RejectedImageCandidate.objects.filter(image_ref=image.pk).count() == 0


def test_archive_survives_image_deletion(autoprocess_on):
    image = _photo(_product(), _small_shot())
    _run(image)
    image_autoprocess.reject_candidate(
        image.pk, expected_checksum=image.candidate_checksum, expected_revision=image.revision
    )
    archived = RejectedImageCandidate.objects.get(image_ref=image.pk)
    product_id = image.product_id

    image.delete()

    archived.refresh_from_db()
    assert archived.image_id is None  # SET_NULL, а не каскадное удаление
    assert archived.product_ref == product_id
    assert archived.file.storage.exists(archived.file.name)


def test_rejected_file_hidden_from_anonymous_visible_to_staff(client, admin_client, autoprocess_on):
    image = _photo(_product(), _small_shot())
    _run(image)
    image_autoprocess.reject_candidate(
        image.pk, expected_checksum=image.candidate_checksum, expected_revision=image.revision
    )
    archived = RejectedImageCandidate.objects.get(image_ref=image.pk)
    url = reverse("admin:catalog_rejectedimagecandidate_file", args=[archived.pk])

    anon = client.get(url)
    assert anon.status_code in (302, 403)  # редирект на логин или отказ, не байты файла

    staff = admin_client.get(url)
    assert staff.status_code == 200
    assert staff["Content-Type"] == "image/webp"
    assert staff["X-Content-Type-Options"] == "nosniff"


def test_return_to_review_refuses_if_source_changed(autoprocess_on):
    image = _photo(_product(), _small_shot())
    _run(image)
    image_autoprocess.reject_candidate(
        image.pk, expected_checksum=image.candidate_checksum, expected_revision=image.revision
    )
    archived = RejectedImageCandidate.objects.get(image_ref=image.pk)

    # Исходник заменили — архивный файл относится уже к другому кадру.
    image.image.save("products/x/new.png", ContentFile(_photo_bytes()), save=True)
    assert image_autoprocess.return_candidate_to_review(archived.pk) is False


def _photo_bytes():
    buf = io.BytesIO()
    _shot(color=(10, 200, 10)).save(buf, format="PNG")
    return buf.getvalue()


def test_return_to_review_then_accept_publishes(autoprocess_on):
    image = _photo(_product(), _small_shot())
    _run(image)
    image_autoprocess.reject_candidate(
        image.pk, expected_checksum=image.candidate_checksum, expected_revision=image.revision
    )
    archived = RejectedImageCandidate.objects.get(image_ref=image.pk)

    assert image_autoprocess.return_candidate_to_review(archived.pk) is True
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.NEEDS_REVIEW
    assert image.candidate_checksum == archived.checksum
    archived.refresh_from_db()
    assert archived.status == RejectedImageCandidate.Status.RETURNED

    accepted = image_autoprocess.accept_candidate(
        image.pk, expected_checksum=image.candidate_checksum, expected_revision=image.revision
    )
    assert accepted is True
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.DONE


# --- точечные действия человека -------------------------------------------------


def test_set_main_is_atomic_single_main_per_product(autoprocess_on):
    product = _product()
    first = _photo(product, _shot(color=(200, 30, 30)))
    second = _photo(product, _shot(color=(30, 30, 200)), url="https://a.example/2.png")
    ProductImage.objects.filter(pk=first.pk).update(is_main=True)

    assert image_autoprocess.set_main(second.pk) is True
    assert list(
        ProductImage.objects.filter(product=product, is_main=True).values_list("pk", flat=True)
    ) == [second.pk]
    assert ProductImageEvent.objects.filter(
        image_ref=second.pk, kind=ProductImageEvent.Kind.SET_MAIN
    ).exists()


def test_request_manual_rembg_refused_for_protected_purpose(autoprocess_on):
    image = _photo(_product(), _shot(bg=bg_gray()))
    _run(image)
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.SKIPPED  # прочий фон

    image_autoprocess.set_purpose(image.pk, ImagePurpose.PROMO)
    result = image_autoprocess.request_manual_rembg(image.pk)
    assert result == "protected_purpose"
    image.refresh_from_db()
    assert image.manual_rembg_requested is False


def test_request_manual_rembg_ok_for_unprotected_purpose_is_never_auto_accepted(
    autoprocess_on, monkeypatch
):
    from apps.catalog import image_rembg

    def _fake_cutout(img):
        w, h = img.size
        rgba = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        rgba.paste((200, 30, 30, 255), (w // 4, h // 4, 3 * w // 4, 3 * h // 4))
        return rgba

    monkeypatch.setattr(image_rembg, "is_available", lambda: True)
    monkeypatch.setattr(image_rembg, "cut_out", _fake_cutout)

    image = _photo(_product(), _shot(bg=bg_gray()))
    _run(image)
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.SKIPPED

    assert image_autoprocess.request_manual_rembg(image.pk) == "ok"
    image.refresh_from_db()
    # Celery в dev/test — eager: enqueue() внутри request_manual_rembg уже
    # выполнил обработку синхронно к этому моменту.
    assert image.manual_rembg_requested is True
    # Маршрут rembg_manual не проверен на выборке — auto_accept сюда никогда не
    # приводит (decide() всегда добавляет unproven_route), даже если бы кадр был чист.
    assert image.processing_status == ImageProcessingStatus.NEEDS_REVIEW
    assert "unproven_route" in image.qc_reasons
    assert image.candidate  # кандидат есть — ждёт решения человека, не витрины


def bg_gray():
    return (128, 128, 128)


# --- применение по манифесту и откат прогона обработки --------------------------


def test_manifest_apply_bypasses_flag_but_respects_content_locked(tmp_path):
    """FEATURE_PRODUCT_IMAGE_AUTOPROCESS выключен — обычная постановка в очередь
    отказала бы; применение по манифесту (--apply) всё равно обрабатывает, но
    content_locked не трогает (флаг не обходит этот инвариант)."""
    free = _photo(_product("free"))
    locked = _photo(_product("locked", content_locked=True))
    manifest = tmp_path / "ids.json"
    manifest.write_text(json.dumps({"ids": [free.pk, locked.pk]}), encoding="utf-8")
    snapshot_path = tmp_path / "run.json"

    call_command(
        "process_product_images",
        "--manifest",
        str(manifest),
        "--snapshot",
        str(snapshot_path),
        "--apply",
    )

    free.refresh_from_db()
    locked.refresh_from_db()
    assert (
        free.processing_status == ImageProcessingStatus.OBSERVED
    )  # маршрут не включён по умолчанию
    assert locked.processing_status == ImageProcessingStatus.NONE  # content_locked — не тронут
    assert json.loads(snapshot_path.read_text())["kind"] == "product_images_processing_run"


def test_manifest_apply_and_processing_rollback_round_trip(tmp_path, settings):
    settings.PRODUCT_IMAGE_AUTO_ACCEPT_ROUTES = {"trim"}
    image = _photo(_product())
    manifest = tmp_path / "ids.json"
    manifest.write_text(json.dumps([image.pk]), encoding="utf-8")
    snapshot_path = tmp_path / "run.json"

    call_command(
        "process_product_images",
        "--manifest",
        str(manifest),
        "--snapshot",
        str(snapshot_path),
        "--apply",
    )
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.DONE
    assert image.display

    call_command(
        "catalog_images_ops",
        "--mode",
        "processing-rollback",
        "--snapshot",
        str(snapshot_path),
        "--apply",
    )
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.NONE
    assert not image.display
    assert not image.candidate


def test_processing_rollback_refuses_if_human_decided_since(tmp_path, settings):
    """Fail-closed: если после прогона человек уже принял решение, откат не
    перезаписывает его молча — план целиком отказывает (как откат tool_type)."""
    settings.PRODUCT_IMAGE_AUTO_ACCEPT_ROUTES = set()  # наблюдение — кандидат, не display
    image = _photo(_product(), _small_shot())  # уйдёт в needs_review
    manifest = tmp_path / "ids.json"
    manifest.write_text(json.dumps([image.pk]), encoding="utf-8")
    snapshot_path = tmp_path / "run.json"

    call_command(
        "process_product_images",
        "--manifest",
        str(manifest),
        "--snapshot",
        str(snapshot_path),
        "--apply",
    )
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.NEEDS_REVIEW

    # Человек успел принять кандидата после прогона.
    image_autoprocess.accept_candidate(
        image.pk, expected_checksum=image.candidate_checksum, expected_revision=image.revision
    )

    with pytest.raises(CommandError):
        call_command(
            "catalog_images_ops",
            "--mode",
            "processing-rollback",
            "--snapshot",
            str(snapshot_path),
            "--apply",
        )
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.DONE  # решение человека не тронуто


def test_processing_rollback_dry_run_writes_nothing(tmp_path, settings):
    settings.PRODUCT_IMAGE_AUTO_ACCEPT_ROUTES = {"trim"}
    image = _photo(_product())
    manifest = tmp_path / "ids.json"
    manifest.write_text(json.dumps([image.pk]), encoding="utf-8")
    snapshot_path = tmp_path / "run.json"
    call_command(
        "process_product_images",
        "--manifest",
        str(manifest),
        "--snapshot",
        str(snapshot_path),
        "--apply",
    )
    call_command(
        "catalog_images_ops", "--mode", "processing-rollback", "--snapshot", str(snapshot_path)
    )
    image.refresh_from_db()
    assert image.processing_status == ImageProcessingStatus.DONE  # dry-run — ничего не изменилось
