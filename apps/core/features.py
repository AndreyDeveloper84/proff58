"""Единая точка проверки feature-флагов платформы.

Двухуровневая модель:
- **Инфраструктурные** флаги (`crm`, `ai`, `eventbus`, `external_integrations`) —
  задаются через окружение (`settings.FEATURES`, см. config/settings/base.py).
  Меняют разработчики на деплое.
- **Бизнес**-флаги (`reviews`, `b2b`, `promotions`, `articles`, `max_chat`,
  `ai_assist`, `video_reviews`) — хранятся в `SiteSettings` и переключаются
  администратором в рантайме.

Приоритет в `is_enabled`: override в `settings.FEATURES` → `SiteSettings` → `False`.

ПРАВИЛА:
- Модули проверяют флаги ТОЛЬКО через `is_enabled()` — не обращаться напрямую к
  `settings.FEATURES` или `SiteSettings.*_enabled`.
- Не вызывать `is_enabled()` бизнес-флага в hot-path/циклах без кэширования: это
  запрос к БД (`SiteSettings.get_solo()`). Кэш — отдельная оптимизация.
"""

from __future__ import annotations

from django.conf import settings

#: Бизнес-флаги хранятся в SiteSettings как поля `<flag>_enabled`.
_BUSINESS = (
    "reviews",
    "b2b",
    "promotions",
    "articles",
    "max_chat",
    "ai_assist",
    "video_reviews",
)


def is_enabled(flag: str) -> bool:
    """Включён ли feature-флаг. Неизвестный флаг — безопасно выключен (False)."""
    flag = flag.lower().strip()

    overrides = getattr(settings, "FEATURES", {})
    if flag in overrides:  # инфраструктурные + любой env-override
        return bool(overrides[flag])

    if flag in _BUSINESS:
        from .models import SiteSettings

        return bool(getattr(SiteSettings.get_solo(), f"{flag}_enabled"))

    return False
