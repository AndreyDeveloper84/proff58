"""Account API: вход, выход, регистрация, профиль (#325, #327, #328)."""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Profile
from apps.core.throttling import AuthRateThrottle, PasswordResetEmailThrottle

from .serializers import (
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileSerializer,
    RegisterSerializer,
    UserProfileSerializer,
    UserSerializer,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = authenticate(
            request, email=ser.validated_data["email"], password=ser.validated_data["password"]
        )
        if user is None:
            # Один текст на оба случая: по ответу нельзя перебрать, какие адреса
            # зарегистрированы.
            return Response(
                {"detail": "Неверный e-mail или пароль."}, status=status.HTTP_400_BAD_REQUEST
            )
        login(request, user)
        from apps.orders.services import claim_guest_orders

        claimed = claim_guest_orders(user)
        data = UserSerializer(user).data
        if claimed:
            data["claimed_orders"] = claimed
        return Response(data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({"ok": True})


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        user = User.objects.create_user(
            password=d["password"],
            full_name=d.get("full_name", ""),
            email=d["email"],
            customer_type=d.get("customer_type", "b2c"),
        )
        if d.get("customer_type") == "b2b":
            # Реквизиты собраны на форме — сохраняем сразу, иначе организация
            # попадёт в кабинет с пустой карточкой и не сможет запросить счёт.
            Profile.objects.update_or_create(
                user=user,
                defaults={
                    "company_name": d.get("company_name", "").strip(),
                    "inn": d.get("inn", "").strip(),
                    "kpp": d.get("kpp", "").strip(),
                },
            )
        # backend указываем явно: их два (почта и админский по телефону), и при
        # входе без authenticate() Django отказывается угадывать.
        login(request, user, backend="apps.accounts.auth_backends.EmailBackend")
        # #421 (B-01): claim гостевых заказов при регистрации не делаем. Теперь
        # телефон на этом шаге вообще не спрашивают, так что и привязывать нечего:
        # номер попадёт в аккаунт через MAX — то есть с подтверждением владения.
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserProfileSerializer(request.user).data)

    def patch(self, request):
        """Правка профиля, включая переход «частное лицо ↔ организация».

        Всё идёт через сериализатор: он проверяет и уникальность e-mail (это
        логин), и реквизиты при переходе в организацию. Раньше поля писались
        напрямую, поэтому проверить их было негде.
        """
        user = request.user
        ser = UserProfileSerializer(user, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        user = ser.save()

        # Реквизиты организации: сохраняем и при переходе в B2B, и при правке
        # уже существующей карточки.
        if user.customer_type == "b2b" and request.data.get("profile"):
            profile, _ = Profile.objects.get_or_create(user=user)
            profile_ser = ProfileSerializer(profile, data=request.data["profile"], partial=True)
            profile_ser.is_valid(raise_exception=True)
            profile_ser.save()

        return Response(UserProfileSerializer(user).data)


#: Потолок разового переноса избранного из браузера в аккаунт. Совпадает по
#: смыслу с лимитом гостевого списка на фронте: больше человек не накопит, а
#: длинный список превратил бы вход в тяжёлую запись.
MAX_WISHLIST_BULK = 100


class WishlistView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Импорт внутри метода: избранное и так стоит на товарах каталога, но
        # модуль аккаунтов — нижний слой и не должен тянуть каталог при загрузке.
        from apps.catalog.services import main_image_urls

        items = list(request.user.wishlist.select_related("product").all())
        images = main_image_urls(item.product_id for item in items)
        data = [
            {
                "product_id": item.product_id,
                "product_name": item.product.name,
                "product_slug": item.product.slug,
                # Главное фото или None — тогда витрина покажет «Фото готовится».
                "product_image": images.get(item.product_id),
            }
            for item in items
        ]
        return Response(data)

    def post(self, request):
        """Добавить товар (``product_id``) или сразу несколько (``product_ids``).

        Список нужен переносу гостевого избранного при входе: человек копил его
        без аккаунта, и отправлять по запросу на товар — значит устроить веер из
        двадцати обращений в момент, когда страница и так грузится.

        Несуществующие id в списке молча пропускаем: товар мог быть снят с
        публикации, пока лежал в браузере, и это не повод потерять весь перенос.
        Одиночная форма по-прежнему отвечает 404 — там id ровно один, и тишина
        в ответ означала бы «сохранили», хотя не сохранили.
        """
        from apps.accounts.wishlist import WishlistItem
        from apps.catalog.models import Product

        raw_ids = request.data.get("product_ids")
        if raw_ids is not None:
            if not isinstance(raw_ids, list):
                return Response(
                    {"detail": "product_ids должен быть списком."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            ids = [int(v) for v in raw_ids if str(v).isdigit()][:MAX_WISHLIST_BULK]
            products = Product.objects.filter(pk__in=ids)
            WishlistItem.objects.bulk_create(
                [WishlistItem(user=request.user, product=product) for product in products],
                ignore_conflicts=True,  # повторный перенос не должен падать
            )
            return Response({"ok": True, "added": len(products)}, status=status.HTTP_201_CREATED)

        product_id = request.data.get("product_id")
        try:
            product = Product.objects.get(pk=product_id)
        except Product.DoesNotExist:
            return Response({"detail": "Товар не найден."}, status=status.HTTP_404_NOT_FOUND)
        WishlistItem.objects.get_or_create(user=request.user, product=product)
        return Response({"ok": True}, status=status.HTTP_201_CREATED)

    def delete(self, request):
        from apps.accounts.wishlist import WishlistItem

        product_id = request.data.get("product_id")
        WishlistItem.objects.filter(user=request.user, product_id=product_id).delete()
        return Response({"ok": True})


class DeleteAccountView(APIView):
    """Удаление аккаунта — обезличивание ПДн (#344, #426/M-02).

    Data map user-owned ПДн (всё чистится в одной транзакции):
    - User: phone → deleted-<pk>, full_name/email очищаются, max_chat_id снят,
      is_active=False;
    - Profile: company_name, ИНН, КПП, юр. адрес и данные согласия ПДн очищаются;
    - Order (снимок): контактные и B2B-реквизиты обезличиваются. Сами записи
      заказов сохраняются как бухгалтерские документы (обязательный срок хранения),
      но без ПДн;
    - WishlistItem: удаляется (user-owned, хранить не требуется);
    - привязки внешних входов (VK ID / Яндекс ID): снимает подписчик события
      ``user_deleted`` (apps.integration_oauth) после коммита.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.db import transaction

        from apps.accounts.models import Profile
        from apps.accounts.wishlist import WishlistItem
        from apps.orders.models import Order

        user_obj = request.user
        # Необратимое действие — подтверждаем паролем, как смену телефона: одной
        # украденной сессии не должно хватать, чтобы стереть аккаунт. У пришедших
        # из MAX пароля нет — им подтверждать нечем.
        if user_obj.has_usable_password():
            password = request.data.get("password", "")
            if not password or not user_obj.check_password(password):
                return Response({"detail": "Неверный пароль."}, status=status.HTTP_400_BAD_REQUEST)
        logout(request)

        with transaction.atomic():
            Order.objects.filter(user=user_obj).update(
                customer_name="[удалён]",
                customer_phone="",
                customer_email="",
                company_name="",
                inn="",
                kpp="",
                legal_address="",
            )

            # #426 (M-02): обезличиваем Profile — иначе ПДн (ИНН/КПП/юр.адрес/
            # согласие) оставались после «удаления», хотя API отвечал об обезличивании.
            Profile.objects.filter(user=user_obj).update(
                company_name="",
                inn="",
                kpp="",
                legal_address="",
                pd_consent_at=None,
                pd_consent_version="",
            )

            WishlistItem.objects.filter(user=user_obj).delete()

            # #573: снапшот публичного имени в отзывах — тоже ПДн. Сами отзывы
            # (оценки/текст) остаются анонимно, author уже SET_NULL.
            from apps.reviews.models import Review

            Review.objects.filter(author=user_obj).update(author_name="Покупатель")

            user_obj.phone = f"deleted-{user_obj.pk}"
            user_obj.full_name = ""
            user_obj.email = ""
            user_obj.max_chat_id = None
            user_obj.is_active = False
            user_obj.save(update_fields=["phone", "full_name", "email", "max_chat_id", "is_active"])

            # Интеграции входа (VK ID / Яндекс ID) снимают свои привязки по событию:
            # accounts о них не знает (слой 0, CLAUDE.md §4). После коммита — чтобы
            # подписчик не снял привязки у аккаунта, удаление которого откатилось.
            from apps.core.events import user_deleted

            transaction.on_commit(
                lambda uid=user_obj.pk: user_deleted.send(sender=User, user_id=uid)
            )

        return Response({"ok": True, "detail": "Аккаунт удалён, данные обезличены."})


class ChangePhoneView(APIView):
    """Смена телефона (#343, #427/M-03).

    Чувствительное действие: требует re-auth текущим паролем. Новый номер
    приводится к канону (E.164) и помечается НЕподтверждённым — владение им
    нужно заново подтвердить через MAX (OTP), только после этого он снова
    сможет использоваться для OTP-входа и claim гостевых заказов.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        from apps.accounts.phone import normalize_phone

        # #427 (M-03): re-auth — подтверждение текущим паролем.
        password = request.data.get("password", "")
        if not password or not request.user.check_password(password):
            return Response({"detail": "Неверный пароль."}, status=status.HTTP_400_BAD_REQUEST)

        new_phone = normalize_phone(request.data.get("new_phone", ""))
        if not new_phone:
            return Response(
                {"detail": "Новый телефон обязателен."}, status=status.HTTP_400_BAD_REQUEST
            )
        if User.objects.filter(phone=new_phone).exclude(pk=request.user.pk).exists():
            return Response(
                {"detail": "Этот телефон уже используется."}, status=status.HTTP_400_BAD_REQUEST
            )
        request.user.phone = new_phone
        request.user.max_chat_id = None
        request.user.phone_verified = False  # новый номер — заново через MAX
        request.user.save(update_fields=["phone", "max_chat_id", "phone_verified"])
        return Response(UserSerializer(request.user).data)


@method_decorator(ensure_csrf_cookie, name="get")
class CSRFView(APIView):
    """Установить csrftoken cookie и вернуть токен.

    SPA делает GET /api/account/csrf/ перед первым POST-запросом, чтобы
    получить csrf-cookie. После этого JavaScript читает csrftoken и отправляет
    его заголовком X-CSRFToken в POST/PUT/PATCH/DELETE запросах.
    """

    permission_classes = [AllowAny]
    authentication_classes = []  # GET не требует сессии

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


# ═══════════ DRF-2298: восстановление пароля покупателя по e-mail ═══════════

_RESET_SENT = {"detail": "Если адрес зарегистрирован, мы отправили письмо со ссылкой."}
_RESET_UNAVAILABLE = {
    "detail": "Не удалось отправить письмо. Попробуйте позже.",
    "code": "email_unavailable",
}
_RESET_INVALID = {"detail": "Ссылка недействительна или устарела.", "code": "invalid_token"}


def _reset_eligible(user) -> bool:
    """Кому сброс доступен: активный покупатель с паролем (или с входом, который
    зарегистрировал модуль выше — см. ``apps.accounts.services.is_reset_eligible``).

    Аккаунт из MAX (`has_usable_password()` False) пароля через сброс не получает —
    e-mail у него не подтверждён, а вход через MAX и так без пароля. Сотрудники
    админки (`is_staff`) восстанавливают доступ административным порядком, а не
    через публичную форму витрины.
    """
    from apps.accounts.services import is_reset_eligible

    return is_reset_eligible(user)


def _find_reset_user(email: str):
    users = list(User.objects.filter(email__iexact=email)[:2])
    if len(users) != 1:  # нет или дубль из прежней схемы — как в EmailBackend
        return None
    return users[0] if _reset_eligible(users[0]) else None


def _reset_link(user) -> str:
    """Ссылка только из SITE_URL — не из Host-заголовка запроса."""
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    base = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{base}/account/reset-password?uid={uid}&token={token}"


class PasswordResetRequestView(APIView):
    """POST /api/account/password-reset/ — письмо со ссылкой на смену пароля.

    Ответ 200 одинаков для известного и неизвестного адреса. Соединение с почтой
    открывается ДО поиска пользователя: сбой транспорта даёт 503 всем одинаково и
    не выдаёт, есть ли аккаунт. Ссылка отправляется синхронно, минуя outbox —
    токен не должен лежать в журнале уведомлений.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle, PasswordResetEmailThrottle]

    def post(self, request):
        from apps.notifications.channels import ChannelError
        from apps.notifications.channels import email as email_channel

        ser = PasswordResetRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        if not (getattr(settings, "SITE_URL", "") or ""):
            logger.error("Сброс пароля: SITE_URL не задан — ссылку собрать не из чего")
            return Response(_RESET_UNAVAILABLE, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        try:
            connection = email_channel.open_connection()
        except ChannelError as exc:
            logger.error("Сброс пароля: транспорт недоступен (%s)", exc)
            return Response(_RESET_UNAVAILABLE, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            user = _find_reset_user(ser.validated_data["email"])
            if user is None:
                return Response(_RESET_SENT)
            hours = max(1, int(getattr(settings, "PASSWORD_RESET_TIMEOUT", 3600) // 3600))
            body = (
                "Вы запросили восстановление пароля на сайте «Профессионал».\n\n"
                "Чтобы задать новый пароль, перейдите по ссылке:\n"
                f"{_reset_link(user)}\n\n"
                f"Ссылка действует {hours} ч и подходит только один раз.\n"
                "Если вы не запрашивали восстановление, просто не открывайте ссылку — "
                "пароль останется прежним.\n"
            )
            try:
                email_channel.send_email(
                    "Восстановление пароля — «Профессионал»",
                    body,
                    [user.email],
                    connection=connection,
                )
            except ChannelError as exc:
                logger.error("Сброс пароля: письмо не отправлено (%s)", exc)
                return Response(_RESET_UNAVAILABLE, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        finally:
            try:
                connection.close()
            except Exception:  # noqa: BLE001 — закрытие не важнее ответа
                pass
        logger.info("Сброс пароля: письмо отправлено")
        return Response(_RESET_SENT)


class PasswordResetConfirmView(APIView):
    """POST /api/account/password-reset/confirm/ — новый пароль по uid+token.

    Токен Django одноразовый по построению: в его хеше старый хеш пароля,
    после смены он не проходит. Старые сессии инвалидирует сам Django —
    session auth hash перестаёт совпадать. Автологина нет: человек входит новым
    паролем.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_decode

        raw = {k: request.data.get(k) for k in ("uid", "token")}
        user = None
        try:
            user = User.objects.filter(
                pk=int(urlsafe_base64_decode(str(raw["uid"])).decode())
            ).first()
        except (TypeError, ValueError, OverflowError):
            user = None
        if (
            user is None
            or not _reset_eligible(user)
            or not default_token_generator.check_token(user, str(raw["token"] or ""))
        ):
            return Response(_RESET_INVALID, status=status.HTTP_400_BAD_REQUEST)

        ser = PasswordResetConfirmSerializer(data=request.data, context={"user": user})
        if not ser.is_valid():
            errors = dict(ser.errors)
            if "new_password" in errors:
                errors["password"] = errors.pop("new_password")
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(ser.validated_data["new_password"])
        user.save(update_fields=["password"])
        logger.info("Сброс пароля: пароль изменён")
        return Response({"detail": "Пароль изменён. Войдите с новым паролем."})
