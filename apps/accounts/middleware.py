"""Маркер входа для фронта: cookie, по которой Next видит «этот вошёл».

Зачем нужен отдельный маркер, если есть `sessionid`. Наличие `sessionid` НЕ
означает, что человек вошёл: сессию Django заводит и анонимному посетителю —
например, гостевой корзине нужен `session_key`. Поэтому серверная защита
кабинета во фронте, судившая по `sessionid`, пропускала внутрь любого
посетителя, успевшего открыть сайт: он видел готовую разметку кабинета, и уже
браузер уводил его на форму входа. Со стороны это выглядит как «меня на секунду
пустили внутрь».

Маркер ставится по факту `request.user.is_authenticated`, поэтому покрывает все
способы входа сразу (пароль, OTP, MAX) и снимается на выходе — отдельная правка
в каждом сценарии не нужна.

Маркер — подсказка для быстрого отсева, а не право доступа: он HttpOnly, но
никем не подписан, и «сессия истекла на сервере» по нему не видно. Настоящую
проверку делает layout кабинета запросом `/api/account/me/`.
"""

from __future__ import annotations

from django.conf import settings

#: Имя cookie-маркера. Фронт знает его же (frontend/proxy.ts).
AUTH_MARKER_COOKIE = "auth"

#: Значение неважно — важно наличие; пишем «1», чтобы cookie не выглядела пустой.
AUTH_MARKER_VALUE = "1"


class AuthMarkerCookieMiddleware:
    """Держит cookie-маркер в согласии с тем, вошёл ли пользователь.

    Ставится после `AuthenticationMiddleware` — до него `request.user` ещё нет.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        user = getattr(request, "user", None)
        if user is None:
            # Запрос мимо AuthenticationMiddleware (например, статика) — не наше дело.
            return response

        has_marker = AUTH_MARKER_COOKIE in request.COOKIES
        if user.is_authenticated:
            if not has_marker:
                response.set_cookie(
                    AUTH_MARKER_COOKIE,
                    AUTH_MARKER_VALUE,
                    max_age=settings.SESSION_COOKIE_AGE,
                    secure=settings.SESSION_COOKIE_SECURE,
                    httponly=True,
                    samesite=settings.SESSION_COOKIE_SAMESITE,
                )
        elif has_marker:
            # Вышел, сессия истекла или её вычистили — маркер обязан уйти следом,
            # иначе фронт будет гонять человека в кабинет и обратно.
            response.delete_cookie(
                AUTH_MARKER_COOKIE,
                samesite=settings.SESSION_COOKIE_SAMESITE,
            )

        return response
