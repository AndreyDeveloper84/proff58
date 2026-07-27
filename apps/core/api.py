"""Публичный API витрины: бренд и публичные контакты из SiteSettings."""

from __future__ import annotations

from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SiteSettings


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
            }
        )
