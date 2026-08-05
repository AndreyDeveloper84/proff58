"""Рейтинг «хитов продаж»: факты, окно, бейдж и витрина.

Главное, что проверяем — витрина не может соврать: в «хиты» попадает только то,
у чего есть продажи за окно.
"""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.admin import site
from django.contrib.messages.storage.fallback import FallbackStorage
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import (
    Product,
    ProductSalesFact,
    ProductSalesStat,
    ProductStatus,
    SalesSource,
)
from apps.catalog.sales import (
    SalesRow,
    bestsellers_queryset,
    purge_old_sales_facts,
    rebuild_sales_stats,
    record_sales_facts,
    sales_window,
)

pytestmark = pytest.mark.django_db


def make_product(code: str, **kwargs) -> Product:
    return Product.objects.create(
        code_1c=code,
        name=f"Товар {code}",
        slug=f"tovar-{code}",
        status=kwargs.pop("status", ProductStatus.PUBLISHED),
        is_active=kwargs.pop("is_active", True),
        **kwargs,
    )


def sell(product: Product, quantity: str, *, days_ago: int = 0, source: str = SalesSource.ONEC):
    day = timezone.localdate() - timedelta(days=days_ago)
    record_sales_facts(source, [SalesRow(product.id, day, Decimal(quantity))])


class TestRecordSalesFacts:
    def test_повторная_выгрузка_дня_не_удваивает_продажи(self):
        product = make_product("A")
        sell(product, "5")
        sell(product, "5")

        assert ProductSalesFact.objects.count() == 1
        assert ProductSalesFact.objects.get().quantity == Decimal("5.000")

    def test_разные_источники_складываются_а_не_конфликтуют(self):
        product = make_product("A")
        sell(product, "2", source=SalesSource.ONEC)
        sell(product, "3", source=SalesSource.SITE)

        assert ProductSalesFact.objects.count() == 2
        rebuild_sales_stats()
        assert ProductSalesStat.objects.get(product=product).quantity == Decimal("5.000")

    def test_нулевые_количества_отбрасываются(self):
        product = make_product("A")
        day = timezone.localdate()
        result = record_sales_facts(
            SalesSource.ONEC,
            [SalesRow(product.id, day, Decimal("0")), SalesRow(product.id, day, Decimal("-1"))],
        )

        assert result["written"] == 0
        assert result["skipped"] == 2
        assert not ProductSalesFact.objects.exists()

    def test_пересчёт_окна_снимает_отменённую_продажу(self):
        """Режим сайта: заказ отменили — продажа обязана исчезнуть."""
        product = make_product("A")
        since, until = sales_window()
        record_sales_facts(
            SalesSource.SITE,
            [SalesRow(product.id, until, Decimal("4"))],
            replace_window=(since, until),
        )
        assert ProductSalesFact.objects.count() == 1

        record_sales_facts(SalesSource.SITE, [], replace_window=(since, until))
        assert not ProductSalesFact.objects.exists()

    def test_пересчёт_сайта_не_трогает_выгрузку_1с(self):
        product = make_product("A")
        sell(product, "7", source=SalesSource.ONEC)
        since, until = sales_window()

        record_sales_facts(SalesSource.SITE, [], replace_window=(since, until))

        assert ProductSalesFact.objects.filter(source=SalesSource.ONEC).count() == 1


class TestRebuildSalesStats:
    def test_рейтинг_упорядочен_по_продажам(self):
        top, mid, low = (make_product(c) for c in "ABC")
        sell(top, "10")
        sell(mid, "5")
        sell(low, "1")

        rebuild_sales_stats()

        assert [s.product_id for s in ProductSalesStat.objects.order_by("rank")] == [
            top.id,
            mid.id,
            low.id,
        ]

    def test_продажи_вне_окна_не_учитываются(self, settings):
        settings.SALES_WINDOW_DAYS = 30
        product = make_product("A")
        sell(product, "9", days_ago=45)

        rebuild_sales_stats()

        assert not ProductSalesStat.objects.exists()

    def test_товар_выпавший_из_окна_теряет_рейтинг(self, settings):
        settings.SALES_WINDOW_DAYS = 30
        product = make_product("A")
        sell(product, "9", days_ago=10)
        rebuild_sales_stats()
        assert ProductSalesStat.objects.exists()

        # Через полсотни дней та же продажа уже вне окна.
        rebuild_sales_stats(today=timezone.localdate() + timedelta(days=50))

        assert not ProductSalesStat.objects.exists()

    def test_единичная_продажа_не_делает_хитом(self, settings):
        settings.SALES_HIT_MIN_QUANTITY = 3
        weak, strong = make_product("A"), make_product("B")
        sell(weak, "1")
        sell(strong, "4")

        rebuild_sales_stats()

        assert ProductSalesStat.objects.get(product=strong).is_hit is True
        assert ProductSalesStat.objects.get(product=weak).is_hit is False

    def test_хитов_не_больше_чем_топ_n(self, settings):
        settings.SALES_HIT_TOP_N = 2
        settings.SALES_HIT_MIN_QUANTITY = 1
        for index in range(4):
            sell(make_product(f"P{index}"), str(10 - index))

        result = rebuild_sales_stats()

        assert result["hits"] == 2
        assert ProductSalesStat.objects.filter(is_hit=True).count() == 2

    def test_дни_с_продажами_и_последняя_продажа(self):
        product = make_product("A")
        sell(product, "2", days_ago=3)
        sell(product, "3", days_ago=1)

        rebuild_sales_stats()

        stat = ProductSalesStat.objects.get(product=product)
        assert stat.quantity == Decimal("5.000")
        assert stat.days_with_sales == 2
        assert stat.last_sold_on == timezone.localdate() - timedelta(days=1)


class TestBestsellersQueryset:
    def test_только_товары_с_продажами(self):
        sold, never_sold = make_product("A"), make_product("B")
        sell(sold, "5")
        rebuild_sales_stats()

        assert list(bestsellers_queryset()) == [sold]
        assert never_sold not in list(bestsellers_queryset())

    def test_неопубликованный_товар_в_витрину_не_попадёт(self):
        hidden = make_product("A", status=ProductStatus.DRAFT)
        sell(hidden, "50")
        rebuild_sales_stats()

        assert list(bestsellers_queryset()) == []


class TestPurge:
    def test_чистит_только_давние_факты(self, settings):
        settings.SALES_WINDOW_DAYS = 30
        product = make_product("A")
        sell(product, "1", days_ago=10)  # в окне
        sell(product, "1", days_ago=45)  # хвост для сверки
        sell(product, "1", days_ago=120)  # за двойным окном

        purge_old_sales_facts()

        assert ProductSalesFact.objects.count() == 2


class TestBestsellersApi:
    def test_пустая_выдача_когда_продаж_нет(self, client):
        make_product("A")

        response = client.get(reverse("catalog_api:bestsellers"))

        assert response.status_code == 200
        assert response.json()["results"] == []

    def test_отдаёт_проданное_с_бейджем_хита(self, client, settings):
        settings.SALES_HIT_MIN_QUANTITY = 1
        product = make_product("A")
        sell(product, "5")
        rebuild_sales_stats()

        response = client.get(reverse("catalog_api:bestsellers"))

        results = response.json()["results"]
        assert [r["slug"] for r in results] == [product.slug]
        assert results[0]["is_hit"] is True

    def test_обычный_список_помечает_хитом_только_проданное(self, client, settings):
        settings.SALES_HIT_MIN_QUANTITY = 1
        hit, plain = make_product("A"), make_product("B")
        sell(hit, "5")
        rebuild_sales_stats()

        response = client.get(reverse("catalog_api:product-list"))

        by_slug = {r["slug"]: r["is_hit"] for r in response.json()["results"]}
        assert by_slug[hit.slug] is True
        assert by_slug[plain.slug] is False

    def test_сортировка_bestsellers_ставит_непроданное_в_конец(self, client):
        plain, sold = make_product("A"), make_product("B")
        sell(sold, "5")
        rebuild_sales_stats()

        response = client.get(reverse("catalog_api:product-list"), {"sort": "bestsellers"})

        assert [r["slug"] for r in response.json()["results"]] == [sold.slug, plain.slug]


class TestРучныеХиты:
    """Подборка магазина: галочка «Хит продаж», пока 1С не присылает продажи."""

    def test_ручной_хит_попадает_в_блок(self, client):
        product = make_product("A", is_hit_manual=True)
        make_product("B")

        response = client.get(reverse("catalog_api:bestsellers"))

        results = response.json()["results"]
        assert [r["slug"] for r in results] == [product.slug]
        assert results[0]["is_hit"] is True

    def test_настоящие_продажи_идут_первыми(self, client, settings):
        """Ручная отметка дополняет рейтинг, а не подменяет его."""
        settings.SALES_HIT_MIN_QUANTITY = 1
        sold = make_product("A")
        by_hand = make_product("B", is_hit_manual=True)
        sell(sold, "5")
        rebuild_sales_stats()

        response = client.get(reverse("catalog_api:bestsellers"))

        assert [r["slug"] for r in response.json()["results"]] == [sold.slug, by_hand.slug]

    def test_снятая_галочка_убирает_из_блока(self, client):
        product = make_product("A", is_hit_manual=True)

        Product.objects.filter(pk=product.pk).update(is_hit_manual=False)

        response = client.get(reverse("catalog_api:bestsellers"))
        assert response.json()["results"] == []

    def test_скрытый_товар_ручным_хитом_не_станет(self, client):
        make_product("A", is_hit_manual=True, is_active=False)

        response = client.get(reverse("catalog_api:bestsellers"))

        assert response.json()["results"] == []


class TestОтметкаХитаВАдминке:
    """Галочка на скрытом товаре не работает — админка обязана сказать об этом.

    Молчаливое «Отмечено хитами: 12» при пустом блоке на главной — ровно тот
    случай, когда интерфейс отчитался об успехе, а результата нет.
    """

    @pytest.fixture
    def staff_client(self, client, django_user_model):
        user = django_user_model.objects.create_superuser(
            phone="+79001112255", email="hits@proff58.ru", password="pass12345"
        )
        client.force_login(user)
        return client

    def _mark(self, staff_client, products):
        return staff_client.post(
            reverse("admin:catalog_product_changelist"),
            {
                "action": "action_mark_hit",
                "_selected_action": [str(p.pk) for p in products],
            },
            follow=True,
        )

    def test_предупреждает_о_скрытых(self, staff_client):
        visible = make_product("A")
        hidden = make_product("B", is_active=False)

        response = self._mark(staff_client, [visible, hidden])

        texts = [str(m) for m in response.context["messages"]]
        assert any("Отмечено хитами: 2" in t for t in texts)
        warning = next(t for t in texts if "скрыты" in t)
        assert "1" in warning and hidden.name in warning

    def test_молчит_когда_все_видимы(self, staff_client):
        response = self._mark(staff_client, [make_product("A"), make_product("B")])

        texts = [str(m) for m in response.context["messages"]]
        assert not any("скрыт" in t for t in texts)

    def test_отметка_в_карточке_скрытого_предупреждает(self, rf, django_user_model):
        """Тот же случай, но галочку ставят в самой карточке, а не действием списка."""
        hidden = make_product("B", is_active=False, is_hit_manual=True)
        request = rf.post("/admin/catalog/product/")
        request.user = django_user_model.objects.create_superuser(
            phone="+79001112266", email="card@proff58.ru", password="pass12345"
        )
        request.session = {}
        request._messages = FallbackStorage(request)
        form = SimpleNamespace(changed_data=["is_hit_manual"])

        site._registry[Product].save_model(request, hidden, form, change=True)

        assert any("скрыт с витрины" in str(m) for m in request._messages)
