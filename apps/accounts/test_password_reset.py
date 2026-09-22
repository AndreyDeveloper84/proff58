"""Восстановление пароля покупателя по e-mail (DRF-2298).

Ответ запроса не зависит от адреса; транспорт проверяется до поиска
пользователя; токен одноразовый и срочный; чужой пароль не меняется; старые
сессии после смены не действуют; MAX-аккаунт без пароля и сотрудники админки
через публичную форму пароль не получают.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import mail
from django.test import override_settings
from rest_framework.test import APIClient

from apps.notifications.channels import RetryableChannelError

User = get_user_model()

REQUEST_URL = "/api/account/password-reset/"
CONFIRM_URL = "/api/account/password-reset/confirm/"
LINK_RE = re.compile(r"https://proff58\.ru/account/reset-password\?uid=([\w-]+)&token=([\w-]+)")


@pytest.fixture(autouse=True)
def _site(settings):
    settings.SITE_URL = "https://proff58.ru"
    settings.DEFAULT_FROM_EMAIL = "site@proff58.ru"


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def покупатель(db):
    return User.objects.create_user(
        phone="+79001110001", email="Buyer@proff58.ru", password="OldStrong2026", full_name="Иван"
    )


def _запросить(api, email="buyer@proff58.ru"):
    return api.post(REQUEST_URL, {"email": email}, format="json")


def _ссылка():
    assert len(mail.outbox) == 1
    m = LINK_RE.search(mail.outbox[0].body)
    assert m, mail.outbox[0].body
    return m.group(1), m.group(2)


def _подтвердить(api, uid, token, password="NewStrong2027"):
    return api.post(
        CONFIRM_URL, {"uid": uid, "token": token, "new_password": password}, format="json"
    )


# ═══════════ запрос письма ═══════════


@pytest.mark.django_db
def test_известный_адрес_получает_письмо_без_пароля(api, покупатель, caplog):
    with caplog.at_level(logging.INFO):
        resp = _запросить(api)
    assert resp.status_code == 200
    письмо = mail.outbox[0]
    assert письмо.to == ["Buyer@proff58.ru"]
    uid, token = _ссылка()
    assert "OldStrong2026" not in письмо.body
    assert "1 ч" in письмо.body
    # В логах нет ни токена, ни uid.
    assert token not in caplog.text and uid not in caplog.text


@pytest.mark.django_db
def test_неизвестный_адрес_получает_тот_же_ответ(api, покупатель):
    known = _запросить(api).json()
    mail.outbox.clear()
    unknown = _запросить(api, "nobody@proff58.ru")
    assert unknown.status_code == 200 and unknown.json() == known
    assert mail.outbox == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "подготовка",
    ["max_only", "inactive", "staff"],
)
def test_кому_письмо_не_шлём(api, подготовка):
    if подготовка == "max_only":
        User.objects.create_user(phone="+79001110002", email="max@proff58.ru", password=None)
    elif подготовка == "inactive":
        u = User.objects.create_user(
            phone="+79001110003", email="max@proff58.ru", password="OldStrong2026"
        )
        u.is_active = False
        u.save(update_fields=["is_active"])
    else:
        User.objects.create_user(
            phone="+79001110004", email="max@proff58.ru", password="OldStrong2026", is_staff=True
        )
    resp = _запросить(api, "max@proff58.ru")
    assert resp.status_code == 200 and resp.json()["detail"].startswith("Если адрес")
    assert mail.outbox == []


@pytest.mark.django_db
@pytest.mark.parametrize("email", ["buyer@proff58.ru", "nobody@proff58.ru"])
def test_сбой_транспорта_даёт_503_всем_одинаково(api, покупатель, settings, email):
    with mock.patch(
        "apps.notifications.channels.email.open_connection",
        side_effect=RetryableChannelError("SMTPConnectError"),
    ):
        resp = _запросить(api, email)
    assert resp.status_code == 503 and resp.json()["code"] == "email_unavailable"
    assert mail.outbox == []


@pytest.mark.django_db
@pytest.mark.parametrize("email", ["buyer@proff58.ru", "nobody@proff58.ru"])
def test_ненастроенный_транспорт_даёт_503_всем(api, покупатель, settings, email):
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    settings.EMAIL_HOST = ""
    assert _запросить(api, email).status_code == 503


@pytest.mark.django_db
def test_сбой_отправки_не_выдаётся_за_отправленное(api, покупатель):
    with mock.patch(
        "apps.notifications.channels.email.send_email",
        side_effect=RetryableChannelError("SMTPServerDisconnected"),
    ):
        resp = _запросить(api)
    assert resp.status_code == 503


@pytest.mark.django_db
def test_лимит_по_адресу_поверх_ip(api, покупатель):
    from django.conf import settings as dj

    with override_settings(
        REST_FRAMEWORK={
            **dj.REST_FRAMEWORK,
            "DEFAULT_THROTTLE_RATES": {
                **dj.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
                "password_reset_email": "2/hour",
                "auth": "100/min",
            },
        }
    ):
        assert _запросить(api, "nobody@proff58.ru").status_code == 200
        assert _запросить(api, "NOBODY@proff58.ru").status_code == 200  # тот же адрес
        assert _запросить(api, "nobody@proff58.ru").status_code == 429
        assert _запросить(api, "other@proff58.ru").status_code == 200  # другой адрес не задет


# ═══════════ подтверждение ═══════════


@pytest.mark.django_db
def test_полный_цикл_старый_пароль_не_подходит_новый_работает(api, покупатель):
    _запросить(api)
    uid, token = _ссылка()
    resp = _подтвердить(api, uid, token)
    assert resp.status_code == 200, resp.json()

    покупатель.refresh_from_db()
    assert покупатель.check_password("NewStrong2027")
    assert not покупатель.check_password("OldStrong2026")
    login = api.post(
        "/api/account/login/",
        {"email": "buyer@proff58.ru", "password": "NewStrong2027"},
        format="json",
    )
    assert login.status_code == 200
    # тот же токен второй раз — отказ
    assert _подтвердить(api, uid, token, "Another2028xyz").status_code == 400


@pytest.mark.django_db
def test_чужой_uid_с_тем_же_токеном_не_меняет_чужой_пароль(api, покупатель):
    другой = User.objects.create_user(
        phone="+79001110005", email="other@proff58.ru", password="OtherStrong2026"
    )
    _запросить(api)
    _uid, token = _ссылка()
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    resp = _подтвердить(api, urlsafe_base64_encode(force_bytes(другой.pk)), token)
    assert resp.status_code == 400 and resp.json()["code"] == "invalid_token"
    другой.refresh_from_db()
    assert другой.check_password("OtherStrong2026")


@pytest.mark.django_db
@pytest.mark.parametrize("uid,token", [("zzz", "x"), ("MQ", "abc-def"), ("", "")])
def test_мусорные_uid_и_токен_отклоняются(api, покупатель, uid, token):
    assert _подтвердить(api, uid, token).status_code == 400


@pytest.mark.django_db
def test_истёкшая_ссылка_отклоняется(api, покупатель):
    _запросить(api)
    uid, token = _ссылка()
    позже = datetime.now() + timedelta(hours=2)  # _now у генератора — наивная дата
    with mock.patch.object(PasswordResetTokenGenerator, "_now", return_value=позже):
        resp = _подтвердить(api, uid, token)
    assert resp.status_code == 400 and resp.json()["code"] == "invalid_token"


@pytest.mark.django_db
def test_смена_email_после_запроса_гасит_ссылку(api, покупатель):
    _запросить(api)
    uid, token = _ссылка()
    User.objects.filter(pk=покупатель.pk).update(email="new@proff58.ru")
    assert _подтвердить(api, uid, token).status_code == 400


@pytest.mark.django_db
def test_деактивация_между_письмом_и_переходом(api, покупатель):
    _запросить(api)
    uid, token = _ссылка()
    User.objects.filter(pk=покупатель.pk).update(is_active=False)
    assert _подтвердить(api, uid, token).status_code == 400


@pytest.mark.django_db
def test_слабый_пароль_отклоняется_с_ключом_password(api, покупатель):
    _запросить(api)
    uid, token = _ссылка()
    resp = _подтвердить(api, uid, token, "12345678")
    assert resp.status_code == 400 and "password" in resp.json()
    покупатель.refresh_from_db()
    assert покупатель.check_password("OldStrong2026")
    # ссылка ещё жива — пароль не менялся
    assert _подтвердить(api, uid, token).status_code == 200


@pytest.mark.django_db
def test_старая_сессия_после_смены_пароля_не_действует(покупатель):
    старый_клиент = APIClient()
    assert (
        старый_клиент.post(
            "/api/account/login/",
            {"email": "buyer@proff58.ru", "password": "OldStrong2026"},
            format="json",
        ).status_code
        == 200
    )
    assert старый_клиент.get("/api/account/me/").status_code == 200

    новый_клиент = APIClient()
    _запросить(новый_клиент)  # токен генерируем ПОСЛЕ логина: last_login входит в хеш
    uid, token = _ссылка()
    assert _подтвердить(новый_клиент, uid, token).status_code == 200

    assert старый_клиент.get("/api/account/me/").status_code in (401, 403)
