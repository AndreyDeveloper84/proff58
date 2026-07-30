"""Сериализаторы информационных страниц витрины."""

from __future__ import annotations

from rest_framework import serializers

from ..models import SEOPage


class InfoPageListSerializer(serializers.ModelSerializer):
    """Пункт меню: только то, что нужно для ссылки в подвале."""

    class Meta:
        model = SEOPage
        fields = ("slug", "title")


class InfoPageSerializer(serializers.ModelSerializer):
    """Страница целиком.

    ``body`` отдаём как есть — обычным текстом. Фронт рендерит его абзацами и
    НЕ вставляет как HTML: страницу пишет человек в админке, и превращать её
    текст в разметку значит открыть XSS через контент-редактора.
    """

    updated_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = SEOPage
        fields = ("slug", "title", "body", "meta_title", "meta_description", "updated_at")
