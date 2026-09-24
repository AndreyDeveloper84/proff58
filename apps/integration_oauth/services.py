"""Сервисный слой входа через VK ID / Яндекс ID: кого впустить, что привязать.

HTTP-слой (views, api) вызывает только эти функции. Правила:

- **Почту от провайдера с существующими аккаунтами не склеиваем.** VK ID не
  сообщает, подтверждена ли почта, и «такая же почта» не доказывает, что это
  владелец аккаунта на сайте. Совпадение → ``email_exists``: войти старым
  способом и привязать провайдера в кабинете.
- Новый аккаунт — только с почтой (менеджер пользователей требует телефон или
  e-mail, а телефон мы у провайдеров не берём) → без почты ``no_email``.
- Привязка (``link``) никогда не впускает другого пользователя: только добавляет
  запись к текущему.
- ``claim_guest_orders`` здесь НЕ вызываем: он переносит гостевые заказы по
  подтверждённому телефону (``phone_verified``), а у пользователей из VK ID /
  Яндекс ID телефона нет вовсе — переносить нечего, а почта не подтверждена.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from . import providers
from .models import OAuthAccount
from .providers import LABELS, ProviderProfile

logger = logging.getLogger(__name__)
User = get_user_model()

#: Текст ошибки отвязки последнего способа входа (контракт кабинета).
LAST_METHOD_DETAIL = (
    "Это единственный способ входа в аккаунт. Сначала задайте пароль или привяжите другой способ."
)


@dataclass
class Result:
    """Итог resolve: ``error`` пустой — успех; иначе код ``oauth_error`` из контракта."""

    user: object | None = None
    error: str = ""
    created: bool = False


def emit(event: str, *, user=None, **params) -> None:
    """Аналитическое событие (без ПДн: ни почты, ни id у провайдера)."""
    payload = {k: v for k, v in params.items() if v is not None}
    logger.info("oauth_event=%s %s", event, payload)
    try:
        from apps.analytics.services import track

        track(event, user=user, payload=payload)
    except Exception:  # аналитика не должна влиять на вход
        logger.debug("analytics track skipped for %s", event, exc_info=True)


# ═══════════ Вход / регистрация ═══════════


def resolve_login(profile: ProviderProfile) -> Result:
    """Найти или создать пользователя по профилю провайдера.

    Гонка (двойной клик, два колбэка параллельно) даёт IntegrityError на одной из
    уникальностей — повторяем разбор один раз: вторая попытка найдёт привязку,
    созданную соседом (→ вход), или его пользователя с той же почтой
    (→ ``email_exists``).
    """
    for attempt in range(2):
        try:
            with transaction.atomic():
                return _resolve_login_once(profile)
        except IntegrityError:
            if attempt:
                logger.warning("OAuth %s: повторный конфликт уникальности", profile.provider)
                return Result(error="failed")
    return Result(error="failed")  # pragma: no cover — цикл всегда возвращает


def _resolve_login_once(profile: ProviderProfile) -> Result:
    now = timezone.now()
    acct = (
        OAuthAccount.objects.select_for_update()
        .select_related("user")
        .filter(provider=profile.provider, provider_user_id=profile.provider_user_id)
        .first()
    )
    if acct is not None:
        user = acct.user
        if user.is_active:
            acct.last_login_at = now
            fields = ["last_login_at"]
            if profile.email and profile.email != acct.email:
                acct.email = profile.email
                fields.append("email")
            if profile.full_name and profile.full_name != acct.full_name:
                acct.full_name = profile.full_name
                fields.append("full_name")
            acct.save(update_fields=fields)
            return Result(user=user)
        if not user.is_anonymized:
            # Заблокирован оператором (не удалён): не заводим обходной аккаунт.
            return Result(error="inactive")
        # Аккаунт удалён покупателем (обезличен): привязка висит на пустом месте.
        # Снимаем её — дальше человек регистрируется заново, как новый.
        acct.delete()
        emit("oauth_account_unlinked", provider=profile.provider, reason="owner_deleted")

    email = profile.email
    if not email:
        return Result(error="no_email")
    if User.objects.filter(email__iexact=email).exists():
        return Result(error="email_exists")

    user = User.objects.create_user(email=email, password=None, full_name=profile.full_name)
    OAuthAccount.objects.create(
        user=user,
        provider=profile.provider,
        provider_user_id=profile.provider_user_id,
        email=email,
        full_name=profile.full_name,
        last_login_at=now,
    )
    _mail_on_commit(user.email, *_created_mail(profile.provider))
    return Result(user=user, created=True)


# ═══════════ Привязка из кабинета ═══════════


def link_account(user, profile: ProviderProfile) -> Result:
    """Привязать аккаунт провайдера к ``user``. Никого, кроме ``user``, не впускает."""
    try:
        with transaction.atomic():
            return _link_once(user, profile)
    except IntegrityError:
        # Соседний запрос успел привязать: к нам — успех, иначе чужая привязка.
        mine = OAuthAccount.objects.filter(
            user=user, provider=profile.provider, provider_user_id=profile.provider_user_id
        ).exists()
        return Result(user=user) if mine else Result(error="already_linked")


def _link_once(user, profile: ProviderProfile) -> Result:
    acct = (
        OAuthAccount.objects.select_for_update()
        .select_related("user")
        .filter(provider=profile.provider, provider_user_id=profile.provider_user_id)
        .first()
    )
    if acct is not None:
        if acct.user_id == user.pk:
            return Result(user=user)  # уже привязан к этому же — ничего не делаем
        if not acct.user.is_anonymized:
            return Result(error="already_linked")
        acct.delete()  # привязка удалённого покупателя — свободна
    if OAuthAccount.objects.filter(user=user, provider=profile.provider).exists():
        # У пользователя уже другой аккаунт этого провайдера: сначала отвязать.
        return Result(error="already_linked")
    OAuthAccount.objects.create(
        user=user,
        provider=profile.provider,
        provider_user_id=profile.provider_user_id,
        email=profile.email,
        full_name=profile.full_name,
    )
    if user.email:
        _mail_on_commit(user.email, *_linked_mail(profile.provider))
    return Result(user=user, created=True)


def has_linked(user, provider: str) -> bool:
    return OAuthAccount.objects.filter(user=user, provider=provider).exists()


# ═══════════ Кабинет: список и отвязка ═══════════


def list_for_user(user) -> list[dict]:
    """Состояние включённых провайдеров для кабинета (контракт GET /api/account/oauth/)."""
    accounts = {a.provider: a for a in OAuthAccount.objects.filter(user=user)}
    result = []
    for provider in providers.enabled_providers():
        acct = accounts.get(provider)
        result.append(
            {
                "id": provider,
                "linked": acct is not None,
                "email": acct.email if acct else "",
                "linked_at": acct.linked_at.isoformat() if acct else None,
                "can_unlink": bool(acct)
                and _has_other_login_method(user, provider, accounts.values()),
            }
        )
    return result


def unlink(user, provider: str) -> str:
    """Отвязать провайдера. Возвращает ``ok`` | ``not_linked`` | ``last_method``."""
    with transaction.atomic():
        accounts = list(OAuthAccount.objects.select_for_update().filter(user=user))
        target = next((a for a in accounts if a.provider == provider), None)
        if target is None:
            return "not_linked"
        if not _has_other_login_method(user, provider, accounts):
            return "last_method"
        target.delete()
    emit("oauth_account_unlinked", user=user, provider=provider, reason="user")
    return "ok"


def _has_other_login_method(user, provider: str, accounts) -> bool:
    """Останется ли у пользователя способ войти без ``provider``."""
    if user.has_usable_password() and user.email:
        return True
    from apps.integration_max.services import can_login_via_max

    if can_login_via_max(user):
        return True
    return any(a.provider != provider and providers.is_enabled(a.provider) for a in accounts)


# ═══════════ Удаление аккаунта и восстановление доступа ═══════════


def drop_user_accounts(user_id: int) -> int:
    """Снять все привязки пользователя (приёмник ``user_deleted``)."""
    deleted, _ = OAuthAccount.objects.filter(user_id=user_id).delete()
    return deleted


def has_oauth_account(user) -> bool:
    """Проверка для сброса пароля: у пользователя без пароля есть вход через провайдера.

    Регистрируется в accounts через ``register_reset_eligibility`` (см. apps.py).
    """
    if user is None or not getattr(user, "pk", None):
        return False
    return OAuthAccount.objects.filter(user=user).exists()


# ═══════════ Письма ═══════════


def _forgot_link() -> str:
    return f"{providers.site_origin()}/account/forgot-password"


def _created_mail(provider: str) -> tuple[str, str]:
    label = LABELS[provider]
    return (
        "Аккаунт создан — «Профессионал»",
        f"Аккаунт на proff58.ru создан через {label}.\n\n"
        "Если это были не вы — восстановите доступ через «Забыли пароль»:\n"
        f"{_forgot_link()}\n",
    )


def _linked_mail(provider: str) -> tuple[str, str]:
    label = LABELS[provider]
    return (
        f"Привязан {label} — «Профессионал»",
        f"К вашему аккаунту на proff58.ru привязан {label} — теперь через него можно входить.\n\n"
        "Если это были не вы — восстановите доступ через «Забыли пароль»:\n"
        f"{_forgot_link()}\n",
    )


def _mail_on_commit(recipient: str, subject: str, body: str) -> None:
    """Письмо после коммита, тем же каналом, что сброс пароля. Сбой не ломает вход."""

    def _send():
        from apps.notifications.channels import email as email_channel

        try:
            email_channel.send_email(subject, body, [recipient])
        except Exception as exc:  # noqa: BLE001 — письмо не важнее входа
            logger.warning("OAuth: письмо не отправлено (%s)", type(exc).__name__)

    transaction.on_commit(_send, robust=True)
