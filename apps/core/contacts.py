"""Публичные контакты магазина в ``SiteSettings.contacts`` (T3).

JSON-поле остаётся хранилищем (схема витрины уже читает эти ключи —
``frontend/lib/site.ts::resolveStorefront``), а здесь — единый список ключей,
подписи для админки и значения по умолчанию, которыми заполняется пустая
настройка (миграция 0003). Витрина держит те же значения только как запасные
на случай недоступного API.
"""

from __future__ import annotations

CONTACT_FIELDS: dict[str, tuple[str, str]] = {
    # ключ в contacts: (подпись, значение по умолчанию)
    "phone_display": ("Телефон (как показывать)", "8 (8412) 20-20-87"),
    "email": ("E-mail", "penzainstrument@yandex.ru"),
    "address": ("Адрес магазина", "г. Пенза, 1-й Онежский проезд, 12"),
    "schedule": ("График работы", "Пн–Сб 09:00–19:00, Вс 09:00–15:00"),
    "store": ("Подпись адреса в шапке", "Магазин на 1-м Онежском проезде, 12"),
    "phone_note": ("Подпись под телефоном", ""),
    "max_url": ("Ссылка на бота MAX (если не из окружения)", ""),
}


def seed_defaults(contacts: dict | None) -> dict:
    """Дополнить словарь контактов значениями по умолчанию для пустых ключей."""
    result = dict(contacts or {})
    for key, (_label, default) in CONTACT_FIELDS.items():
        if not str(result.get(key) or "").strip() and default:
            result[key] = default
    return result
