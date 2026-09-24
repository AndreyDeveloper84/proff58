"""Публичный сервисный контракт accounts для других модулей.

Реестр «кому доступно восстановление пароля». По умолчанию сброс получает только
покупатель с паролем: аккаунт из MAX без пароля его не получает (почта у него не
подтверждена, а вход через MAX и так без пароля).

Модули входа выше по слоям (VK ID / Яндекс ID) могут добавить своё условие через
``register_reset_eligibility`` из своего ``AppConfig.ready()``. Почему реестр, а не
``user.oauth_accounts.exists()`` прямо здесь: accounts — слой 0 и о слое
интеграций не знает (CLAUDE.md §4). Обращение по related_name — это то же чтение
чужой таблицы, только неявное: без установленного integration_oauth атрибута нет,
и accounts молча зависел бы от модуля, который может быть выключен. Реестр
разворачивает зависимость: интеграция знает об accounts, не наоборот.
"""

from __future__ import annotations

from collections.abc import Callable

_reset_checks: list[Callable[[object], bool]] = []


def register_reset_eligibility(check: Callable[[object], bool]) -> None:
    """Добавить условие: ``check(user) -> True`` открывает сброс пользователю без пароля.

    Повторная регистрация той же функции (двойной ready() в тестах) — no-op.
    """
    if check not in _reset_checks:
        _reset_checks.append(check)


def is_reset_eligible(user) -> bool:
    """Кому сброс пароля доступен.

    Активный покупатель (не сотрудник) — с паролем либо с другим подтверждённым
    способом входа, который зарегистрировал модуль выше (например, VK ID / Яндекс
    ID: такой аккаунт создан без пароля, а «Забыли пароль» — его путь восстановить
    доступ, если провайдер недоступен). Сотрудники админки (`is_staff`)
    восстанавливают доступ административным порядком.
    """
    if not user.is_active or user.is_staff:
        return False
    if user.has_usable_password():
        return True
    return any(check(user) for check in _reset_checks)
