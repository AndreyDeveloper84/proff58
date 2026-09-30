"""DRF-2497: «подтвердите, что это вы» перед удалением аккаунта и сменой e-mail.

Угроза: украденная или оставленная открытой сессия. У кого пароль — подтверждает
паролем; у кого нет (MAX, VK ID, Яндекс ID) — свежим входом своим способом.
"""

from __future__ import annotations

import time
from unittest import mock

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts import reauth

User = get_user_model()
MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"  # MAX и OAuth входят им
EMAIL_BACKEND = "apps.accounts.auth_backends.EmailBackend"  # вход по паролю


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def passwordless(db):
    return User.objects.create_user(phone="+79005550101", password=None, full_name="Без пароля")


@pytest.fixture
def with_password(db):
    return User.objects.create_user(
        phone="+79005550102", email="owner@test.ru", password="pass123", full_name="С паролем"
    )


def _delete(client, **data):
    return client.post("/api/account/delete/", data, format="json")


def _shift_clock(seconds: float):
    """Часы модуля reauth «через N секунд»."""
    now = time.time()
    return mock.patch("apps.accounts.reauth.time.time", return_value=now + seconds)


# ═══════════ Отметка о свежем входе ═══════════


@pytest.mark.django_db
def test_вход_паролем_ставит_отметку_и_её_видно_в_me(client, with_password):
    resp = client.post(
        "/api/account/login/", {"email": "owner@test.ru", "password": "pass123"}, format="json"
    )
    assert resp.status_code == 200
    me = client.get("/api/account/me/").json()
    assert me["reauth_valid_until"] is not None
    assert client.session[reauth.SESSION_KEY]["method"] == reauth.PASSWORD


@pytest.mark.django_db
def test_без_сессионного_входа_отметки_нет(client, passwordless):
    client.force_authenticate(user=passwordless)
    assert client.get("/api/account/me/").json()["reauth_valid_until"] is None


@pytest.mark.django_db
def test_вход_через_max_или_oauth_ставит_внешнюю_отметку(client, passwordless):
    client.force_login(passwordless, backend=MODEL_BACKEND)
    assert client.session[reauth.SESSION_KEY]["method"] == reauth.EXTERNAL


# ═══════════ Удаление без пароля ═══════════


@pytest.mark.django_db
def test_без_пароля_одной_сессии_мало(client, passwordless):
    client.force_authenticate(user=passwordless)
    resp = _delete(client)
    assert resp.status_code == 403
    assert resp.json()["code"] == "reauth_required"
    passwordless.refresh_from_db()
    assert passwordless.is_active is True


@pytest.mark.django_db
def test_без_пароля_свежий_вход_разрешает(client, passwordless):
    client.force_login(passwordless, backend=MODEL_BACKEND)
    assert _delete(client).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize(("shift", "allowed"), [(599, True), (601, False), (-60, False)])
def test_окно_подтверждения(client, passwordless, shift, allowed):
    client.force_login(passwordless, backend=MODEL_BACKEND)
    with _shift_clock(shift):
        resp = _delete(client)
    assert (resp.status_code == 200) is allowed


# ═══════════ Удаление с паролем — как раньше ═══════════


@pytest.mark.django_db
def test_с_паролем_внешний_вход_не_заменяет_пароль(client, with_password):
    """Открытая сессия Яндекса/VK/MAX владельца в браузере — не повод удалить без пароля."""
    client.force_login(with_password, backend=MODEL_BACKEND)
    resp = _delete(client)
    assert resp.status_code == 403 and resp.json()["code"] == "reauth_required"
    assert _delete(client, password="pass123").status_code == 200


@pytest.mark.django_db
def test_с_паролем_свежий_вход_по_паролю_достаточен(client, with_password):
    client.force_login(with_password, backend=EMAIL_BACKEND)
    assert _delete(client).status_code == 200


# ═══════════ Счётчик неверных паролей (общий) ═══════════


@pytest.mark.django_db
def test_неверные_пароли_блокируют_все_места_проверки(client, with_password):
    client.force_authenticate(user=with_password)
    # Пять неудач в разных местах — один счётчик.
    for _ in range(2):
        assert _delete(client, password="нет").status_code == 400
    for _ in range(2):
        resp = client.patch(
            "/api/account/me/", {"email": "x@test.ru", "current_password": "нет"}, format="json"
        )
        assert resp.status_code == 400
    assert (
        client.post("/api/account/reauth/password/", {"password": "нет"}, format="json").status_code
        == 400
    )
    # Дальше отказ даже с верным паролем.
    resp = _delete(client, password="pass123")
    assert resp.status_code == 429 and resp.json()["code"] == "reauth_locked"
    with_password.refresh_from_db()
    assert with_password.is_active is True


@pytest.mark.django_db
def test_верный_пароль_сбрасывает_счётчик(client, with_password):
    client.force_authenticate(user=with_password)
    for _ in range(4):
        _delete(client, password="нет")
    assert (
        client.post(
            "/api/account/reauth/password/", {"password": "pass123"}, format="json"
        ).status_code
        == 200
    )
    for _ in range(4):
        assert _delete(client, password="нет").status_code in (200, 400)


# ═══════════ Смена e-mail ═══════════


@pytest.mark.django_db
def test_смена_имени_без_подтверждения(client, passwordless):
    client.force_authenticate(user=passwordless)
    resp = client.patch("/api/account/me/", {"full_name": "Новое"}, format="json")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_смена_email_без_пароля_требует_свежий_вход(client, passwordless):
    client.force_authenticate(user=passwordless)
    resp = client.patch("/api/account/me/", {"email": "thief@evil.ru"}, format="json")
    assert resp.status_code == 403 and resp.json()["code"] == "reauth_required"
    passwordless.refresh_from_db()
    assert passwordless.email == ""

    client.force_login(passwordless, backend=MODEL_BACKEND)
    resp = client.patch("/api/account/me/", {"email": "me@test.ru"}, format="json")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_смена_email_с_паролем(client, with_password):
    client.force_authenticate(user=with_password)
    assert (
        client.patch("/api/account/me/", {"email": "new@test.ru"}, format="json").status_code == 403
    )
    resp = client.patch(
        "/api/account/me/", {"email": "new@test.ru", "current_password": "нет"}, format="json"
    )
    assert resp.status_code == 400
    resp = client.patch(
        "/api/account/me/", {"email": "new@test.ru", "current_password": "pass123"}, format="json"
    )
    assert resp.status_code == 200 and resp.json()["email"] == "new@test.ru"


@pytest.mark.django_db
def test_тот_же_email_в_другом_регистре_не_смена(client, with_password):
    client.force_authenticate(user=with_password)
    resp = client.patch("/api/account/me/", {"email": "OWNER@test.ru"}, format="json")
    assert resp.status_code == 200


# ═══════════ Подтверждение паролем ═══════════


@pytest.mark.django_db
def test_подтверждение_паролем_меняет_ключ_сессии(client, with_password):
    client.force_login(with_password, backend=MODEL_BACKEND)
    before = client.session.session_key
    resp = client.post("/api/account/reauth/password/", {"password": "pass123"}, format="json")
    assert resp.status_code == 200 and resp.json()["reauth_valid_until"]
    assert client.session.session_key != before
    # Старая кука больше не пускает.
    stale = APIClient()
    stale.cookies[settings.SESSION_COOKIE_NAME] = before
    assert stale.get("/api/account/me/").status_code in (401, 403)


@pytest.mark.django_db
def test_подтверждение_паролем_у_беспарольного(client, passwordless):
    client.force_authenticate(user=passwordless)
    resp = client.post("/api/account/reauth/password/", {"password": "x"}, format="json")
    assert resp.status_code == 400


# ═══════════ Вход другого пользователя в той же сессии ═══════════


@pytest.mark.django_db
def test_чужой_вход_не_освежает_жертву(client, passwordless, with_password):
    client.force_login(passwordless, backend=MODEL_BACKEND)
    client.post(
        "/api/account/login/", {"email": "owner@test.ru", "password": "pass123"}, format="json"
    )
    # Сессия теперь у вошедшего; удаление касается только его.
    assert client.get("/api/account/me/").json()["id"] == with_password.pk
    assert _delete(client).status_code == 200
    passwordless.refresh_from_db()
    with_password.refresh_from_db()
    assert passwordless.is_active is True and with_password.is_active is False


# ═══════════ Лимит удаления по пользователю ═══════════


@pytest.mark.django_db
def test_лимит_удаления_по_пользователю_а_не_по_ip(client, with_password):
    rates = {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "account_delete": "2/hour"}
    with override_settings(
        REST_FRAMEWORK={**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": rates}
    ):
        client.force_authenticate(user=with_password)
        codes = [
            client.post(
                "/api/account/delete/",
                {"password": "нет"},
                format="json",
                REMOTE_ADDR=f"10.0.0.{i}",
            ).status_code
            for i in range(3)
        ]
    assert codes == [400, 400, 429]


# ═══════════ Поправки по ревью кода ═══════════


@pytest.mark.django_db
def test_смена_телефона_в_общем_счётчике(client, with_password):
    client.force_authenticate(user=with_password)
    for _ in range(5):
        resp = client.post(
            "/api/account/change-phone/",
            {"password": "нет", "new_phone": "+79005550199"},
            format="json",
        )
        assert resp.status_code == 400
    assert _delete(client, password="pass123").status_code == 429


@pytest.mark.django_db
@pytest.mark.parametrize("bad", [123, {"x": 1}, ["pass123"]])
def test_пароль_не_строкой_не_роняет_сервер(client, with_password, bad):
    client.force_authenticate(user=with_password)
    assert _delete(client, password=bad).status_code == 403
    resp = client.post("/api/account/reauth/password/", {"password": bad}, format="json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_тело_массивом_не_роняет_сервер(client, with_password):
    client.force_authenticate(user=with_password)
    resp = client.post("/api/account/delete/", ["pass123"], format="json")
    assert resp.status_code == 403
