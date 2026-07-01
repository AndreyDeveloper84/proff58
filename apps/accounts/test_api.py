"""Тесты account API (#325, #327, #328)."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(phone="+79001112233", password="pass123", full_name="Тест")


# ═══════════ #327 Регистрация ═══════════


@pytest.mark.django_db
def test_register(client):
    resp = client.post(
        "/api/account/register/",
        {"phone": "+79009999999", "password": "pass123", "full_name": "Новый"},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.json()["phone"] == "+79009999999"
    assert User.objects.filter(phone="+79009999999").exists()


@pytest.mark.django_db
def test_register_duplicate_phone(client, user):
    resp = client.post(
        "/api/account/register/",
        {"phone": "+79001112233", "password": "pass123"},
        format="json",
    )
    assert resp.status_code == 400


# ═══════════ #325 Вход/выход ═══════════


@pytest.mark.django_db
def test_login(client, user):
    resp = client.post(
        "/api/account/login/",
        {"phone": "+79001112233", "password": "pass123"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.json()["phone"] == "+79001112233"


@pytest.mark.django_db
def test_login_wrong_password(client, user):
    resp = client.post(
        "/api/account/login/",
        {"phone": "+79001112233", "password": "wrong"},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_logout(client, user):
    client.force_authenticate(user=user)
    resp = client.post("/api/account/logout/")
    assert resp.status_code == 200


# ═══════════ #328 Профиль ═══════════


@pytest.mark.django_db
def test_me_authenticated(client, user):
    client.force_authenticate(user=user)
    resp = client.get("/api/account/me/")
    assert resp.status_code == 200
    assert resp.json()["phone"] == "+79001112233"


@pytest.mark.django_db
def test_me_anonymous(client):
    resp = client.get("/api/account/me/")
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_me_update(client, user):
    client.force_authenticate(user=user)
    resp = client.patch(
        "/api/account/me/",
        {"full_name": "Новое Имя", "email": "new@test.ru"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Новое Имя"


# ═══════════ #329 Избранное ═══════════


@pytest.mark.django_db
def test_wishlist_add_and_list(client, user):
    from apps.catalog.models import Product, ProductStatus

    p = Product.objects.create(
        name="Дрель", slug="wish-drel", price=1000, status=ProductStatus.PUBLISHED, is_active=True
    )
    client.force_authenticate(user=user)
    resp = client.post("/api/account/wishlist/", {"product_id": p.id}, format="json")
    assert resp.status_code == 201

    resp = client.get("/api/account/wishlist/")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["product_slug"] == "wish-drel"


@pytest.mark.django_db
def test_wishlist_delete(client, user):
    from apps.catalog.models import Product, ProductStatus

    p = Product.objects.create(
        name="Пила", slug="wish-pila", price=500, status=ProductStatus.PUBLISHED, is_active=True
    )
    client.force_authenticate(user=user)
    client.post("/api/account/wishlist/", {"product_id": p.id}, format="json")
    resp = client.delete("/api/account/wishlist/", {"product_id": p.id}, format="json")
    assert resp.status_code == 200
    assert client.get("/api/account/wishlist/").json() == []


# ═══════════ #326 OTP Login ═══════════


@pytest.mark.django_db
def test_otp_login(client, user):
    from django.core.cache import cache

    user.max_chat_id = 555
    user.save()
    cache.set("max_otp:555", {"otp": "1234", "user_id": user.pk, "attempts": 0}, timeout=300)

    resp = client.post(
        "/api/account/otp-login/",
        {"phone": "+79001112233", "otp": "1234"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.json()["phone"] == "+79001112233"
    cache.clear()


@pytest.mark.django_db
def test_otp_login_wrong_code(client, user):
    from django.core.cache import cache

    user.max_chat_id = 556
    user.save()
    cache.set("max_otp:556", {"otp": "1234", "user_id": user.pk, "attempts": 0}, timeout=300)

    resp = client.post(
        "/api/account/otp-login/",
        {"phone": "+79001112233", "otp": "0000"},
        format="json",
    )
    assert resp.status_code == 400
    cache.clear()


@pytest.mark.django_db
def test_otp_login_no_max(client, user):
    resp = client.post(
        "/api/account/otp-login/",
        {"phone": "+79001112233", "otp": "1234"},
        format="json",
    )
    assert resp.status_code == 400
    assert "MAX" in resp.json()["detail"]


# ═══════════ #341 Привязка гостевых заказов ═══════════


@pytest.mark.django_db
def test_claim_guest_orders_on_login(client):
    from apps.orders.models import Order

    User.objects.create_user(phone="+79005550001", password="pass")
    Order.objects.create(order_number="П-GUEST-1", customer_phone="+79005550001")

    resp = client.post(
        "/api/account/login/", {"phone": "+79005550001", "password": "pass"}, format="json"
    )
    assert resp.status_code == 200
    assert resp.json().get("claimed_orders", 0) == 1


# ═══════════ #344 Удаление аккаунта ═══════════


@pytest.mark.django_db
def test_delete_account(client):
    u = User.objects.create_user(phone="+79005550002", password="pass", full_name="Удаляемый")
    client.force_authenticate(user=u)
    resp = client.post("/api/account/delete/")
    assert resp.status_code == 200
    u.refresh_from_db()
    assert u.is_active is False
    assert u.full_name == ""


# ═══════════ #343 Смена телефона ═══════════


@pytest.mark.django_db
def test_change_phone(client, user):
    client.force_authenticate(user=user)
    resp = client.post("/api/account/change-phone/", {"new_phone": "+79005550003"}, format="json")
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.phone == "+79005550003"
    assert user.max_chat_id is None
