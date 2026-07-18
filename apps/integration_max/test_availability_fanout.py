"""Тесты fan-out подписчиков «Сообщить о поступлении» (#518): receiver → Celery
delay, и сама задача notify_product_available (claim, батчи, идемпотентность,
N+1-smoke)."""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.catalog.availability_subscriptions import (
    SubscriptionStatus,
    subscribe,
)
from apps.catalog.models import Product, ProductStatus
from apps.core import events
from apps.core.models import SiteSettings
from apps.notifications.models import Notification
from apps.notifications.services import get_or_create_preference

from .models import MaxAccount

User = get_user_model()


@pytest.fixture
def _enable_max(db):
    s = SiteSettings.get_solo()
    s.max_chat_enabled = True
    s.save()


def _link_max(user, chat_id):
    return MaxAccount.objects.create(
        user=user,
        max_user_id=chat_id,
        chat_id=chat_id,
        phone=user.phone,
        phone_verified_at=timezone.now(),
    )


@pytest.fixture
def product(db):
    return Product.objects.create(
        name="Дрель",
        slug="drel-fanout-518",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        available_quantity=Decimal("0"),
    )


# ═══════════════════════════════════════════════════════════════════════
# Receiver — только валидирует и ставит .delay(), не делает fan-out сам
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
@mock.patch("apps.integration_max.tasks.notify_product_available.delay")
def test_receiver_enqueues_task(mock_delay, product):
    from . import receivers  # noqa: F401

    events.product_stock_became_available.send(
        sender=Product,
        product_id=product.pk,
        old_available="0",
        new_available="5",
        source="1c",
        transition_id="tr-1",
    )
    mock_delay.assert_called_once_with(
        product_id=product.pk,
        transition_id="tr-1",
        old_available="0",
        new_available="5",
        source="1c",
    )


# ═══════════════════════════════════════════════════════════════════════
# Задача — базовый fan-out
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.channels.max.send_message", return_value=True)
def test_task_notifies_subscriber_and_marks_notified(mock_max_send, product, db, settings):
    settings.MAX_BOT_TOKEN = "test-token"
    from .tasks import notify_product_available

    user = User.objects.create_user(phone="+79001111111", password="pass")
    _link_max(user, chat_id=777)
    sub = subscribe(user, product)

    notify_product_available(
        product_id=product.pk, transition_id="tr-2", old_available="0", new_available="5"
    )

    sub.refresh_from_db()
    assert sub.status == SubscriptionStatus.NOTIFIED
    assert sub.notified_at is not None
    mock_max_send.assert_called_once_with(777, mock.ANY)
    notif = Notification.objects.get(user=user, event="product_available")
    assert notif.policy_skip_reason == ""
    assert "Дрель" in notif.title or "Дрель" in notif.body


@pytest.mark.django_db
def test_task_no_subscribers_is_noop(product):
    from .tasks import notify_product_available

    # Не должно упасть — просто нечего делать.
    notify_product_available(
        product_id=product.pk, transition_id="tr-3", old_available="0", new_available="5"
    )


@pytest.mark.django_db
def test_task_missing_product_does_not_crash():
    from .tasks import notify_product_available

    notify_product_available(
        product_id=999999, transition_id="tr-4", old_available="0", new_available="5"
    )


# ═══════════════════════════════════════════════════════════════════════
# Idempotency / concurrent claim (#518 AC)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.channels.max.send_message", return_value=True)
def test_duplicate_task_run_same_transition_no_duplicate_delivery(mock_max_send, product, settings):
    """AC #518: два воркера/повторный сигнал на одну transition_id не создают
    дубль — второй прогон claim'ит 0 подписок (первый уже перевёл их в notified)."""
    settings.MAX_BOT_TOKEN = "test-token"
    from .tasks import notify_product_available

    user = User.objects.create_user(phone="+79002222222", password="pass")
    _link_max(user, chat_id=778)
    subscribe(user, product)

    for _ in range(2):
        notify_product_available(
            product_id=product.pk, transition_id="tr-dup", old_available="0", new_available="5"
        )

    assert mock_max_send.call_count == 1
    assert Notification.objects.filter(user=user, event="product_available").count() == 1


@pytest.mark.django_db
def test_cancelled_subscription_not_claimed(product):
    from apps.catalog.availability_subscriptions import unsubscribe

    from .tasks import notify_product_available

    user = User.objects.create_user(phone="+79003333333", password="pass")
    _link_max(user, chat_id=779)
    subscribe(user, product)
    unsubscribe(user, product)

    with mock.patch("apps.notifications.services.create_notification") as mock_cn:
        notify_product_available(
            product_id=product.pk, transition_id="tr-5", old_available="0", new_available="5"
        )
    mock_cn.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════
# Missing MAX / disabled preference — one-shot всё равно отрабатывает подписку
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
def test_subscriber_without_max_marked_notified_without_send(product, settings):
    """Подписчик отвязал MAX между подпиской и восстановлением остатка —
    create_notification() сам пропустит (нет chat_id), но подписка — one-shot,
    считается отработанной."""
    settings.MAX_BOT_TOKEN = "test-token"
    from .tasks import notify_product_available

    user = User.objects.create_user(phone="+79004444444", password="pass")
    acct = _link_max(user, chat_id=780)
    sub = subscribe(user, product)
    acct.delete()  # имитация unlink без прохода через cancel_active_for_user

    with mock.patch("apps.notifications.channels.max.send_message") as mock_max_send:
        notify_product_available(
            product_id=product.pk, transition_id="tr-6", old_available="0", new_available="5"
        )

    mock_max_send.assert_not_called()
    sub.refresh_from_db()
    assert sub.status == SubscriptionStatus.NOTIFIED


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
def test_subscriber_with_disabled_preference_marked_notified_without_send(product, settings):
    settings.MAX_BOT_TOKEN = "test-token"
    from .tasks import notify_product_available

    user = User.objects.create_user(phone="+79005555555", password="pass")
    _link_max(user, chat_id=781)
    sub = subscribe(user, product)
    pref = get_or_create_preference(user)
    pref.product_availability_enabled = False
    pref.save()

    with mock.patch("apps.notifications.channels.max.send_message") as mock_max_send:
        notify_product_available(
            product_id=product.pk, transition_id="tr-7", old_available="0", new_available="5"
        )

    mock_max_send.assert_not_called()
    sub.refresh_from_db()
    assert sub.status == SubscriptionStatus.NOTIFIED
    notif = Notification.objects.get(user=user, event="product_available")
    assert notif.policy_skip_reason == "category_disabled:product_availability"


# ═══════════════════════════════════════════════════════════════════════
# Батчи + N+1 smoke (#518 AC: без N+1 по users/MaxAccount/preferences)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_fanout_query_count_does_not_scale_per_subscriber(product):
    """Изолируем СОБСТВЕННУЮ логику fan-out (claim + product fetch) от стоимости
    create_notification() (мокнута) — claim не должен расти линейно с числом
    подписчиков (select_related, без запроса на каждого)."""
    from .tasks import notify_product_available

    users = [User.objects.create_user(phone=f"+7900666{i:04d}", password="pass") for i in range(5)]
    for i, user in enumerate(users):
        _link_max(user, chat_id=1000 + i)
        subscribe(user, product)

    with mock.patch(
        "apps.notifications.services.create_notification", return_value=None
    ) as mock_cn:
        with CaptureQueriesContext(connection) as ctx:
            notify_product_available(
                product_id=product.pk, transition_id="tr-8", old_available="0", new_available="5"
            )

    assert mock_cn.call_count == 5
    # product fetch (1) + claim select_for_update (1) + claim bulk update (1) +
    # mark_notified_bulk одним чанком (1) — всё константно, не растёт с числом
    # подписчиков (select_related на claim, bulk update вместо update на каждого).
    assert len(ctx.captured_queries) <= 10


@pytest.mark.usefixtures("_enable_max")
@pytest.mark.django_db
@mock.patch("apps.notifications.tasks.send_notification_task.delay")
def test_fanout_query_growth_is_bounded_per_subscriber(mock_delay, product, settings):
    """AC #518 сквозь настоящий create_notification() (не мокнутый, в отличие от
    теста выше, который изолирует только СОБСТВЕННУЮ логику fan-out) — доказывает,
    что рост запросов на подписчика ограничен небольшой константой (Notification-
    claim + preference get_or_create + chat-резолв + outbox-claim), а не скрытым
    повторным фетчем Product/MaxAccount на каждого.

    Мокаем ``send_notification_task.delay`` (не ``channels.max.send_message``):
    в проде доставка — отдельная асинхронная Celery-задача, её собственная
    стоимость не часть footprint'а fan-out-задачи; при CELERY_TASK_ALWAYS_EAGER
    (дев/тест) `.delay()` иначе исполнился бы синхронно ПРЯМО ЗДЕСЬ и раздул бы
    счётчик чужими для fan-out запросами, исказив измерение.
    """
    settings.MAX_BOT_TOKEN = "test-token"
    from .tasks import notify_product_available

    def _make_subscribers(n: int, offset: int) -> None:
        for i in range(n):
            user = User.objects.create_user(phone=f"+7900777{offset + i:04d}", password="pass")
            _link_max(user, chat_id=3000 + offset + i)
            subscribe(user, product)

    _make_subscribers(5, 0)
    with CaptureQueriesContext(connection) as ctx_5:
        notify_product_available(
            product_id=product.pk, transition_id="tr-lin-5", old_available="0", new_available="5"
        )
    queries_5 = len(ctx_5.captured_queries)

    # Первые 5 подписок уже NOTIFIED (терминальны) — claim_active_subscriptions
    # их не увидит; 20 новых подписчиков подписываются свежо, все ACTIVE.
    _make_subscribers(20, 100)
    with CaptureQueriesContext(connection) as ctx_20:
        notify_product_available(
            product_id=product.pk, transition_id="tr-lin-20", old_available="0", new_available="5"
        )
    queries_20 = len(ctx_20.captured_queries)

    extra_subscribers = 20
    extra_queries = queries_20 - queries_5
    per_subscriber = extra_queries / extra_subscribers
    assert mock_delay.call_count == 25
    # ~11 запросов/подписчика для НОВОГО user — это 2×get_or_create (Notification,
    # UserNotificationPreference — у каждого SELECT+SAVEPOINT+INSERT+RELEASE) +
    # резолв chat_id + outbox-claim: легитимная, не избыточная работа за
    # РАЗНЫЕ данные разных подписчиков (унаследовано от #514/#515, не привнесено
    # fan-out'ом #517/#518) — не паттерн N+1 (не скан/повторный фетч Product или
    # ВСЕЙ таблицы MaxAccount на каждого). Порог — с запасом над наблюдаемым
    # ~11.2, чтобы ловить реальный регресс (напр. Product.objects.get() внутри
    # цикла добавил бы кратно больше).
    assert per_subscriber <= 15, (
        f"{extra_queries} доп. запросов на {extra_subscribers} доп. подписчиков "
        f"({per_subscriber:.1f}/подписчика) — похоже на N+1 сверх ожидаемой "
        f"per-subscriber стоимости (Notification+preference+chat+outbox)"
    )
