"""Сериализаторы accounts API (#325, #327, #328)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.models import Profile
from apps.accounts.phone import normalize_phone

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField()

    def validate_phone(self, value):
        # #421 (B-01): вход по нормализованному номеру — совпадает с тем, как
        # телефон сохранён при регистрации, независимо от формата ввода.
        return normalize_phone(value)


class RegisterSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField()
    # allow_blank: форма регистрации шлёт ключи всегда, даже с пустым значением
    # (имя необязательно). Без allow_blank DRF валит пустую строку ДО применения
    # default="" → регистрация без имени падала с 400 «Это поле не может быть пустым».
    full_name = serializers.CharField(required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    customer_type = serializers.ChoiceField(choices=["b2c", "b2b"], default="b2c")

    def validate_phone(self, value):
        # #421 (B-01): храним номер в каноне; уникальность проверяем по нему же.
        phone = normalize_phone(value)
        if not phone:
            raise serializers.ValidationError("Некорректный телефон.")
        if User.objects.filter(phone=phone).exists():
            raise serializers.ValidationError("Пользователь с таким телефоном уже существует.")
        return phone

    def validate(self, attrs):
        # #427 (M-03): полноценная проверка пароля Django-валидаторами (сложность,
        # длина, распространённость, похожесть на телефон/имя), а не только длина.
        candidate = User(
            phone=attrs.get("phone", ""),
            email=attrs.get("email", ""),
            full_name=attrs.get("full_name", ""),
        )
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "phone", "email", "full_name", "customer_type", "date_joined")
        read_only_fields = fields


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ("company_name", "inn", "kpp", "legal_address")


class UserProfileSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ("id", "phone", "email", "full_name", "customer_type", "profile")
        read_only_fields = ("id", "phone", "customer_type")
