"""Сериализаторы accounts API (#325, #327, #328)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.accounts.models import Profile

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField()


class RegisterSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField(min_length=6)
    full_name = serializers.CharField(required=False, default="")
    email = serializers.EmailField(required=False, default="")
    customer_type = serializers.ChoiceField(choices=["b2c", "b2b"], default="b2c")

    def validate_phone(self, value):
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("Пользователь с таким телефоном уже существует.")
        return value


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
