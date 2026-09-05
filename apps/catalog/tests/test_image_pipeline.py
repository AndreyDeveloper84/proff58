# apps/catalog/tests/test_image_pipeline.py
import io
import threading
import time

import pytest
from django.test import override_settings
from PIL import Image

from apps.catalog.image_pipeline import HostThrottle, ImagePipeline
from apps.catalog.models import Category, ImageSource, Product, ProductImage, ProductStatus


@pytest.fixture(autouse=True)
def _media(tmp_path, settings):
    """Своё MEDIA_ROOT на тест: pipeline пишет реальные webp, не в общий media/."""
    settings.MEDIA_ROOT = tmp_path / "media"
    (tmp_path / "media" / "products").mkdir(parents=True)
    return settings.MEDIA_ROOT


def _png_bytes(w=1500, h=1500, color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
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


# --- VI-INT-02a: инвариант main-изображения -------------------------------
#
# Контракт: импорт не создаёт ВТОРОЙ main и не демотирует существующий;
# при отсутствующем main его получает первое РЕАЛЬНО СОЗДАННОЕ изображение
# пачки (дедуп — не создание и в счёт не идёт).

_COLORS = [(200, 30, 30), (30, 200, 30), (30, 30, 200), (200, 200, 30)]


def _batch_pipe(monkeypatch, urls):
    """Pipeline с подменённым скачиванием: каждому URL — свои байты (свой checksum).

    Возвращает (pipe, calls): calls — журнал обращений к _download, чтобы
    проверять, что дедуп до сети не выполняет скачивание.
    """
    pipe = ImagePipeline()
    mapping = {url: _png_bytes(color=_COLORS[i % len(_COLORS)]) for i, url in enumerate(urls)}
    calls = []

    def fake_download(url):
        calls.append(url)
        return mapping.get(url)

    monkeypatch.setattr(pipe, "_download", fake_download)
    return pipe, calls


def _existing_image(product, *, is_main=False, source=ImageSource.MANUAL, url=None, sort_order=7):
    """Запись об уже существующем изображении (файл не нужен — его никто не читает)."""
    return ProductImage.objects.create(
        product=product,
        image=f"products/{product.pk}/existing-{sort_order}.webp",
        alt="старое фото",
        is_main=is_main,
        sort_order=sort_order,
        source=source,
        source_url=url,
        checksum=None,
    )


def _fields(image):
    """Контролируемые поля записи для сравнения «до/после» (T6)."""
    return {
        "is_main": image.is_main,
        "sort_order": image.sort_order,
        "checksum": image.checksum,
        "source": image.source,
        "source_url": image.source_url,
        "alt": image.alt,
        "image": image.image.name,
    }


@pytest.mark.django_db
def test_t1_empty_gallery_first_created_becomes_main(monkeypatch):
    """T1/сценарий B: пустая галерея — main ровно один, у первого созданного."""
    p = _product()
    urls = ["https://r.test/1.png", "https://r.test/2.png", "https://r.test/3.png"]
    pipe, _ = _batch_pipe(monkeypatch, urls)

    images = pipe.process_batch(p, urls, source=ImageSource.RESANTA)

    assert len(images) == 3
    mains = [i for i in images if i.is_main]
    assert len(mains) == 1
    assert mains[0].source_url == urls[0], "main — первое созданное изображение пачки"
    assert [i.is_main for i in images] == [True, False, False]
    assert p.images.filter(is_main=True).count() == 1


@pytest.mark.django_db
def test_t2_existing_main_survives_batch_unchanged(monkeypatch):
    """T2/сценарий A: main уже есть — второй не создаётся, существующий не меняется."""
    p = _product()
    old_main = _existing_image(p, is_main=True)
    before = _fields(old_main)
    urls = ["https://r.test/1.png", "https://r.test/2.png", "https://r.test/3.png"]
    pipe, _ = _batch_pipe(monkeypatch, urls)

    images = pipe.process_batch(p, urls, source=ImageSource.RESANTA)

    assert len(images) == 3
    assert all(not i.is_main for i in images), "новые изображения — всегда не-main"
    assert p.images.filter(is_main=True).count() == 1
    old_main.refresh_from_db()
    assert _fields(old_main) == before, "существующий main не изменён ни в одном поле"
    assert old_main.is_main is True


@pytest.mark.django_db
def test_t3_gallery_without_main_first_created_promoted(monkeypatch):
    """T3/сценарий B: галерея без main — существующие не трогаем, main у первого созданного."""
    p = _product()
    old1 = _existing_image(p, is_main=False, sort_order=1)
    old2 = _existing_image(p, is_main=False, sort_order=2)
    before = {_fields(old1)["image"]: _fields(old1), _fields(old2)["image"]: _fields(old2)}
    urls = ["https://r.test/1.png", "https://r.test/2.png"]
    pipe, _ = _batch_pipe(monkeypatch, urls)

    images = pipe.process_batch(p, urls, source=ImageSource.RESANTA)

    assert [i.is_main for i in images] == [True, False]
    assert p.images.filter(is_main=True).count() == 1
    for old in (old1, old2):
        old.refresh_from_db()
        assert _fields(old) == before[old.image.name], "существующие записи не изменились"


@pytest.mark.django_db
def test_t4_dedup_first_url_second_created_gets_main(monkeypatch):
    """T4/сценарий C: первый URL — дедуп, main получает второй (первый созданный)."""
    p = _product()
    urls = ["https://r.test/1.png", "https://r.test/2.png"]
    existing = _existing_image(p, is_main=False, source=ImageSource.RESANTA, url=urls[0])
    before = _fields(existing)
    pipe, calls = _batch_pipe(monkeypatch, urls)

    images = pipe.process_batch(p, urls, source=ImageSource.RESANTA)

    assert [i.pk for i in images] == [existing.pk, images[1].pk]
    assert calls == [urls[1]], "дедуп по source_url до сети — скачивание не выполняется"
    assert images[0].is_main is False and images[1].is_main is True
    existing.refresh_from_db()
    assert _fields(existing) == before, "дедуп-запись не изменилась и не стала main"
    assert p.images.filter(is_main=True).count() == 1


@pytest.mark.django_db
def test_t5_repeat_batch_creates_nothing_and_skips_network(monkeypatch):
    """T5: повторный прогон той же пачки — create 0, update 0, сеть не дёргается."""
    p = _product()
    urls = ["https://r.test/1.png", "https://r.test/2.png", "https://r.test/3.png"]
    pipe, calls = _batch_pipe(monkeypatch, urls)
    first = pipe.process_batch(p, urls, source=ImageSource.RESANTA)
    mains_before = list(p.images.filter(is_main=True).values_list("pk", flat=True))

    again = pipe.process_batch(p, urls, source=ImageSource.RESANTA)

    assert [i.pk for i in again] == [i.pk for i in first]
    assert p.images.count() == 3, "новых записей нет"
    assert len(calls) == 3, "повторный прогон: дедуп по source_url до сети, скачиваний нет"
    assert list(p.images.filter(is_main=True).values_list("pk", flat=True)) == mains_before


@pytest.mark.django_db
def test_t6_existing_main_immutable_all_fields(monkeypatch):
    """T6: полное сравнение контролируемых полей существующего main до/после импорта."""
    p = _product()
    old_main = _existing_image(p, is_main=True, sort_order=3, url="https://r.test/old.png")
    before = _fields(old_main)
    urls = ["https://r.test/1.png", "https://r.test/2.png"]
    pipe, _ = _batch_pipe(monkeypatch, urls)

    pipe.process_batch(p, urls, source=ImageSource.RESANTA)

    old_main.refresh_from_db()
    assert _fields(old_main) == before
    assert p.images.filter(is_main=True).count() == 1


@pytest.mark.django_db
def test_t7_main_from_other_source_not_demoted(monkeypatch):
    """T7: main другого источника (resanta) переживает импорт vseinstrumenti."""
    p = _product()
    old_main = _existing_image(p, is_main=True, source=ImageSource.RESANTA)
    urls = ["https://v.test/1.png", "https://v.test/2.png"]
    pipe, _ = _batch_pipe(monkeypatch, urls)

    images = pipe.process_batch(p, urls, source=ImageSource.VSEINSTRUMENTI)

    assert all(not i.is_main for i in images)
    old_main.refresh_from_db()
    assert old_main.is_main is True, "чужой main не демотирован"
    assert p.images.filter(is_main=True).count() == 1


@pytest.mark.django_db
def test_secondary_images_order_stable_by_pk():
    """VI-INT-03: ordering ["-is_main", "sort_order", "pk"] — main первый,
    secondary при равном sort_order выстраиваются стабильно по pk."""
    p = _product()
    main = _existing_image(p, is_main=True, sort_order=0)
    sec = [_existing_image(p, is_main=False, sort_order=0) for _ in range(3)]

    expected = [main.pk] + [i.pk for i in sec]
    for _ in range(3):  # порядок обязан быть одинаковым от запроса к запросу
        assert [i.pk for i in p.images.all()] == expected
    assert p.images.first().pk == main.pk, "единственный main — всегда первый"
