"""Подписчики доменных событий: удаление аккаунта снимает привязки VK ID / Яндекс ID.

Обезличенный аккаунт (DeleteAccountView) остаётся в БД строкой с is_active=False —
каскад по FK не срабатывает, поэтому привязки снимаем по событию ``user_deleted``.
Иначе человек, удаливший аккаунт, не смог бы зарегистрироваться заново тем же VK ID.
"""

from __future__ import annotations

import logging

from apps.core import events

logger = logging.getLogger(__name__)


def on_user_deleted(sender, user_id=None, **kwargs) -> None:
    from .services import drop_user_accounts

    if user_id is None:
        return
    removed = drop_user_accounts(user_id)
    if removed:
        logger.info("OAuth: сняты привязки удалённого пользователя (%s шт.)", removed)


events.user_deleted.connect(on_user_deleted, dispatch_uid="integration_oauth.user_deleted")
