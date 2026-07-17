"""Подписка «Сообщить о поступлении» (#517) — user-owned one-shot подписка на
появление конкретного товара, доставка в MAX.

Модель — в отдельном файле по прецеденту `apps.accounts.wishlist` (#329): нужен
import-trick в конце `apps/catalog/models.py`, иначе Django не видит модель при
makemigrations/reverse-аксессорах до первого lazy-импорта.

Границы: этот модуль — единственный владелец жизненного цикла подписки
(active → queued → notified/cancelled). Доставку делает
`apps.notifications.services.create_notification()`; сам fan-out (Celery-задача,
claim под нагрузкой) — `apps.integration_max.tasks.notify_product_available`
(#518), который импортирует `claim_active_subscriptions`/`mark_notified` отсюда.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

from .filters import visible_products
from .models import Product


class SubscriptionChannel(models.TextChoices):
    MAX = "max", _("MAX")


class SubscriptionStatus(models.TextChoices):
    ACTIVE = "active", _("Активна")
    QUEUED = "queued", _("В очереди на уведомление")
    NOTIFIED = "notified", _("Уведомлён")
    CANCELLED = "cancelled", _("Отменена")


class ProductAvailabilitySubscription(TimeStampedModel):
    """Одна попытка подписки на (user, product, channel) — #517 §Data model.

    Не более одной АКТИВНОЙ подписки на (user, product, channel) — частичный
    unique constraint. Terminal-строки (notified/cancelled) — история, дублировать
    их можно: пользователь может подписаться повторно после нового цикла
    «в наличии → нет → снова в наличии».
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="availability_subscriptions",
        verbose_name=_("Пользователь"),
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="availability_subscriptions",
        verbose_name=_("Товар"),
    )
    channel = models.CharField(
        _("Канал"),
        max_length=10,
        choices=SubscriptionChannel.choices,
        default=SubscriptionChannel.MAX,
    )
    status = models.CharField(
        _("Статус"),
        max_length=10,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.ACTIVE,
        db_index=True,
    )
    subscribed_at = models.DateTimeField(_("Оформлена"), auto_now_add=True)
    queued_at = models.DateTimeField(_("Поставлена в очередь"), null=True, blank=True)
    notified_at = models.DateTimeField(_("Уведомление отправлено"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("Отменена"), null=True, blank=True)

    class Meta:
        verbose_name = _("Подписка на поступление")
        verbose_name_plural = _("Подписки на поступление")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product", "channel"],
                condition=Q(status=SubscriptionStatus.ACTIVE),
                name="uniq_active_availability_subscription",
            )
        ]
        indexes = [models.Index(fields=["product", "status"])]

    def __str__(self) -> str:
        return f"{self.user_id} ⇐ {self.product_id} [{self.status}]"


# ═══════════════════════════════════════════════════════════════════════
# Ошибки правил (#517 AC: actionable error для фронта)
# ═══════════════════════════════════════════════════════════════════════


class SubscriptionError(Exception):
    """Базовая ошибка правил подписки. `.code` — машиночитаемый код для фронта."""

    code = "subscription_error"


class ProductNotEligible(SubscriptionError):
    """Товар не опубликован/скрыт — не палим причину явно (как get_object_or_404)."""

    code = "product_not_found"


class ProductInStock(SubscriptionError):
    code = "product_in_stock"


class MaxConnectionRequired(SubscriptionError):
    code = "max_connection_required"


# ═══════════════════════════════════════════════════════════════════════
# API-facing операции (#517)
# ═══════════════════════════════════════════════════════════════════════


def get_eligible_product(slug: str) -> Product:
    """Товар для подписки: опубликован и видим (#517 Rules). ProductNotEligible,
    если товара с таким slug среди видимых нет — вызывающий сам решает, 404 это
    или что-то ещё (не течёт наружу инфа о скрытых/неопубликованных товарах)."""
    product = visible_products().filter(slug=slug).first()
    if product is None:
        raise ProductNotEligible()
    return product


def get_status(user, product: Product) -> ProductAvailabilitySubscription | None:
    """Активная/queued подписка пользователя на товар, если есть."""
    return (
        ProductAvailabilitySubscription.objects.filter(
            user=user,
            product=product,
            channel=SubscriptionChannel.MAX,
            status__in=(SubscriptionStatus.ACTIVE, SubscriptionStatus.QUEUED),
        )
        .order_by("-subscribed_at")
        .first()
    )


def subscribe(user, product: Product) -> ProductAvailabilitySubscription:
    """Оформить подписку (#517 AC: идемпотентно — повтор возвращает existing active).

    Правила проверяются здесь, а не только в API-слое, чтобы правило нельзя было
    обойти вызовом функции напрямую (напр. из будущей management-команды):
    - товар фактически отсутствует (canonical `available_quantity`, не с фронта);
    - активная привязка MAX обязательна.
    """
    from apps.integration_max.services import has_active_max_account

    if (product.available_quantity or 0) > 0:
        raise ProductInStock()
    if not has_active_max_account(user):
        raise MaxConnectionRequired()

    existing = ProductAvailabilitySubscription.objects.filter(
        user=user,
        product=product,
        channel=SubscriptionChannel.MAX,
        status=SubscriptionStatus.ACTIVE,
    ).first()
    if existing is not None:
        return existing

    return ProductAvailabilitySubscription.objects.create(
        user=user, product=product, channel=SubscriptionChannel.MAX
    )


def unsubscribe(user, product: Product) -> bool:
    """Отменить активную/queued подписку (#517 AC: DELETE повторяем и безопасен).

    True — была активная/queued подписка и она отменена; False — нечего было
    отменять (уже отменена/не существовала) — не ошибка, идемпотентный no-op.
    """
    updated = ProductAvailabilitySubscription.objects.filter(
        user=user,
        product=product,
        channel=SubscriptionChannel.MAX,
        status__in=(SubscriptionStatus.ACTIVE, SubscriptionStatus.QUEUED),
    ).update(status=SubscriptionStatus.CANCELLED, cancelled_at=timezone.now())
    return updated > 0


def cancel_active_for_user(user, *, channel: str = SubscriptionChannel.MAX) -> int:
    """Отменить все активные подписки пользователя на канал (#517 AC: unlink MAX
    не удаляет историю — только переводит active → cancelled; terminal-строки не
    трогает). Вызывается из `apps.integration_max.services.unlink_max`."""
    return ProductAvailabilitySubscription.objects.filter(
        user=user, channel=channel, status=SubscriptionStatus.ACTIVE
    ).update(status=SubscriptionStatus.CANCELLED, cancelled_at=timezone.now())


# ═══════════════════════════════════════════════════════════════════════
# Fan-out операции (#518) — вызываются из apps.integration_max.tasks
# ═══════════════════════════════════════════════════════════════════════


def claim_active_subscriptions(
    product_id: int, *, channel: str = SubscriptionChannel.MAX
) -> list[ProductAvailabilitySubscription]:
    """Атомарно забрать все active-подписки товара под отправку (#518 AC:
    конкурентный claim).

    `select_for_update(skip_locked=True)`: параллельный вызов (дубль Celery-
    доставки, повторный сигнал) видит уже залоченные под первым вызовом строки
    и просто их не берёт — без гонки двойной постановки на отправку. К моменту,
    когда первый вызов коммитит (строки уже `queued`), второй вызов их и вовсе
    не находит — `status=active` больше не матчит.
    """
    with transaction.atomic():
        subs = list(
            ProductAvailabilitySubscription.objects.select_for_update(skip_locked=True)
            .select_related("user")
            .filter(product_id=product_id, channel=channel, status=SubscriptionStatus.ACTIVE)
        )
        ids = [s.pk for s in subs]
        if ids:
            ProductAvailabilitySubscription.objects.filter(pk__in=ids).update(
                status=SubscriptionStatus.QUEUED, queued_at=timezone.now()
            )
    return subs


def mark_notified(subscription_id: int) -> None:
    """one-shot: подписка считается отработанной независимо от того, дошла ли
    реальная доставка (skip по preferences/unlink MAX — тоже терминальный исход
    для ЭТОЙ подписки, не повод слать её снова на следующий импорт остатков)."""
    ProductAvailabilitySubscription.objects.filter(pk=subscription_id).update(
        status=SubscriptionStatus.NOTIFIED, notified_at=timezone.now()
    )
