# apps/catalog/tests/test_image_reversibility.py
"""ИЗО-02: идемпотентность записи изображений и обратимость прогона.

Проверяем ровно то, чего не было до трека: повторный прогон не плодит дубли,
откат снимает только спарсенное, `manual` не трогается ничем, а осиротевшие
файлы находятся и остаются на месте.
"""

from __future__ import annotations

import hashlib
import io
from datetime import timedelta

import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.utils import timezone
from PIL import Image

from apps.catalog.image_pipeline import ImagePipeline
from apps.catalog.image_reversibility import (
    RollbackRefused,
    apply_rollback,
    audit,
    build_plan,
    build_rollback_plan,
    build_snapshot,
)
from apps.catalog.models import Category, ImageSource, Product, ProductImage, ProductStatus

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _media(tmp_path, settings):
    """Своё MEDIA_ROOT на тест: сверка БД↔файлы не должна видеть чужие файлы."""
    settings.MEDIA_ROOT = tmp_path / "media"
    (tmp_path / "media" / "products").mkdir(parents=True)
    return settings.MEDIA_ROOT


def _png_bytes(w=600, h=600, color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _category():
    return Category.add_root(name="Перфораторы", slug="perf-izo")


def _product(cat, slug="p1", name="Товар"):
    return Product.objects.create(
        category=cat,
        name=name,
        slug=slug,
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
    )


def _image(product, *, source, url=None, checksum=None, fetched_at=None, payload=b"x"):
    """Запись + реальный файл в MEDIA_ROOT (иначе откат нечего удалять)."""
    image = ProductImage(
        product=product,
        source=source,
        source_url=url,
        checksum=checksum or hashlib.sha256(payload).hexdigest(),
        fetched_at=fetched_at,
    )
    image.image.save(f"products/{product.pk}/{id(payload)}.webp", ContentFile(payload), save=True)
    return image


# --- идемпотентность на уровне БД ---------------------------------------


def test_same_checksum_same_product_rejected():
    cat = _category()
    p = _product(cat)
    _image(p, source=ImageSource.RESANTA, url="https://a/1.jpg", checksum="a" * 64)
    with pytest.raises(IntegrityError), transaction.atomic():
        _image(p, source=ImageSource.RESANTA, url="https://a/2.jpg", checksum="a" * 64)


def test_same_checksum_different_products_allowed():
    """Одна картинка на серию товаров — законный случай, не дубль."""
    cat = _category()
    p1, p2 = _product(cat, "p1"), _product(cat, "p2")
    _image(p1, source=ImageSource.VIHR, url="https://a/1.jpg", checksum="b" * 64)
    _image(p2, source=ImageSource.VIHR, url="https://a/1.jpg", checksum="b" * 64)
    assert ProductImage.objects.filter(checksum="b" * 64).count() == 2


def test_same_url_same_product_rejected():
    cat = _category()
    p = _product(cat)
    _image(p, source=ImageSource.RESANTA, url="https://a/1.jpg", checksum="c" * 64)
    with pytest.raises(IntegrityError), transaction.atomic():
        _image(p, source=ImageSource.RESANTA, url="https://a/1.jpg", checksum="d" * 64)


def test_legacy_rows_without_provenance_do_not_collide():
    """107 существующих записей — с NULL-провенансом; они не должны конфликтовать."""
    cat = _category()
    p = _product(cat)
    _image(p, source=ImageSource.MANUAL, payload=b"one")
    ProductImage.objects.filter(product=p).update(checksum=None)
    _image(p, source=ImageSource.MANUAL, payload=b"two")
    ProductImage.objects.filter(product=p, checksum__isnull=False).update(checksum=None)
    assert ProductImage.objects.filter(product=p).count() == 2


# --- идемпотентность pipeline -------------------------------------------


def test_pipeline_repeat_same_url_no_duplicate(monkeypatch):
    cat = _category()
    p = _product(cat)
    pipe = ImagePipeline()
    monkeypatch.setattr(pipe, "_download", lambda url: _png_bytes())
    a = pipe.process_url(p, "https://x/y.png", source=ImageSource.RESANTA)
    b = pipe.process_url(p, "https://x/y.png", source=ImageSource.RESANTA)
    assert a.pk == b.pk
    assert p.images.count() == 1
    assert a.source == ImageSource.RESANTA and a.checksum and a.fetched_at


def test_pipeline_same_bytes_other_url_no_duplicate(monkeypatch):
    """Та же картинка под другим URL (CDN, ?v=2) — второй записи не будет."""
    cat = _category()
    p = _product(cat)
    pipe = ImagePipeline()
    monkeypatch.setattr(pipe, "_download", lambda url: _png_bytes())
    a = pipe.process_url(p, "https://x/y.png", source=ImageSource.VIHR)
    b = pipe.process_url(p, "https://cdn.x/y.png?v=2", source=ImageSource.VIHR)
    assert a.pk == b.pk and p.images.count() == 1


def test_pipeline_different_bytes_creates_second(monkeypatch):
    cat = _category()
    p = _product(cat)
    pipe = ImagePipeline()
    monkeypatch.setattr(pipe, "_download", lambda url: _png_bytes(color=(1, 2, 3)))
    pipe.process_url(p, "https://x/a.png", source=ImageSource.VIHR)
    monkeypatch.setattr(pipe, "_download", lambda url: _png_bytes(color=(9, 9, 9)))
    pipe.process_url(p, "https://x/b.png", source=ImageSource.VIHR)
    assert p.images.count() == 2


# --- план ----------------------------------------------------------------


def test_plan_marks_url_and_checksum_duplicates():
    cat = _category()
    p = _product(cat)
    _image(p, source=ImageSource.RESANTA, url="https://a/1.jpg", checksum="e" * 64)
    plan = build_plan(
        [
            {"product_id": p.pk, "source_url": "https://a/1.jpg", "source": "resanta"},
            {
                "product_id": p.pk,
                "source_url": "https://a/2.jpg",
                "checksum": "e" * 64,
                "source": "resanta",
            },
            {"product_id": p.pk, "source_url": "https://a/3.jpg", "source": "resanta"},
            {"product_id": p.pk, "source_url": "https://a/4.jpg", "source": "manual"},
        ]
    )
    assert plan["skip_same_url"] == 1
    assert plan["skip_same_checksum"] == 1
    assert plan["add"] == 1
    assert plan["invalid"] == 1  # manual в плане прогона недопустим


# --- откат ---------------------------------------------------------------


def test_rollback_refuses_manual():
    with pytest.raises(RollbackRefused):
        build_rollback_plan(source=ImageSource.MANUAL)


def test_rollback_restores_previous_state():
    """Создали прогон → откатили → состояние равно исходному (БД и файлы)."""
    cat = _category()
    p = _product(cat)
    _image(p, source=ImageSource.MANUAL, payload=b"manual-photo")
    before = build_snapshot()

    run_at = timezone.now()
    _image(
        p,
        source=ImageSource.RESANTA,
        url="https://a/1.jpg",
        fetched_at=run_at,
        payload=b"scraped-1",
    )
    _image(
        p,
        source=ImageSource.RESANTA,
        url="https://a/2.jpg",
        fetched_at=run_at,
        payload=b"scraped-2",
    )
    assert build_snapshot()["records_total"] == 3

    plan = build_rollback_plan(source=ImageSource.RESANTA, since=run_at - timedelta(minutes=1))
    assert plan["records_to_delete"] == 2 and plan["files_to_delete"] == 2
    result = apply_rollback(plan)
    assert result["records_deleted"] == 2 and result["files_deleted"] == 2

    after = build_snapshot()
    assert after["records"] == before["records"]
    assert after["files"] == before["files"]
    assert after["orphan_files"] == before["orphan_files"] == []


def test_rollback_does_not_touch_manual():
    cat = _category()
    p = _product(cat)
    manual = _image(p, source=ImageSource.MANUAL, payload=b"manual-photo")
    run_at = timezone.now()
    _image(p, source=ImageSource.ZUBR, url="https://z/1.jpg", fetched_at=run_at, payload=b"scraped")

    apply_rollback(build_rollback_plan(source=ImageSource.ZUBR))

    manual.refresh_from_db()
    assert ProductImage.objects.count() == 1
    assert (build_snapshot()["media_root"], manual.source) == (
        build_snapshot()["media_root"],
        ImageSource.MANUAL,
    )
    assert audit()["missing_file_total"] == 0


def test_rollback_window_limits_to_run():
    """Откат — по source И окну fetched_at: прошлый прогон не задевается."""
    cat = _category()
    p = _product(cat)
    old = timezone.now() - timedelta(days=3)
    new = timezone.now()
    _image(p, source=ImageSource.VIHR, url="https://v/old.jpg", fetched_at=old, payload=b"old")
    _image(p, source=ImageSource.VIHR, url="https://v/new.jpg", fetched_at=new, payload=b"new")

    plan = build_rollback_plan(source=ImageSource.VIHR, since=new - timedelta(minutes=5))
    assert plan["records_to_delete"] == 1
    apply_rollback(plan)
    assert list(ProductImage.objects.values_list("source_url", flat=True)) == ["https://v/old.jpg"]


def test_rollback_conflict_when_record_changed_after_plan():
    """Между планом и применением запись переехала в manual — отказ целиком."""
    cat = _category()
    p = _product(cat)
    img = _image(
        p,
        source=ImageSource.RESANTA,
        url="https://a/1.jpg",
        fetched_at=timezone.now(),
        payload=b"scraped",
    )
    plan = build_rollback_plan(source=ImageSource.RESANTA)
    ProductImage.objects.filter(pk=img.pk).update(source=ImageSource.MANUAL)
    with pytest.raises(RollbackRefused):
        apply_rollback(plan)
    assert ProductImage.objects.count() == 1


# --- post-audit и сироты --------------------------------------------------


def test_audit_finds_orphan_files_and_keeps_them(_media):
    cat = _category()
    p = _product(cat)
    _image(p, source=ImageSource.MANUAL, payload=b"kept")
    orphan = _media / "products" / "orphan.webp"
    orphan.write_bytes(b"nobody-references-me")

    report = audit()
    assert report["orphan_files_total"] == 1
    assert report["orphan_files"] == ["products/orphan.webp"]
    assert orphan.exists(), "сироты только показываются, удаление — решение владельца"


def test_audit_reports_missing_file_and_checksum_drift(_media):
    cat = _category()
    p = _product(cat)
    gone = _image(p, source=ImageSource.MANUAL, payload=b"will-vanish")
    (_media / gone.image.name).unlink()
    drifted = _image(p, source=ImageSource.RESANTA, url="https://a/1.jpg", payload=b"stable")
    ProductImage.objects.filter(pk=drifted.pk).update(checksum="f" * 64)

    report = audit()
    assert report["missing_file_total"] == 1
    assert report["checksum_mismatch_total"] == 1


# --- команда --------------------------------------------------------------


def test_command_rollback_is_dry_run_by_default(capsys):
    cat = _category()
    p = _product(cat)
    _image(
        p,
        source=ImageSource.RESANTA,
        url="https://a/1.jpg",
        fetched_at=timezone.now(),
        payload=b"scraped",
    )
    call_command("catalog_images_ops", "--mode", "rollback", "--source", "resanta")
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert ProductImage.objects.count() == 1, "dry-run обязан ничего не удалять"


def test_command_rollback_refuses_manual():
    with pytest.raises(CommandError):
        call_command("catalog_images_ops", "--mode", "rollback", "--source", "manual", "--apply")


def test_command_snapshot_and_audit_report_orphans(tmp_path, _media, capsys):
    cat = _category()
    p = _product(cat)
    _image(p, source=ImageSource.MANUAL, payload=b"kept")
    (_media / "products" / "orphan.webp").write_bytes(b"orphan")

    out_file = tmp_path / "snapshot.json"
    call_command("catalog_images_ops", "--mode", "snapshot", "--out", str(out_file))
    call_command("catalog_images_ops", "--mode", "audit")
    out = capsys.readouterr().out
    assert out_file.exists()
    assert "осиротевших файлов:    1" in out
    assert (_media / "products" / "orphan.webp").exists()
