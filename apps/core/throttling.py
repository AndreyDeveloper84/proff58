"""Троттлинг чувствительных эндпоинтов (#9 код-ревью).

DRF проверяет throttle ПОСЛЕ permission, поэтому на /api/1c/ это ограничивает
флуд с уже валидным ключом (сценарий утечки ключа — массовая подмена цен/
остатков), а брутфорс самого ключа — задача nginx limit_req / IP-allowlist.

Лимиты задаются в settings.DEFAULT_THROTTLE_RATES (scope-и `onec`, `orders`).
Используем фиксированный scope на классе (а не ScopedRateThrottle+throttle_scope):
ключ по IP, scope зашит в класс — одинаково удобно и для function-based 1С-вьюх,
и для class-based вьюх корзины/заказов.
"""

from __future__ import annotations

from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle


class _FixedScopeThrottle(SimpleRateThrottle):
    """Лимит по IP с фиксированным scope (берёт rate из DEFAULT_THROTTLE_RATES)."""

    def get_rate(self):
        # Читаем свежую ставку из api_settings, а не из кэшированного на классе
        # SimpleRateThrottle.THROTTLE_RATES — иначе override_settings в тестах
        # (и любая перезагрузка настроек) «залипает» на старом словаре.
        return api_settings.DEFAULT_THROTTLE_RATES.get(self.scope)

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class OneCRateThrottle(_FixedScopeThrottle):
    """Лимит запросов к /api/1c/ по IP (scope `onec`)."""

    scope = "onec"


class OrdersRateThrottle(_FixedScopeThrottle):
    """Лимит оформления/добавления в корзину по IP (scope `orders`)."""

    scope = "orders"
