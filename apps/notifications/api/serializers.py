from __future__ import annotations

from django.utils import timezone
from rest_framework import serializers

from ..models import Notification, UserNotificationPreference


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """GET/PATCH собственных preferences (#515).

    `consent_version` — write-only: фронт передаёт версию политики, которую
    показал пользователю; обязателен при включении `marketing_enabled`
    (explicit consent — AC #515). Выключение маркетинга согласие не трогает —
    `marketing_consent_at/version` остаются как исторический след последнего
    согласия.
    """

    consent_version = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = UserNotificationPreference
        fields = (
            "max_enabled",
            "order_updates_enabled",
            "product_availability_enabled",
            "marketing_enabled",
            "marketing_consent_at",
            "marketing_consent_version",
            "consent_version",
        )
        read_only_fields = ("marketing_consent_at", "marketing_consent_version")

    def validate(self, attrs):
        if (
            attrs.get("marketing_enabled") is True
            and not (attrs.get("consent_version") or "").strip()
        ):
            raise serializers.ValidationError(
                {"consent_version": "Обязателен при включении marketing_enabled."}
            )
        return attrs

    def update(self, instance, validated_data):
        consent_version = validated_data.pop("consent_version", "")
        if validated_data.get("marketing_enabled") is True:
            instance.marketing_consent_at = timezone.now()
            instance.marketing_consent_version = consent_version
        return super().update(instance, validated_data)


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = (
            "id",
            "event",
            "category",
            "title",
            "body",
            "data",
            "policy_skip_reason",
            "created_at",
            "read_at",
        )
        read_only_fields = fields
