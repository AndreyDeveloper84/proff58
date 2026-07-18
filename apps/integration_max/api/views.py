"""API авторизации через MAX (#492): создание попытки, опрос статуса, отмена,
привязка/отвязка из ЛК. Токен бота на фронт не отдаётся (§11.7) — только диплинк
с одноразовым секретом попытки.
"""

from __future__ import annotations

from django.contrib.auth import login
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.throttling import AuthRateThrottle

from .. import services
from ..models import MaxAccount, MaxAuthAttempt

# Единственный бэкенд аутентификации в проекте — ModelBackend; указываем явно,
# чтобы login() не зависел от числа настроенных бэкендов.
_AUTH_BACKEND = "django.contrib.auth.backends.ModelBackend"


def _ensure_session_key(request) -> str:
    """Гарантировать наличие ключа сессии — к нему привязывается попытка (§11.2)."""
    if request.session.session_key is None:
        request.session.save()
    return request.session.session_key


def _attempt_payload(started: services.StartedAttempt) -> dict:
    a = started.attempt
    return {
        "attempt_id": str(a.public_id),
        "deeplink": started.deeplink,
        "expires_at": a.expires_at.isoformat(),
        "status": a.status,
    }


class MaxAuthStartView(APIView):
    """POST /api/auth/max/start/ — создать попытку входа/регистрации (§7.1)."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        session_key = _ensure_session_key(request)
        started = services.create_attempt(
            session_key=session_key, operation_type=MaxAuthAttempt.Operation.LOGIN
        )
        return Response(_attempt_payload(started), status=status.HTTP_201_CREATED)


class MaxAuthStatusView(APIView):
    """GET /api/auth/max/<public_id>/status/ — опрос статуса (§7.3).

    Завершает вход ТОЛЬКО в браузере, создавшем попытку (§11.2): при completed и
    совпадении сессии поднимает Django-сессию пользователя.
    """

    permission_classes = [AllowAny]

    def get(self, request, public_id):
        attempt = services.get_attempt(str(public_id))
        if attempt is None:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)

        # §11.2: чужая браузер-сессия не должна ни завершать вход, ни читать статус.
        if attempt.browser_session_key != (request.session.session_key or ""):
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)

        # attempt.user is None для завершённых track_order-попыток (#520, гость без
        # аккаунта) — раньше у любой COMPLETED попытки user был гарантирован, этот
        # инвариант больше не всегда верен, здесь его нельзя молча предполагать.
        if (
            attempt.status == MaxAuthAttempt.Status.COMPLETED
            and not request.user.is_authenticated
            and attempt.user is not None
        ):
            user = attempt.user
            user.backend = _AUTH_BACKEND
            login(request, user)

        return Response(
            {"status": attempt.status, "failure_reason": attempt.failure_reason or None}
        )


class MaxAuthCancelView(APIView):
    """POST /api/auth/max/<public_id>/cancel/ — отмена попытки пользователем (§13)."""

    permission_classes = [AllowAny]

    def post(self, request, public_id):
        attempt = services.cancel_attempt(
            str(public_id), session_key=request.session.session_key or ""
        )
        if attempt is None:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"status": attempt.status})


class MaxLinkStartView(APIView):
    """POST /api/account/max/link/ — начать привязку MAX к текущему аккаунту (§5.4)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        session_key = _ensure_session_key(request)
        started = services.create_attempt(
            session_key=session_key,
            operation_type=MaxAuthAttempt.Operation.LINK,
            user=request.user,
        )
        return Response(_attempt_payload(started), status=status.HTTP_201_CREATED)


class MaxUnlinkView(APIView):
    """POST /api/account/max/unlink/ — отключить MAX в ЛК (§5.4)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        removed = services.unlink_max(request.user)
        return Response({"linked": False, "removed": removed})


class MaxStatusMeView(APIView):
    """GET /api/account/max/status/ — привязан ли MAX у текущего пользователя."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        acct = MaxAccount.objects.filter(user=request.user, is_active=True).first()
        return Response(
            {
                "linked": acct is not None,
                "max_user_id": acct.max_user_id if acct else None,
                "linked_at": acct.linked_at.isoformat() if acct else None,
            }
        )


class MaxTrackOrderStartView(APIView):
    """POST /api/orders/<number>/max-track/start/ — начать отслеживание гостевого
    заказа в MAX (#520).

    ``access_token`` — в теле запроса (не в query string): это мутирующий POST,
    держать гостевой токен подальше от URL/логов прокси/Referer лишним не будет
    (тот же токен, что #438 уже бережёт в GuestOrderView через query+no-store).
    Сам токен НИКУДА дальше не уходит — попытка несёт только public_id/secret
    (§11.1), в MAX или лог токен заказа не попадает.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request, number):
        from apps.orders.services import get_guest_order_by_token

        token = request.data.get("access_token", "")
        order = get_guest_order_by_token(number, token)
        if order is None:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)

        session_key = _ensure_session_key(request)
        started = services.create_attempt(
            session_key=session_key,
            operation_type=MaxAuthAttempt.Operation.TRACK_ORDER,
            order=order,
        )
        return Response(_attempt_payload(started), status=status.HTTP_201_CREATED)


class MaxTrackOrderStatusView(APIView):
    """GET /api/orders/max-track/<public_id>/status/ — опрос статуса track_order-попытки.

    В отличие от ``MaxAuthStatusView`` НЕ поднимает Django-сессию по completed —
    это не вход, гость так и остаётся гостем, только заказ теперь помечен для
    уведомлений (см. ``OrderTrackingGrant``).
    """

    permission_classes = [AllowAny]

    def get(self, request, public_id):
        attempt = services.get_attempt(str(public_id))
        if attempt is None or attempt.operation_type != MaxAuthAttempt.Operation.TRACK_ORDER:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        # §11.2: чужая браузер-сессия не должна читать статус попытки другого гостя.
        if attempt.browser_session_key != (request.session.session_key or ""):
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {"status": attempt.status, "failure_reason": attempt.failure_reason or None}
        )
