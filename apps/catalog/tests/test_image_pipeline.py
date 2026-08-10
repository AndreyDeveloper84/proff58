# apps/catalog/tests/test_image_pipeline.py
import io
import threading
import time

import pytest
from django.test import override_settings
from PIL import Image

from apps.catalog.image_pipeline import HostThrottle, ImagePipeline
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


# --- ИЗО-09: вежливый темп по хосту -----------------------------------------


class _FakeClock:
    """Часы + пауза без реального ожидания: sleep двигает время вперёд."""

    def __init__(self, start=1000.0):
        self.now = start
        self.slept = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds

    def advance(self, seconds):
        self.now += seconds


def _throttle():
    clock = _FakeClock()
    return clock, HostThrottle(monotonic=clock.monotonic, sleep=clock.sleep)


def test_throttle_holds_interval_for_one_host():
    # первый запрос идёт сразу, каждый следующий к тому же хосту ждёт интервал
    clock, throttle = _throttle()
    waits = [throttle.wait("cdn.example", 3.0) for _ in range(3)]
    assert waits == [0.0, 3.0, 3.0]
    assert clock.slept == [3.0, 3.0]


def test_throttle_does_not_delay_other_hosts():
    # темп считается ПО ХОСТУ: чужая площадка не занимает окно соседней
    clock, throttle = _throttle()
    assert throttle.wait("a.example", 3.0) == 0.0
    assert throttle.wait("b.example", 3.0) == 0.0
    assert throttle.wait("c.example", 3.0) == 0.0
    assert clock.slept == []
    # а повтор по первому хосту всё так же ждёт
    assert throttle.wait("a.example", 3.0) == 3.0


def test_throttle_subtracts_time_already_elapsed():
    # если между запросами прошло 2 из 3 секунд — доспим только остаток
    clock, throttle = _throttle()
    throttle.wait("cdn.example", 3.0)
    clock.advance(2.0)
    assert throttle.wait("cdn.example", 3.0) == pytest.approx(1.0)
    # прошло больше интервала — паузы нет вовсе
    clock.advance(10.0)
    assert throttle.wait("cdn.example", 3.0) == 0.0
    assert clock.slept == [pytest.approx(1.0)]


def test_throttle_interval_is_configurable():
    clock, throttle = _throttle()
    throttle.wait("cdn.example", 0.5)
    assert throttle.wait("cdn.example", 0.5) == pytest.approx(0.5)
    assert clock.slept == [pytest.approx(0.5)]


def test_throttle_zero_interval_never_sleeps():
    clock, throttle = _throttle()
    assert [throttle.wait("cdn.example", 0) for _ in range(5)] == [0.0] * 5
    assert clock.slept == []


def test_throttle_host_is_case_insensitive():
    clock, throttle = _throttle()
    throttle.wait("CDN.Example", 3.0)
    assert throttle.wait("cdn.example", 3.0) == 3.0


def test_throttle_serializes_concurrent_threads_on_one_host():
    # замок хоста держится и на время паузы: два потока не проскочат парой
    throttle = HostThrottle()
    started = time.monotonic()
    waits = []
    lock = threading.Lock()

    def worker():
        waited = throttle.wait("cdn.example", 0.05)
        with lock:
            waits.append(waited)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - started
    assert len(waits) == 4
    assert sorted(waits)[0] == 0.0  # ровно один прошёл без паузы
    assert sum(w > 0 for w in waits) == 3
    assert elapsed >= 0.15 - 0.01  # три интервала по 0.05 выдержаны


@override_settings(IMAGE_FETCH_INTERVAL_SECONDS=7.5)
def test_pipeline_reads_interval_from_settings():
    assert ImagePipeline().throttle_interval == 7.5
    # явный аргумент конструктора перебивает настройку
    assert ImagePipeline(throttle_interval=0).throttle_interval == 0.0


def _fake_pool(monkeypatch, calls):
    """Подменяет HTTPSConnectionPool: сеть не дёргаем, только считаем запросы."""

    class _Resp:
        status = 200
        headers = {}

        def read(self, _n):
            return b"payload"

        def release_conn(self):
            pass

    class _Pool:
        def __init__(self, host, **kw):
            self.host = host

        def urlopen(self, method, target, **kw):
            calls.append(target)
            return _Resp()

        def close(self):
            pass

    monkeypatch.setattr("apps.catalog.image_pipeline.urllib3.HTTPSConnectionPool", _Pool)


def test_download_throttles_between_requests_to_same_host(monkeypatch):
    calls = []
    _fake_pool(monkeypatch, calls)
    monkeypatch.setattr(ImagePipeline, "_resolve_public_ips", lambda self, host: ["8.8.8.8"])
    clock, throttle = _throttle()
    pipe = ImagePipeline(throttle_interval=3.0, throttle=throttle)

    assert pipe._download("https://cdn.example/1.png") == b"payload"
    assert clock.slept == []
    assert pipe._download("https://cdn.example/2.png") == b"payload"
    assert clock.slept == [3.0]
    # другой хост — без ожидания
    assert pipe._download("https://other.example/1.png") == b"payload"
    assert clock.slept == [3.0]
    assert len(calls) == 3


def test_download_rejected_url_does_not_burn_throttle_window(monkeypatch):
    # отбракованный URL до чужого сервера не доходит — паузу тратить не на что
    clock, throttle = _throttle()
    pipe = ImagePipeline(throttle_interval=3.0, throttle=throttle)
    assert pipe._download("http://cdn.example/x.png") is None
    assert pipe._download("https://127.0.0.1/x.png") is None
    assert pipe._download("https://8.8.8.8:8080/x.png") is None
    assert clock.slept == []
