"""Account API: вход, выход, регистрация, профиль (#325, #327, #328)."""

from __future__ import annotations

from django.contrib.auth import authenticate, get_user_model, login, logout
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Profile

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

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = authenticate(
            request, username=ser.validated_data["phone"], password=ser.validated_data["password"]
        )
        if user is None:
            return Response(
                {"detail": "Неверный телефон или пароль."}, status=status.HTTP_400_BAD_REQUEST
            )
        login(request, user)
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({"ok": True})


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        user = User.objects.create_user(
            phone=d["phone"],
            password=d["password"],
            full_name=d.get("full_name", ""),
            email=d.get("email", ""),
            customer_type=d.get("customer_type", "b2c"),
        )
        login(request, user)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserProfileSerializer(request.user).data)

    def patch(self, request):
        user = request.user
        for field in ("full_name", "email"):
            if field in request.data:
                setattr(user, field, request.data[field])
        user.save(update_fields=["full_name", "email", "updated_at"])

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
