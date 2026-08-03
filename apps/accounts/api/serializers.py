"""Сериализаторы accounts API (#325, #327, #328)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.models import Profile
from apps.accounts.requisites import validate_company_requisites

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    """Вход по e-mail. Телефон логином не является — см. accounts/models.py."""

    email = serializers.EmailField()
    password = serializers.CharField()

    def validate_email(self, value):
        return value.strip()


class RegisterSerializer(serializers.Serializer):
    """Регистрация по e-mail — для частного лица и для организации.

    Организация указывает реквизиты сразу: они нужны для счёта, и без них
    кабинет юрлица пустой. Проверка ждать не заставляет — счета и реквизиты
    доступны сразу после регистрации (флаг верификации — отметка для менеджера,
    на возможности покупателя он не влияет, см. ADR-0013).
    """

    email = serializers.EmailField()
    password = serializers.CharField()
    # allow_blank: форма регистрации шлёт ключи всегда, даже с пустым значением
    # (имя необязательно). Без allow_blank DRF валит пустую строку ДО применения
    # default="" → регистрация без имени падала с 400 «Это поле не может быть пустым».
    full_name = serializers.CharField(required=False, allow_blank=True, default="")
    customer_type = serializers.ChoiceField(choices=["b2c", "b2b"], default="b2c")
    company_name = serializers.CharField(required=False, allow_blank=True, default="")
    inn = serializers.CharField(required=False, allow_blank=True, default="")
    kpp = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_email(self, value):
        email = value.strip()
        # iexact: адрес — логин, и Ivan@ с ivan@ не должны стать разными людьми.
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("Пользователь с таким e-mail уже существует.")
        return email

    def validate(self, attrs):
        # #427 (M-03): полноценная проверка пароля Django-валидаторами (сложность,
        # длина, распространённость, похожесть на e-mail/имя), а не только длина.
        candidate = User(
            email=attrs.get("email", ""),
            full_name=attrs.get("full_name", ""),
        )
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc

        if attrs.get("customer_type") == "b2b":
            errors = validate_company_requisites(
                inn=attrs.get("inn", ""),
                company_name=attrs.get("company_name", ""),
                kpp=attrs.get("kpp", ""),
            )
            if errors:
                raise serializers.ValidationError({"detail": errors})
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
    """Профиль в кабинете.

    ``customer_type`` менять можно: человек, зарегистрировавшийся частным лицом,
    начинает покупать от организации — и наоборот. Раньше поле было read-only, и
    такой переход был возможен только через менеджера в админке. Переход в
    организацию требует реквизитов: без них кабинет юрлица бессмыслен.

    Телефон правится отдельной ручкой (ChangePhoneView) — он подтверждается
    через MAX, поэтому свободной записи здесь ему не место.
    """

    profile = ProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ("id", "phone", "email", "full_name", "customer_type", "profile")
        read_only_fields = ("id", "phone")

    def validate_customer_type(self, value):
        if value not in {"b2c", "b2b"}:
            raise serializers.ValidationError("Неизвестный тип покупателя.")
        return value

    def validate_email(self, value):
        email = (value or "").strip()
        if not email:
            # Пустой адрес допустим только у тех, кто пришёл из MAX и его не
            # задавал; отобрать у себя логин, стерев почту, нельзя.
            raise serializers.ValidationError("E-mail нужен для входа — его нельзя очистить.")
        taken = User.objects.filter(email__iexact=email)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError("Этот e-mail уже занят.")
        return email

    def validate(self, attrs):
        user = self.instance
        target_type = attrs.get("customer_type", user.customer_type if user else "b2c")
        if target_type != "b2b":
            return attrs

        # Реквизиты берём из этого же запроса, а чего нет — из уже сохранённого
        # профиля: переключиться в организацию, ничего не указав, нельзя, но и
        # повторять сохранённое ради смены имени не заставляем.
        profile_data = self.initial_data.get("profile") or {}
        saved = getattr(user, "profile", None)
        errors = validate_company_requisites(
            inn=profile_data.get("inn", getattr(saved, "inn", "")),
            company_name=profile_data.get("company_name", getattr(saved, "company_name", "")),
            kpp=profile_data.get("kpp", getattr(saved, "kpp", "")),
        )
        if errors:
            raise serializers.ValidationError({"detail": errors})
        return attrs
