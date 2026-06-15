"""Аутентификация 1С по статическому ключу.

1С 7.7 не умеет OAuth, поэтому используем простой общий секрет в заголовке
`X-Api-Key`, который сверяется с settings.ONEC_API_KEY. Если ключ на сервере
не задан — доступ закрыт (безопасное поведение по умолчанию).
"""

from django.conf import settings
from django.utils.crypto import constant_time_compare
from rest_framework.permissions import BasePermission


class HasOneCApiKey(BasePermission):
    message = "Неверный или отсутствующий X-Api-Key."

    def has_permission(self, request, view) -> bool:
        expected = getattr(settings, "ONEC_API_KEY", "") or ""
        if not expected:
            return False
        provided = request.headers.get("X-Api-Key", "") or ""
        # Сравнение за константное время — без timing side-channel для shared-secret.
        return bool(provided) and constant_time_compare(provided, expected)
