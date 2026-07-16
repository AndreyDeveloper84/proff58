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


def test_download_rejects_non_https():
    # M-13: только https
    assert ImagePipeline()._download("http://example.test/x.png") is None


def test_download_rejects_private_host():
    # M-13: SSRF — loopback/private хост отклоняется ДО сетевого запроса
    assert ImagePipeline()._download("https://127.0.0.1/x.png") is None
    assert ImagePipeline()._download("https://localhost/x.png") is None


def test_host_is_public_rejects_private():
    p = ImagePipeline()
    assert p._host_is_public("127.0.0.1") is False
    assert p._host_is_public("localhost") is False


def test_process_bytes_rejects_decompression_bomb():
    # M-13: изображение сверх лимита пикселей отбраковывается
    pipe = ImagePipeline()
    pipe.MAX_PIXELS = 1000
    assert pipe._process_bytes(_png_bytes(1500, 1500)) is None


def test_download_rejects_nonstandard_port():
    # M-13: только стандартный https-порт 443 (публичный IP на 8080 не пробиваем)
    assert ImagePipeline()._download("https://8.8.8.8:8080/x.png") is None


def test_download_rejects_metadata_ip():
    # M-13: cloud metadata (link-local) — классическая цель SSRF
    assert ImagePipeline()._download("https://169.254.169.254/latest/meta-data/") is None


def test_resolve_public_ips_returns_validated(monkeypatch):
    def fake_getaddrinfo(host, *a, **k):
        return [(2, 1, 6, "", ("8.8.8.8", 0))]

    monkeypatch.setattr("apps.catalog.image_pipeline.socket.getaddrinfo", fake_getaddrinfo)
    assert ImagePipeline()._resolve_public_ips("cdn.example") == ["8.8.8.8"]


def test_resolve_rejects_when_any_ip_private(monkeypatch):
    # M-13/DNS-rebinding: если хоть один адрес приватный — отказ (не только по первому)
    def fake_getaddrinfo(host, *a, **k):
        return [(2, 1, 6, "", ("8.8.8.8", 0)), (2, 1, 6, "", ("10.0.0.5", 0))]

    monkeypatch.setattr("apps.catalog.image_pipeline.socket.getaddrinfo", fake_getaddrinfo)
    assert ImagePipeline()._resolve_public_ips("rebind.example") is None
