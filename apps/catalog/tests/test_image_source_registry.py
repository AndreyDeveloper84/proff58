# apps/catalog/tests/test_image_source_registry.py
"""MEDIA-SOURCE-01: реестр источников изображений расширен manufacturer-сайтами.

Новые идентификаторы (`hanskonner`, `einhell`, `thorvik`) должны проходить весь
существующий media-контракт без изменений самого контракта: model validation,
сохранение провенанса, `ImagePipeline.process_batch`, план/откат прогона,
main-инвариант и дедуп. Старые значения продолжают работать как раньше.
"""
import io

import pytest
from django.core.files.base import ContentFile
from PIL import Image

from apps.catalog.image_pipeline import ImagePipeline
from apps.catalog.image_reversibility import RollbackRefused, build_plan, build_rollback_plan
from apps.catalog.models import Category, ImageSource, Product, ProductImage, ProductStatus

pytestmark = pytest.mark.django_db

NEW_SOURCES = ("hanskonner", "einhell", "thorvik")
OLD_SOURCES = ("manual", "resanta", "vihr", "interskol", "zubr", "huter", "vseinstrumenti")


@pytest.fixture(autouse=True)
def _media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    (tmp_path / "media" / "products").mkdir(parents=True)
    return settings.MEDIA_ROOT


def _png_bytes(w=1500, h=1500, color=(30, 120, 200)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _product(slug="p-src"):
    cat = Category.add_root(name="Дрели", slug=f"dreli-{slug}")
    return Product.objects.create(
        category=cat,
        name="Дрель",
        slug=slug,
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
    )


@pytest.mark.parametrize("source", NEW_SOURCES)
def test_new_source_is_registered_and_fits_field(source):
    assert source in ImageSource.values
    assert len(source) <= ProductImage._meta.get_field("source").max_length


@pytest.mark.parametrize("source", OLD_SOURCES)
def test_existing_sources_unchanged(source):
    assert source in ImageSource.values


def test_registry_labels_name_actual_hosts():
    labels = dict(ImageSource.choices)
    assert labels["hanskonner"] == "hanskonner.ru"
    assert labels["thorvik"] == "thorvik.ru"
    # einhell.ru — мёртвая заглушка; фактический manufacturer-источник — einhell.de
    assert labels["einhell"] == "einhell.de"


@pytest.mark.parametrize("source", NEW_SOURCES)
def test_new_source_passes_model_validation_and_persists_provenance(source):
    p = _product(slug=f"p-{source}")
    image = ProductImage(
        product=p,
        source=source,
        source_url=f"https://{source}.example/1.png",
        checksum="a" * 64,
    )
    image.full_clean(exclude=["image"])
    image.image.save(f"products/{p.pk}/x.webp", ContentFile(b"x"), save=True)
    stored = ProductImage.objects.get(pk=image.pk)
    assert (stored.source, stored.source_url, stored.checksum) == (
        source,
        f"https://{source}.example/1.png",
        "a" * 64,
    )


@pytest.mark.parametrize("source", NEW_SOURCES)
def test_pipeline_process_batch_accepts_new_source(monkeypatch, source):
    p = _product(slug=f"batch-{source}")
    pipe = ImagePipeline()
    # разные байты на разные URL — иначе второй кадр законно дедупится по checksum
    monkeypatch.setattr(
        pipe,
        "_download",
        lambda url: _png_bytes(color=(30, 120, 200 if url.endswith("a.png") else 90)),
    )
    created = pipe.process_batch(
        p, ["https://cdn.example/a.png", "https://cdn.example/b.png"], source=source
    )
    assert [img.source for img in created] == [source, source]
    assert created[0].pk != created[1].pk
    assert p.images.filter(is_main=True).count() == 1
    assert created[0].is_main and not created[1].is_main


def test_pipeline_dedup_and_idempotency_unchanged_for_new_source(monkeypatch):
    p = _product(slug="dedup-new")
    pipe = ImagePipeline()
    monkeypatch.setattr(pipe, "_download", lambda url: _png_bytes())
    first = pipe.process_batch(p, ["https://cdn.example/a.png"], source="hanskonner")
    again = pipe.process_batch(p, ["https://cdn.example/a.png"], source="hanskonner")
    same_bytes = pipe.process_batch(p, ["https://cdn.example/a-copy.png"], source="hanskonner")
    assert first[0].pk == again[0].pk == same_bytes[0].pk
    assert p.images.count() == 1


def test_pipeline_still_rejects_unknown_and_manual_source():
    p = _product(slug="reject")
    with pytest.raises(ValueError):
        ImagePipeline().process_batch(p, ["https://cdn.example/a.png"], source="denzel")
    with pytest.raises(ValueError):
        ImagePipeline().process_batch(p, ["https://cdn.example/a.png"], source="manual")


@pytest.mark.parametrize("source", NEW_SOURCES)
def test_run_plan_accepts_new_source(source):
    p = _product(slug=f"plan-{source}")
    plan = build_plan(
        [{"product_id": p.pk, "source_url": "https://cdn.example/1.png", "source": source}]
    )
    assert plan["add"] == 1 and plan["invalid"] == 0


@pytest.mark.parametrize("source", NEW_SOURCES)
def test_rollback_plan_accepts_new_source_and_spares_manual(source):
    p = _product(slug=f"rb-{source}")
    for src, url in ((source, "https://cdn.example/1.png"), ("manual", None)):
        img = ProductImage(product=p, source=src, source_url=url, checksum=f"{src[:1]}" * 64)
        img.image.save(f"products/{p.pk}/{src}.webp", ContentFile(src.encode()), save=True)
    plan = build_rollback_plan(source=source)
    assert plan["records_to_delete"] == 1
    assert [t["id"] for t in plan["targets"]] == [p.images.get(source=source).pk]
    with pytest.raises(RollbackRefused):
        build_rollback_plan(source="manual")
