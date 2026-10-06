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

from apps.accounts import reauth
from apps.core.throttling import AuthRateThrottle, ReauthThrottle

from .. import confirm, services
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


def _start_attempt(**kwargs) -> Response:
    """Создать попытку или явно сообщить, что MAX не настроен.

    Раньше пустой ``MAX_BOT_USERNAME`` превращался в ссылку ``max.ru/bot`` и
    пользователь видел рабочий на вид, но недействительный QR-код.
    """
    try:
        started = services.create_attempt(**kwargs)
    except services.MaxIntegrationUnavailable:
        return Response(
            {"detail": "Вход через MAX временно недоступен."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response(_attempt_payload(started), status=status.HTTP_201_CREATED)


class MaxAuthStartView(APIView):
    """POST /api/auth/max/start/ — создать попытку входа/регистрации (§7.1)."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        session_key = _ensure_session_key(request)
        return _start_attempt(
            session_key=session_key, operation_type=MaxAuthAttempt.Operation.LOGIN
        )


def _own_attempt(request, public_id) -> MaxAuthAttempt | None:
    """Попытка этой браузер-сессии (§11.2): чужая сессия не видит ни статуса, ни кода."""
    attempt = services.get_attempt(str(public_id))
    session_key = request.session.session_key or ""
    if attempt is None or not session_key or attempt.browser_session_key != session_key:
        return None
    return attempt


#: Причины отказа входа, которые до выдачи кода раскрывали бы чужому браузеру, есть
#: ли у номера аккаунт и какой он (ревью В-5). Сам человек читает честную причину в
#: чате бота; после ввода кода (попытка уже прошла через код) причина отдаётся как есть.
_PRIVATE_LOGIN_REASONS = frozenset(
    {"phone_unverified", "password_account", "user_has_other_max", "inactive_account"}
)


def _status_payload(attempt: MaxAuthAttempt) -> dict:
    """Ответ опроса/подтверждения. Ничего об отложенной личности: пока код не введён,
    эти ответы читает и браузер, создавший попытку, — возможно, чужой."""
    reason = attempt.failure_reason or None
    if (
        reason in _PRIVATE_LOGIN_REASONS
        and attempt.operation_type == MaxAuthAttempt.Operation.LOGIN
        and attempt.code_issues == 0
    ):
        reason = "declined_in_max"
    return {
        "status": attempt.status,
        "failure_reason": reason,
        "expires_at": attempt.expires_at.isoformat(),
    }


class MaxAuthStatusView(APIView):
    """GET /api/auth/max/<public_id>/status/ — опрос статуса (§7.3).

    С DRF-2740 вход опрос НЕ выполняет: сессию поднимает ``MaxAuthConfirmView`` по
    верному коду. Отслеживание заказа (#520) завершается ботом, и ``completed``
    здесь по-прежнему приходит.
    """

    permission_classes = [AllowAny]

    def get(self, request, public_id):
        attempt = _own_attempt(request, public_id)
        if attempt is None:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_status_payload(attempt))


class MaxAuthConfirmView(APIView):
    """POST /api/auth/max/<public_id>/confirm/ {code} — ввод кода из бота (DRF-2740).

    Единственное место, где попытка входа/привязки/подтверждения завершается, — и
    только из браузер-сессии, создавшей попытку. Перебор ограничен счётчиком на
    самой попытке (5 неверных → отказ), лимит по IP — общий для входа.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request, public_id):
        attempt = _own_attempt(request, public_id)
        if attempt is None or attempt.operation_type == MaxAuthAttempt.Operation.TRACK_ORDER:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        op = attempt.operation_type
        if op == MaxAuthAttempt.Operation.LOGIN and request.user.is_authenticated:
            return Response(
                {"detail": "Вы уже вошли.", "code": "already_authenticated"},
                status=status.HTTP_409_CONFLICT,
            )
        if op in (MaxAuthAttempt.Operation.LINK, MaxAuthAttempt.Operation.CONFIRM_LOGIN) and (
            not request.user.is_authenticated or attempt.user_id != request.user.pk
        ):
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        if attempt.status == MaxAuthAttempt.Status.PENDING:
            return Response(
                {
                    "detail": "Код ещё не выдан: откройте MAX и нажмите «Начать».",
                    "code": "code_not_issued",
                    **_status_payload(attempt),
                },
                status=status.HTTP_409_CONFLICT,
            )
        if attempt.status != MaxAuthAttempt.Status.CONFIRMATION_REQUIRED:
            # Уже завершена или закрыта: повторный ввод ничего не подтверждает заново
            # (и не продлевает окно reauth).
            return Response(_status_payload(attempt), status=status.HTTP_409_CONFLICT)

        data = request.data if isinstance(request.data, dict) else {}
        result = confirm.confirm(attempt, code=str(data.get("code", "")))
        attempt = result.attempt
        if result.wrong_code:
            return Response(
                {
                    "detail": "Неверный код.",
                    "code": "wrong_code",
                    "attempts_left": result.attempts_left,
                    **_status_payload(attempt),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if attempt.status != MaxAuthAttempt.Status.COMPLETED:
            return Response(_status_payload(attempt), status=status.HTTP_409_CONFLICT)

        if op == MaxAuthAttempt.Operation.LOGIN and result.user is not None:
            user = result.user
            user.backend = _AUTH_BACKEND
            login(request, user)
        elif op == MaxAuthAttempt.Operation.CONFIRM_LOGIN:
            # DRF-2497: личность подтверждена в MAX. Время — момент подтверждения.
            # Ключ сессии не меняем: кабинет шлёт параллельные запросы со старой кукой.
            reauth.mark_verified(
                request, method=reauth.EXTERNAL, at=attempt.completed_at, rotate=False
            )
        return Response(_status_payload(attempt))


class MaxAuthCancelView(APIView):
    """POST /api/auth/max/<public_id>/cancel/ — отмена попытки пользователем (§13)."""

    permission_classes = [AllowAny]

    def post(self, request, public_id):
        attempt = services.cancel_attempt(
            str(public_id), session_key=request.session.session_key or ""
        )
        if attempt is None:
            return Response({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_status_payload(attempt))


class MaxLinkStartView(APIView):
    """POST /api/account/max/link/ — начать привязку MAX к текущему аккаунту (§5.4)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        session_key = _ensure_session_key(request)
        return _start_attempt(
            session_key=session_key,
            operation_type=MaxAuthAttempt.Operation.LINK,
            user=request.user,
        )


class MaxReauthStartView(APIView):
    """POST /api/account/max/reauth/ — подтвердить личность через привязанный MAX (DRF-2497).

    Для вошедших без пароля: перед удалением аккаунта, сменой e-mail, привязкой
    способа входа. Кто с паролем — подтверждает паролем.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AuthRateThrottle, ReauthThrottle]

    def post(self, request):
        if request.user.has_usable_password():
            return Response(
                {"detail": "Подтвердите действие паролем."}, status=status.HTTP_400_BAD_REQUEST
            )
        if not MaxAccount.objects.filter(user=request.user, is_active=True).exists():
            return Response(
                {"detail": "MAX не привязан к аккаунту."}, status=status.HTTP_400_BAD_REQUEST
            )
        session_key = _ensure_session_key(request)
        return _start_attempt(
            session_key=session_key,
            operation_type=MaxAuthAttempt.Operation.CONFIRM_LOGIN,
            user=request.user,
        )


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
        return _start_attempt(
            session_key=session_key,
            operation_type=MaxAuthAttempt.Operation.TRACK_ORDER,
            order=order,
        )


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
