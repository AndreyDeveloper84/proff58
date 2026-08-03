"""Cookie-маркер входа (AuthMarkerCookieMiddleware).

Фронт по этому маркеру отсекает заведомых гостей от личного кабинета, не сходив
в Django. Отдельная cookie нужна потому, что `sessionid` есть и у анонимного
посетителя (гостевая корзина), — по ней «вошёл ли человек» не определить.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.middleware import AUTH_MARKER_COOKIE

User = get_user_model()


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="marker@proff58.ru", password="StrongPass2026", full_name="Ю"
    )


@pytest.mark.django_db
def test_guest_gets_no_marker(client):
    resp = client.get("/api/cart/")

    assert AUTH_MARKER_COOKIE not in resp.cookies


@pytest.mark.django_db
def test_login_sets_marker(client, user):
    resp = client.post(
        "/api/account/login/",
        {"email": user.email, "password": "StrongPass2026"},
        format="json",
    )

    assert resp.status_code == 200
    marker = resp.cookies[AUTH_MARKER_COOKIE]
    assert marker.value == "1"
    assert marker["httponly"]


@pytest.mark.django_db
def test_marker_is_not_reissued_on_every_request(client, user):
    """Уже есть — не трогаем: лишний Set-Cookie на каждый запрос ни к чему."""
    client.post(
        "/api/account/login/",
        {"email": user.email, "password": "StrongPass2026"},
        format="json",
    )

    resp = client.get("/api/account/me/")

    assert resp.status_code == 200
    assert AUTH_MARKER_COOKIE not in resp.cookies


@pytest.mark.django_db
def test_logout_clears_marker(client, user):
    client.post(
        "/api/account/login/",
        {"email": user.email, "password": "StrongPass2026"},
        format="json",
    )

    resp = client.post("/api/account/logout/", format="json")

    assert AUTH_MARKER_COOKIE in resp.cookies
    assert resp.cookies[AUTH_MARKER_COOKIE].value == ""


@pytest.mark.django_db
def test_stale_marker_without_session_is_cleared(client):
    """Сессия истекла, а маркер остался — снимаем, иначе фронт гоняет по кругу."""
    client.cookies[AUTH_MARKER_COOKIE] = "1"

    resp = client.get("/api/cart/")

    assert resp.cookies[AUTH_MARKER_COOKIE].value == ""
