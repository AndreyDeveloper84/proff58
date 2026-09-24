"""Кабинет: привязка и отвязка VK ID / Яндекс ID (`/api/account/oauth/…`).

Снаружи доступны только через Next-BFF (nginx шлёт `/api/account/` во фронт):
BFF добавляет X-CSRFToken, SessionAuthentication проверяет его на POST.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.throttling import AuthRateThrottle

from .. import pending, providers, services
from ..providers import LABELS, YANDEX


def _unavailable() -> Response:
    return Response(
        {"detail": "Этот способ входа сейчас недоступен."}, status=status.HTTP_404_NOT_FOUND
    )


class OAuthAccountsView(APIView):
    """GET /api/account/oauth/ — включённые провайдеры и их привязка к текущему аккаунту."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"providers": services.list_for_user(request.user)})


class OAuthLinkView(APIView):
    """POST /api/account/oauth/<provider>/link/ — адрес провайдера для привязки.

    Заводит в сессии ожидание с intent=link и id текущего пользователя: колбэк
    привяжет аккаунт только к нему и только если в браузере всё ещё он.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AuthRateThrottle]

    def post(self, request, provider):
        if not providers.is_enabled(provider):
            return _unavailable()
        if services.has_linked(request.user, provider):
            return Response(
                {"detail": f"{LABELS[provider]} уже привязан к аккаунту."},
                status=status.HTTP_409_CONFLICT,
            )
        state, verifier = pending.create(
            request.session,
            provider=provider,
            intent="link",
            next_url="/account/profile",
            user_id=request.user.pk,
        )
        services.emit("oauth_login_started", user=request.user, provider=provider, intent="link")
        url = providers.authorize_url(
            provider, state=state, verifier=verifier, force_confirm=provider == YANDEX
        )
        return Response({"url": url})


class OAuthUnlinkView(APIView):
    """POST /api/account/oauth/<provider>/unlink/ — отвязать, если есть другой способ входа."""

    permission_classes = [IsAuthenticated]

    def post(self, request, provider):
        if provider not in providers.PROVIDERS:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        outcome = services.unlink(request.user, provider)
        if outcome == "not_linked":
            return Response(
                {"detail": f"{LABELS[provider]} не привязан."}, status=status.HTTP_404_NOT_FOUND
            )
        if outcome == "last_method":
            return Response(
                {"detail": services.LAST_METHOD_DETAIL}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response({"ok": True})
