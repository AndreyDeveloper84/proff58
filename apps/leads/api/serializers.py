"""Сериализатор приёма заявок по товару."""

from __future__ import annotations

import re

from rest_framework import serializers

from apps.leads.models import ProductInquiry
from apps.leads.services import create_inquiry


class ProductInquirySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductInquiry
        fields = ["id", "kind", "product", "phone", "name", "message", "status"]
        read_only_fields = ["id", "status"]
        extra_kwargs = {"product": {"required": False, "allow_null": True}}

    def validate_phone(self, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if len(digits) == 11 and digits[0] in {"7", "8"}:
            return "+7" + digits[1:]
        if len(digits) == 10:
            return "+7" + digits
        raise serializers.ValidationError("Укажите корректный номер телефона.")

    def validate(self, attrs):
        from apps.leads.models import InquiryKind

        if attrs.get("kind") != InquiryKind.CONSULTATION and not attrs.get("product"):
            raise serializers.ValidationError({"product": "Для этого типа заявки требуется товар."})
        return attrs

    def to_representation(self, instance):
        return {
            "id": instance.id,
            "kind": instance.kind,
            "status": instance.status,
        }

    def create(self, validated_data):
        return create_inquiry(**validated_data)
