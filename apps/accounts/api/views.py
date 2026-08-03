"""Account API: вход, выход, регистрация, профиль (#325, #327, #328)."""

from __future__ import annotations

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Profile
from apps.core.throttling import AuthRateThrottle

from .serializers import (
    LoginSerializer,
    ProfileSerializer,
    RegisterSerializer,
    UserProfileSerializer,
    UserSerializer,
)

User = get_user_model()


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


class WishlistView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = request.user.wishlist.select_related("product").all()
        data = [
            {
                "product_id": item.product_id,
                "product_name": item.product.name,
                "product_slug": item.product.slug,
            }
            for item in items
        ]
        return Response(data)

    def post(self, request):
        from apps.accounts.wishlist import WishlistItem
        from apps.catalog.models import Product

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
    - WishlistItem: удаляется (user-owned, хранить не требуется).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.db import transaction

        from apps.accounts.models import Profile
        from apps.accounts.wishlist import WishlistItem
        from apps.orders.models import Order

        user_obj = request.user
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
