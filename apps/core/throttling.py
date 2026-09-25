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

import hmac

from django.conf import settings
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


class AuthRateThrottle(_FixedScopeThrottle):
    """Лимит чувствительных auth-эндпоинтов по IP (scope `auth`, #427/M-03).

    Логин/регистрация/OTP/смена телефона — низкий лимит против брутфорса пароля
    и enumeration телефонов. Ключ по IP.
    """

    scope = "auth"


class PasswordResetEmailThrottle(_FixedScopeThrottle):
    """Лимит запросов сброса пароля ПО АДРЕСУ (scope `password_reset_email`, DRF-2298).

    Дополняет IP-лимит `auth`: иначе один запрос в минуту с разных адресов
    превращает форму в бомбардировку чужого ящика и расход SMTP-квоты. Ключ —
    хеш нормализованного e-mail, сам адрес в кэш не пишем.
    """

    scope = "password_reset_email"

    def get_cache_key(self, request, view):
        import hashlib

        email = str(request.data.get("email", "") or "").strip().lower()
        if not email:
            return None  # пустой адрес отобьёт сериализатор
        ident = hashlib.sha256(email.encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": ident}


class SubscriptionRateThrottle(_FixedScopeThrottle):
    """Лимит подписки «Сообщить о поступлении» по IP (scope `subscription`, #517)."""

    scope = "subscription"


class ReviewsRateThrottle(_FixedScopeThrottle):
    """Лимит создания отзывов по IP (scope `reviews`, #573) — антиспам модерации."""

    scope = "reviews"


class DeliveryQuoteRateThrottle(_FixedScopeThrottle):
    """Лимит расчёта доставки СДЭК по IP (scope `delivery_quote`, DRF-2299):
    каждый расчёт — платные для нас запросы к API перевозчика."""

    scope = "delivery_quote"


class DeliveryLookupRateThrottle(_FixedScopeThrottle):
    """Лимит подсказок городов и пунктов выдачи СДЭК по IP (scope `delivery_lookup`)."""

    scope = "delivery_lookup"


class AnonRateThrottle(_FixedScopeThrottle):
    """Глобальный лимит анонимных запросов по IP (scope `anon`, #279).

    Защищает каталог и другие AllowAny-эндпоинты (фасеты, поиск) от дешёвого
    DoS. Аутентифицированные пользователи не ограничиваются этим троттлом.
    Задаётся в DEFAULT_THROTTLE_CLASSES; вьюхи с явным throttle_classes
    (1С, корзина/заказы) используют свои классы и игнорируют этот.
    """

    scope = "anon"

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            return None  # аутентифицированные запросы не ограничиваем
        if is_trusted_ssr(request):
            return None  # SSR витрины: общий IP контейнера фронта, см. is_trusted_ssr
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


def is_trusted_ssr(request) -> bool:
    """Запрос пришёл от SSR витрины (Next.js), а не от посетителя (PF-SH-RELEASE-01).

    SSR ходит в Django напрямую (``INTERNAL_API_BASE_URL=http://web:8000``) без
    X-Forwarded-For, поэтому для троттла все посетители сайта — один IP контейнера
    фронта. Общий анонимный лимит на нём превращался в 429 → SSR 500 на карточках
    при обходе краулером. SSR подтверждает себя секретом ``SSR_INTERNAL_TOKEN``
    (общий для web и frontend, из .env) в заголовке ``X-SSR-Token``. Снаружи
    заголовок до Django не доходит: стек-nginx его вырезает. Пустой секрет (дефолт)
    обход выключает.
    """
    expected = getattr(settings, "SSR_INTERNAL_TOKEN", "")
    if not expected:
        return False
    supplied = request.META.get("HTTP_X_SSR_TOKEN", "")
    return bool(supplied) and hmac.compare_digest(supplied, expected)
