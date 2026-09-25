"""Регистрация и переход в организацию (вход по e-mail).

Витрина различает частное лицо и организацию с самого входа: организация
указывает реквизиты сразу и получает счета без ожидания проверки — флаг
верификации остаётся отметкой менеджера и на возможности не влияет (ADR-0013).
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import Profile

User = get_user_model()

PASSWORD = "StrongPass2026"


@pytest.fixture
def client():
    return APIClient()


def register(client, **overrides):
    body = {"email": "company@proff58.ru", "password": PASSWORD}
    body.update(overrides)
    return client.post("/api/account/register/", body, format="json")


# ── регистрация ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_register_company_saves_requisites(client):
    resp = register(
        client,
        customer_type="b2b",
        company_name="ООО «Профессионал»",
        inn="5836123456",
        kpp="583601001",
    )

    assert resp.status_code == 201, resp.json()
    user = User.objects.get(email="company@proff58.ru")
    assert user.customer_type == "b2b"
    profile = Profile.objects.get(user=user)
    assert profile.company_name == "ООО «Профессионал»"
    assert profile.inn == "5836123456"
    assert profile.kpp == "583601001"


@pytest.mark.django_db
def test_company_gets_access_without_manager_approval(client):
    """Ждать проверки не нужно — счета и реквизиты доступны сразу."""
    register(
        client,
        customer_type="b2b",
        company_name="ООО «Профессионал»",
        inn="5836123456",
        kpp="583601001",
    )

    me = client.get("/api/account/me/")

    assert me.status_code == 200
    assert me.json()["customer_type"] == "b2b"


@pytest.mark.django_db
def test_register_company_without_inn_rejected(client):
    resp = register(client, customer_type="b2b", company_name="ООО «Профессионал»")

    assert resp.status_code == 400
    assert not User.objects.filter(email="company@proff58.ru").exists()


@pytest.mark.django_db
def test_register_company_requires_kpp_for_legal_entity(client):
    """ИНН из 10 цифр — организация, у неё КПП есть всегда."""
    resp = register(
        client, customer_type="b2b", company_name="ООО «Профессионал»", inn="5836123456"
    )

    assert resp.status_code == 400


@pytest.mark.django_db
def test_register_entrepreneur_without_kpp_allowed(client):
    """ИНН из 12 цифр — ИП: КПП у него не существует."""
    resp = register(client, customer_type="b2b", company_name="ИП Петров", inn="583601234567")

    assert resp.status_code == 201, resp.json()
    assert Profile.objects.get(user__email="company@proff58.ru").kpp == ""


@pytest.mark.django_db
def test_register_private_person_has_no_company_profile(client):
    resp = register(client, customer_type="b2c")

    assert resp.status_code == 201
    user = User.objects.get(email="company@proff58.ru")
    assert user.customer_type == "b2c"
    assert not Profile.objects.filter(user=user).exists()


# ── переход в организацию из кабинета ──────────────────────────────────


@pytest.fixture
def person(db, client):
    register(client, email="person@proff58.ru", customer_type="b2c")
    return User.objects.get(email="person@proff58.ru")


@pytest.mark.django_db
def test_private_person_becomes_company(client, person):
    resp = client.patch(
        "/api/account/me/",
        {
            "customer_type": "b2b",
            "profile": {
                "company_name": "ООО «Профессионал»",
                "inn": "5836123456",
                "kpp": "583601001",
            },
        },
        format="json",
    )

    assert resp.status_code == 200, resp.json()
    person.refresh_from_db()
    assert person.customer_type == "b2b"
    assert person.profile.inn == "5836123456"


@pytest.mark.django_db
def test_switch_to_company_without_requisites_rejected(client, person):
    """Организация без реквизитов — пустой кабинет и счёт не из чего выпустить."""
    resp = client.patch("/api/account/me/", {"customer_type": "b2b"}, format="json")

    assert resp.status_code == 400
    person.refresh_from_db()
    assert person.customer_type == "b2c"


@pytest.mark.django_db
def test_company_can_switch_back_to_private_person(client, person):
    client.patch(
        "/api/account/me/",
        {
            "customer_type": "b2b",
            "profile": {"company_name": "ООО «П»", "inn": "5836123456", "kpp": "583601001"},
        },
        format="json",
    )

    resp = client.patch("/api/account/me/", {"customer_type": "b2c"}, format="json")

    assert resp.status_code == 200, resp.json()
    person.refresh_from_db()
    assert person.customer_type == "b2c"


# ── e-mail как логин ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_cannot_take_email_of_another_user(client, person):
    User.objects.create_user(email="taken@proff58.ru", password=PASSWORD)

    resp = client.patch("/api/account/me/", {"email": "taken@proff58.ru"}, format="json")

    assert resp.status_code == 400


@pytest.mark.django_db
def test_cannot_clear_own_email(client, person):
    """Стерев почту, человек лишился бы единственного способа войти паролем."""
    resp = client.patch("/api/account/me/", {"email": ""}, format="json")

    assert resp.status_code == 400


@pytest.mark.django_db
def test_login_is_case_insensitive(client):
    User.objects.create_user(email="Mixed@Proff58.ru", password=PASSWORD)

    resp = client.post(
        "/api/account/login/",
        {"email": "mixed@proff58.ru", "password": PASSWORD},
        format="json",
    )

    assert resp.status_code == 200


@pytest.mark.django_db
def test_max_account_without_email_still_possible(client):
    """Из MAX человек приходит с телефоном и без почты — такой аккаунт валиден."""
    user = User.objects.create_user(phone="+79005550099", password=None)

    assert user.pk is not None
    assert user.email == ""
