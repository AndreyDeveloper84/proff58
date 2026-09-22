"""Приёмка модерации отзывов перед включением модуля (DRF-2295).

Модуль #573 уже умеет всё нужное; здесь зафиксированы сценарии из приёмки,
которых в test_reviews.py не было: покупатель не управляет модерацией и не
видит чужое, полный цикл «отклонить с причиной → автор видит причину → одобрить
→ публично виден» через настоящую админку, права на массовые действия,
и согласованное поведение при выключенном модуле, включая публичный эндпоинт
товара и боевой рычаг включения в «Настройках сайта».
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductStatus
from apps.core.models import SiteSettings
from apps.orders.models import FulfillmentStatus, Order, OrderItem
from apps.reviews import services
from apps.reviews.admin import ReviewAdmin
from apps.reviews.models import Review, ReviewStatus

User = get_user_model()

ACCOUNT_URL = "/api/account/reviews/"
PUBLIC_URL = "/api/reviews/product/drel-mod/"


@pytest.fixture(autouse=True)
def _reviews_on(settings):
    settings.FEATURES = {**getattr(settings, "FEATURES", {}), "reviews": True}


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def товар(db):
    cat = Category.add_root(name="Инструмент", slug="instr-mod")
    return Product.objects.create(
        category=cat,
        name="Дрель",
        slug="drel-mod",
        unit="шт",
        price=Decimal("1000.00"),
        status=ProductStatus.PUBLISHED,
        is_active=True,
    )


def _покупатель(phone, name):
    return User.objects.create_user(phone=phone, password="pass12345", full_name=name)


def _заказ(user, товар, number):
    order = Order.objects.create(
        order_number=number,
        user=user,
        fulfillment_status=FulfillmentStatus.COMPLETED,
        customer_name=user.full_name,
    )
    OrderItem.objects.create(
        order=order,
        product=товар,
        name=товар.name,
        price_final=товар.price,
        quantity=1,
        line_total=товар.price,
    )
    return order


def _отзыв(user, number, text="Хороший инструмент"):
    return services.create_review(
        user=user,
        order_number=number,
        product_rating=5,
        delivery_rating=4,
        shop_rating=5,
        text=text,
    )


@pytest.fixture
def автор(db, товар):
    user = _покупатель("+79001113301", "Иван Петров")
    _заказ(user, товар, "MOD-1")
    return user


@pytest.fixture
def отзыв(автор):
    return _отзыв(автор, "MOD-1")


@pytest.fixture
def модератор(db):
    return User.objects.create_superuser(phone="+79001113399", password="pwd12345")


def _change_url(отзыв):
    return reverse("admin:reviews_review_change", args=[отзыв.pk])


def _approve_bulk(client, отзыв):
    return client.post(
        reverse("admin:reviews_review_changelist"),
        {"action": "approve_selected", "_selected_action": [str(отзыв.pk)], "index": "0"},
    )


# ═══════════ покупатель не управляет модерацией ═══════════


@pytest.mark.django_db
@pytest.mark.parametrize("метод", ["patch", "put", "delete"])
def test_автор_не_может_менять_или_удалять_отзыв_через_api(api, автор, отзыв, метод):
    api.force_authenticate(user=автор)
    resp = getattr(api, метод)(ACCOUNT_URL, {"status": "approved"}, format="json")
    assert resp.status_code == 405
    отзыв.refresh_from_db()
    assert отзыв.status == ReviewStatus.PENDING


@pytest.mark.django_db
def test_статус_в_теле_создания_игнорируется(api, автор):
    api.force_authenticate(user=автор)
    resp = api.post(
        ACCOUNT_URL,
        {
            "order_number": "MOD-1",
            "product_rating": 5,
            "delivery_rating": 5,
            "shop_rating": 5,
            "status": "approved",
            "rejection_reason": "",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    assert resp.json()["status"] == "pending"
    assert Review.objects.get().status == ReviewStatus.PENDING


@pytest.mark.django_db
def test_чужой_отзыв_не_виден_в_моих(api, автор, отзыв, товар):
    другой = _покупатель("+79001113302", "Пётр Сидоров")
    _заказ(другой, товар, "MOD-2")
    api.force_authenticate(user=другой)

    assert api.get(ACCOUNT_URL).json()["count"] == 0
    assert api.get(ACCOUNT_URL + "?order=MOD-1").json()["count"] == 0


# ═══════════ полный цикл модерации через настоящую админку ═══════════


@pytest.mark.django_db
def test_отклонить_без_причины_нельзя(client, модератор, отзыв):
    client.force_login(модератор)
    resp = client.post(_change_url(отзыв), {"status": "rejected", "rejection_reason": " "})
    assert resp.status_code == 200  # форма вернулась с ошибкой, редиректа нет
    assert "Укажите причину отклонения" in resp.content.decode()
    отзыв.refresh_from_db()
    assert отзыв.status == ReviewStatus.PENDING
    assert отзыв.moderated_at is None


@pytest.mark.django_db
def test_цикл_отклонить_с_причиной_затем_одобрить(api, client, модератор, автор, отзыв):
    client.force_login(модератор)
    api.force_authenticate(user=автор)

    # до модерации: публично пусто, автор видит «на модерации»
    assert api.get(PUBLIC_URL).json()["summary"]["count"] == 0
    assert api.get(ACCOUNT_URL).json()["results"][0]["status"] == "pending"

    # отклонить с индивидуальной причиной
    resp = client.post(
        _change_url(отзыв),
        {"status": "rejected", "rejection_reason": "Текст не про товар."},
    )
    assert resp.status_code == 302
    отзыв.refresh_from_db()
    assert отзыв.status == ReviewStatus.REJECTED
    assert отзыв.moderated_at is not None
    assert api.get(PUBLIC_URL).json()["summary"]["count"] == 0  # отклонённый не публикуется
    мой = api.get(ACCOUNT_URL).json()["results"][0]
    assert мой["status"] == "rejected"
    assert мой["rejection_reason"] == "Текст не про товар."  # причина доступна автору

    # одобрить массовым действием из списка
    assert _approve_bulk(client, отзыв).status_code == 302
    отзыв.refresh_from_db()
    assert отзыв.status == ReviewStatus.APPROVED
    assert отзыв.rejection_reason == ""
    public = api.get(PUBLIC_URL).json()
    assert public["summary"] == {"product_rating_avg": 5.0, "count": 1}
    assert public["results"][0]["author_name"] == "Иван П."
    assert api.get(ACCOUNT_URL).json()["results"][0]["status"] == "approved"

    # повторное «Одобрить» — ничего не переписывает
    первое = отзыв.moderated_at
    _approve_bulk(client, отзыв)
    отзыв.refresh_from_db()
    assert отзыв.moderated_at == первое


@pytest.mark.django_db
def test_одобрение_из_карточки_стирает_причину_отклонения(api, client, модератор, автор, отзыв):
    client.force_login(модератор)
    api.force_authenticate(user=автор)
    client.post(_change_url(отзыв), {"status": "rejected", "rejection_reason": "Спам."})

    resp = client.post(_change_url(отзыв), {"status": "approved", "rejection_reason": "Спам."})
    assert resp.status_code == 302
    отзыв.refresh_from_db()
    assert отзыв.status == ReviewStatus.APPROVED
    assert отзыв.rejection_reason == ""
    assert api.get(ACCOUNT_URL).json()["results"][0]["rejection_reason"] == ""


@pytest.mark.django_db
def test_сотрудник_без_права_изменения_не_модерирует(client, отзыв):
    наблюдатель = User.objects.create_user(phone="+79001113398", password="pwd12345", is_staff=True)
    наблюдатель.user_permissions.set(Permission.objects.filter(codename="view_review"))
    client.force_login(наблюдатель)

    # массовых действий для него нет вообще — Django просто показывает список
    assert _approve_bulk(client, отзыв).status_code == 200
    # карточка на POST без права изменения — 403
    resp = client.post(_change_url(отзыв), {"status": "approved", "rejection_reason": ""})
    assert resp.status_code == 403
    отзыв.refresh_from_db()
    assert отзыв.status == ReviewStatus.PENDING
    assert отзыв.moderated_at is None

    request = RequestFactory().get("/")
    request.user = наблюдатель
    actions = ReviewAdmin(Review, AdminSite()).get_actions(request)
    assert "approve_selected" not in actions and "reject_selected" not in actions


# ═══════════ выключенный модуль ═══════════


@pytest.mark.django_db
def test_при_выключенном_модуле_публичный_список_товара_404(api, отзыв, settings):
    Review.objects.filter(pk=отзыв.pk).update(status=ReviewStatus.APPROVED)
    assert api.get(PUBLIC_URL).json()["summary"]["count"] == 1

    settings.FEATURES = {**settings.FEATURES, "reviews": False}
    resp = api.get(PUBLIC_URL)
    assert resp.status_code == 404
    assert resp.json()["code"] == "reviews_disabled"


@pytest.mark.django_db
def test_боевой_рычаг_настройки_сайта_без_override(api, автор, отзыв, settings):
    """На проде override в FEATURES нет: включает администратор галочкой в «Настройках сайта»."""
    settings.FEATURES = {k: v for k, v in settings.FEATURES.items() if k != "reviews"}
    Review.objects.filter(pk=отзыв.pk).update(status=ReviewStatus.APPROVED)
    api.force_authenticate(user=автор)

    assert SiteSettings.get_solo().reviews_enabled is False  # по умолчанию выключено
    assert api.get(PUBLIC_URL).status_code == 404
    assert api.get(ACCOUNT_URL).status_code == 404
    # флаг проверяется раньше товара: существование slug через отзывы не светится
    assert api.get("/api/reviews/product/net-takogo/").json()["code"] == "reviews_disabled"

    SiteSettings.objects.filter(pk=1).update(reviews_enabled=True)
    assert api.get(PUBLIC_URL).json()["summary"]["count"] == 1
    assert api.get(ACCOUNT_URL).json()["count"] == 1
