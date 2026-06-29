# apps/catalog/tests/test_image_pipeline.py
import io

import pytest
from PIL import Image

from apps.catalog.image_pipeline import ImagePipeline
from apps.catalog.models import Category, Product, ProductStatus


def _png_bytes(w=1500, h=1500):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _product(**kw):
    cat = Category.add_root(name="Перф", slug="perf")
    return Product.objects.create(
        category=cat,
        name="X",
        slug="x",
        status=ProductStatus.IMPORTED,
        is_active=False,
        price="1000",
        **kw,
    )


def test_process_bytes_resizes_and_thumbs():
    main, thumb = ImagePipeline()._process_bytes(_png_bytes())
    assert Image.open(io.BytesIO(main.read())).size[0] <= 1200
    assert Image.open(io.BytesIO(thumb.read())).size[0] <= 400


def test_process_bytes_rejects_non_image():
    assert ImagePipeline()._process_bytes(b"not-an-image") is None


@pytest.mark.django_db
def test_content_locked_blocks(monkeypatch):
    p = _product(content_locked=True)
    pipe = ImagePipeline()
    monkeypatch.setattr(pipe, "_download", lambda url: _png_bytes())
    assert pipe.process_url(p, "http://x/y.png") is None
    assert p.images.count() == 0


@pytest.mark.django_db
def test_process_url_idempotent(monkeypatch):
    p = _product()
    pipe = ImagePipeline()
    monkeypatch.setattr(pipe, "_download", lambda url: _png_bytes())
    a = pipe.process_url(p, "http://x/y.png")
    b = pipe.process_url(p, "http://x/y.png")
    assert a.pk == b.pk and p.images.count() == 1
