"""Публичный API витрины: бренд и публичные контакты из SiteSettings."""

from __future__ import annotations

from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SiteSettings


def _max_bot_url() -> str:
    """Ссылка на бота магазина в MAX — пустая строка, если бот не настроен.

    Витрина рисует плитку «наш бот в MAX» только по непустому значению: ссылка на
    max.ru без имени бота вела бы не к магазину, а на главную мессенджера — и
    выглядела бы рабочей.

    Настройку читаем напрямую из env: apps.core — нижний слой и об интеграциях
    знать не должен (ADR: зависимости направлены вниз). Формат адреса профиля —
    тот же, что у диплинка в apps/integration_max/services.build_deeplink.
    """
    username = (getattr(settings, "MAX_BOT_USERNAME", "") or "").strip().lstrip("@")
    token = (getattr(settings, "MAX_BOT_TOKEN", "") or "").strip()
    if not username or not token:
        return ""
    return f"https://max.ru/{username}"


class ThemeView(APIView):
    """GET /api/core/theme/ — публичные настройки оформления витрины."""

    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        s = SiteSettings.get_solo()
        logo_url = ""
        if s.logo:
            logo_url = request.build_absolute_uri(s.logo.url)
        return Response(
            {
                "name": s.name,
                "primary_color": s.primary_color,
                "accent_color": s.accent_color,
                "logo_url": logo_url,
                "region": s.region,
                "contacts": s.contacts if isinstance(s.contacts, dict) else {},
                # Бот магазина в MAX: адрес собирается из настроек сервера, чтобы
                # стенд и прод вели каждый в своего бота и ссылка не устаревала
                # в коде витрины.
                "max_bot_url": _max_bot_url(),
            }
        )
