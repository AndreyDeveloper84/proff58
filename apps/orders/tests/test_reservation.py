"""Тесты жизненного цикла резерва склада (#423, B-03).

Покрывает: reserve при оформлении (TTL + HELD), release, confirm, идемпотентность
(двойной release/confirm), janitor просрочки, приём событий оплаты.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Product, ProductStatus
from apps.core import events
from apps.orders.models import (
    Order,
    OrderItem,
    PaymentStatus,
    ReservationStatus,
)
from apps.orders.reservation import confirm_reservation, release_reservation
from apps.orders.services import add_to_cart, place_order
from apps.orders.tasks import release_expired_reservations


def _product(qty="10", reserved="0"):
    return Product.objects.create(
        name="Товар",
        code_1c="res-1",
        slug="res-1",
        unit="шт",
        price=Decimal("100.00"),
        currency="RUB",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        available_quantity=Decimal(qty),
        reserved_quantity=Decimal(reserved),
    )


def _order_with_item(product, qty=3, **order_kw):
    defaults = dict(
        order_number=f"RES-{timezone.now().timestamp()}",
        reservation_status=ReservationStatus.HELD,
        customer_phone="+79001112233",
    )
    defaults.update(order_kw)
    order = Order.objects.create(**defaults)
    OrderItem.objects.create(
        order=order,
        product=product,
        quantity=qty,
        price_final=Decimal("100.00"),
        line_total=Decimal("100.00") * qty,
    )
    return order


# ── reserve at checkout ────────────────────────────────────────────────


@pytest.mark.django_db
def test_place_order_sets_held_and_ttl(cart, product):
    product.available_quantity = Decimal("5")
    product.save(update_fields=["available_quantity"])
    add_to_cart(cart, product, 2)

    order = place_order(
        cart,
        user=None,
        customer_data={"customer_name": "Гость", "customer_phone": "+79990099099"},
    )
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.HELD
    assert order.reserved_until is not None
    assert order.reserved_until > timezone.now()


# ── release ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_release_returns_stock_and_marks_released():
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    assert release_reservation(order.pk) is True
    p.refresh_from_db()
    assert p.available_quantity == Decimal("10")  # 7 + 3
    assert p.reserved_quantity == Decimal("0")  # 3 - 3
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.RELEASED


@pytest.mark.django_db
def test_release_idempotent_no_double_restore():
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    assert release_reservation(order.pk) is True
    assert release_reservation(order.pk) is False  # уже released
    p.refresh_from_db()
    assert p.available_quantity == Decimal("10")  # без двойного возврата
    assert p.reserved_quantity == Decimal("0")


# ── confirm ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_confirm_drops_reserved_keeps_available():
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    assert confirm_reservation(order.pk) is True
    p.refresh_from_db()
    assert p.available_quantity == Decimal("7")  # не меняется — товар уже ушёл из available
    assert p.reserved_quantity == Decimal("0")  # 3 - 3
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.CONFIRMED


@pytest.mark.django_db
def test_confirm_idempotent():
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    assert confirm_reservation(order.pk) is True
    assert confirm_reservation(order.pk) is False
    p.refresh_from_db()
    assert p.reserved_quantity == Decimal("0")


@pytest.mark.django_db
def test_confirmed_cannot_be_released():
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)
    confirm_reservation(order.pk)

    assert release_reservation(order.pk) is False  # CONFIRMED терминален для release
    p.refresh_from_db()
    assert p.available_quantity == Decimal("7")  # не восстановился


# ── janitor ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_janitor_releases_expired_unpaid():
    p = _product(qty="7", reserved="3")
    order = _order_with_item(
        p,
        qty=3,
        reserved_until=timezone.now() - timedelta(minutes=1),
        payment_status=PaymentStatus.PENDING,
    )

    assert release_expired_reservations() == 1
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.RELEASED
    p.refresh_from_db()
    assert p.available_quantity == Decimal("10")


@pytest.mark.django_db
def test_janitor_skips_paid_orders():
    p = _product(qty="7", reserved="3")
    _order_with_item(
        p,
        qty=3,
        reserved_until=timezone.now() - timedelta(minutes=1),
        payment_status=PaymentStatus.PAID,
    )

    assert release_expired_reservations() == 0
    p.refresh_from_db()
    assert p.reserved_quantity == Decimal("3")  # не тронут


@pytest.mark.django_db
def test_janitor_skips_not_yet_expired():
    p = _product(qty="7", reserved="3")
    _order_with_item(
        p,
        qty=3,
        reserved_until=timezone.now() + timedelta(hours=1),
        payment_status=PaymentStatus.PENDING,
    )

    assert release_expired_reservations() == 0
    p.refresh_from_db()
    assert p.reserved_quantity == Decimal("3")


# ── payment events → confirm/release ───────────────────────────────────


@pytest.mark.django_db
def test_payment_succeeded_confirms_reservation():
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    events.payment_succeeded.send(sender=None, order_id=order.pk, payment_id=1)
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.CONFIRMED


@pytest.mark.django_db
def test_payment_failed_releases_reservation():
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    events.payment_failed.send(sender=None, order_id=order.pk, payment_id=1, reason="expired")
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.RELEASED
    p.refresh_from_db()
    assert p.available_quantity == Decimal("10")


@pytest.mark.django_db
def test_repeat_payment_succeeded_is_idempotent():
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    events.payment_succeeded.send(sender=None, order_id=order.pk, payment_id=1)
    events.payment_succeeded.send(sender=None, order_id=order.pk, payment_id=1)
    p.refresh_from_db()
    assert p.reserved_quantity == Decimal("0")  # без двойного списания


# ── TTL по типу покупателя (#568) ──────────────────────────────────────


def _ttl_window(before, after, delta: timedelta):
    """Интервал допустимых значений reserved_until для TTL, взятого до/после вызова."""
    return before + delta, after + delta


B2B_DATA = {
    "customer_name": "Иван Петров",
    "customer_phone": "+79001234567",
    "customer_email": "buh@romashka.ru",
    "customer_type": "b2b",
    "company_name": "ООО «Ромашка»",
    "inn": "7700000000",
    "kpp": "770001001",
    "legal_address": "г. Пенза, ул. Ленина, 1",
}


@pytest.mark.django_db
def test_b2c_reservation_ttl_is_30_minutes(cart, product):
    add_to_cart(cart, product, 1)
    before = timezone.now()
    order = place_order(
        cart,
        user=None,
        customer_data={"customer_name": "Гость", "customer_phone": "+79990099099"},
    )
    after = timezone.now()
    lo, hi = _ttl_window(before, after, timedelta(minutes=30))
    assert lo <= order.reserved_until <= hi


@pytest.mark.django_db
def test_b2c_ttl_configurable(cart, product, settings):
    settings.RESERVATION_TTL_B2C_MINUTES = 5
    add_to_cart(cart, product, 1)
    before = timezone.now()
    order = place_order(
        cart,
        user=None,
        customer_data={"customer_name": "Гость", "customer_phone": "+79990099099"},
    )
    after = timezone.now()
    lo, hi = _ttl_window(before, after, timedelta(minutes=5))
    assert lo <= order.reserved_until <= hi


@pytest.mark.django_db
def test_authenticated_b2c_ttl_is_30_minutes(cart, product, b2c_user):
    add_to_cart(cart, product, 1)
    before = timezone.now()
    order = place_order(cart, user=b2c_user, customer_data={})
    after = timezone.now()
    lo, hi = _ttl_window(before, after, timedelta(minutes=30))
    assert lo <= order.reserved_until <= hi


@pytest.mark.django_db
def test_b2b_reservation_ttl_stays_24_hours(cart, product, b2b_user):
    add_to_cart(cart, product, 1)
    before = timezone.now()
    order = place_order(cart, user=b2b_user, customer_data={})
    after = timezone.now()
    lo, hi = _ttl_window(before, after, timedelta(hours=24))
    assert lo <= order.reserved_until <= hi
    # Инвариант #559: счёт и резерв истекают вместе.
    assert order.b2b_invoice.valid_until == order.reserved_until


@pytest.mark.django_db
def test_guest_b2b_ttl_stays_24_hours(cart, product):
    """Гостевой B2B (customer_type из тела) тоже получает 24ч, а не 30 мин."""
    add_to_cart(cart, product, 1)
    before = timezone.now()
    order = place_order(cart, user=None, customer_data=dict(B2B_DATA))
    after = timezone.now()
    lo, hi = _ttl_window(before, after, timedelta(hours=24))
    assert lo <= order.reserved_until <= hi


# ── удаление заказа мимо release_reservation (DRF-1002) ────────────────


@pytest.mark.django_db
def test_delete_order_instance_returns_stock():
    """Удаление объекта (админка вызывает именно его) снимает резерв."""
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    order.delete()

    p.refresh_from_db()
    assert p.available_quantity == Decimal("10")  # 7 + 3
    assert p.reserved_quantity == Decimal("0")


@pytest.mark.django_db
def test_delete_order_via_queryset_returns_stock():
    """Массовое удаление тоже снимает резерв: сигнал отключает fast-delete."""
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    Order.objects.filter(pk=order.pk).delete()

    p.refresh_from_db()
    assert p.available_quantity == Decimal("10")
    assert p.reserved_quantity == Decimal("0")


@pytest.mark.django_db
def test_delete_after_release_does_not_restore_twice():
    """Штатный путь не ломается: резерв уже возвращён, удаление ничего не добавляет."""
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)
    assert release_reservation(order.pk) is True

    order.delete()

    p.refresh_from_db()
    assert p.available_quantity == Decimal("10")  # ровно один возврат
    assert p.reserved_quantity == Decimal("0")


@pytest.mark.django_db
def test_delete_confirmed_order_keeps_stock():
    """CONFIRMED — товар уже ушёл; удаление заказа не возвращает его на склад."""
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)
    assert confirm_reservation(order.pk) is True

    order.delete()

    p.refresh_from_db()
    assert p.available_quantity == Decimal("7")
    assert p.reserved_quantity == Decimal("0")


@pytest.mark.django_db
def test_delete_product_then_order_does_not_break():
    """Удалили товар — возвращать остаток некуда; строка заказа переживает (SET_NULL)."""
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    p.delete()
    item = OrderItem.objects.get(order=order)
    assert item.product_id is None

    order.delete()  # не падает: строки без товара пропускаются

    assert not Order.objects.filter(pk=order.pk).exists()


# ── повторное удержание после снятия резерва (DRF-2299, оплата позже) ──────


@pytest.mark.django_db
def test_rehold_after_release_holds_stock_again():
    from apps.orders.reservation import rehold_reservation

    p = _product(qty="10", reserved="0")
    order = _order_with_item(p, qty=3, reservation_status=ReservationStatus.RELEASED)

    ok, reason = rehold_reservation(order.pk, ttl=timedelta(hours=24))

    assert ok and reason == ""
    p.refresh_from_db()
    order.refresh_from_db()
    assert p.available_quantity == Decimal("7") and p.reserved_quantity == Decimal("3")
    assert order.reservation_status == ReservationStatus.HELD
    assert order.reserved_until > timezone.now() + timedelta(hours=23)


@pytest.mark.django_db
def test_rehold_refuses_when_stock_is_short_and_changes_nothing():
    from apps.orders.reservation import rehold_reservation

    p = _product(qty="2", reserved="0")
    order = _order_with_item(p, qty=3, reservation_status=ReservationStatus.RELEASED)

    ok, reason = rehold_reservation(order.pk, ttl=timedelta(hours=1))

    assert not ok and "нет в наличии" in reason
    p.refresh_from_db()
    order.refresh_from_db()
    assert p.available_quantity == Decimal("2") and p.reserved_quantity == Decimal("0")
    assert order.reservation_status == ReservationStatus.RELEASED


@pytest.mark.django_db
def test_rehold_all_or_nothing_across_lines():
    from apps.orders.reservation import rehold_reservation

    p1 = _product(qty="10", reserved="0")
    p2 = Product.objects.create(
        name="Второй",
        code_1c="res-2",
        slug="res-2",
        unit="шт",
        price=Decimal("50.00"),
        currency="RUB",
        status=ProductStatus.PUBLISHED,
        is_active=True,
        available_quantity=Decimal("0"),
    )
    order = _order_with_item(p1, qty=1, reservation_status=ReservationStatus.RELEASED)
    OrderItem.objects.create(
        order=order,
        product=p2,
        quantity=1,
        price_final=Decimal("50.00"),
        line_total=Decimal("50.00"),
    )

    ok, _ = rehold_reservation(order.pk, ttl=timedelta(hours=1))

    assert not ok
    p1.refresh_from_db()
    assert p1.available_quantity == Decimal("10")  # первую строку не списали


@pytest.mark.django_db
def test_rehold_when_held_only_extends_deadline():
    from apps.orders.reservation import rehold_reservation

    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)  # HELD
    order.reserved_until = timezone.now() + timedelta(minutes=5)
    order.save(update_fields=["reserved_until"])

    ok, _ = rehold_reservation(order.pk, ttl=timedelta(hours=24))

    assert ok
    p.refresh_from_db()
    order.refresh_from_db()
    assert p.available_quantity == Decimal("7") and p.reserved_quantity == Decimal("3")
    assert order.reserved_until > timezone.now() + timedelta(hours=23)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "kw,reason",
    [
        ({"reservation_status": ReservationStatus.CONFIRMED}, "уже списан"),
        ({"reservation_status": ReservationStatus.RELEASED, "payment_status": "paid"}, "оплачен"),
        (
            {"reservation_status": ReservationStatus.RELEASED, "fulfillment_status": "cancelled"},
            "отменён",
        ),
    ],
)
def test_rehold_refuses_terminal_orders(kw, reason):
    from apps.orders.reservation import rehold_reservation

    p = _product(qty="10", reserved="0")
    order = _order_with_item(p, qty=1, **kw)
    ok, why = rehold_reservation(order.pk, ttl=timedelta(hours=1))
    assert not ok and reason in why
    p.refresh_from_db()
    assert p.available_quantity == Decimal("10")


@pytest.mark.django_db
def test_janitor_does_not_release_reservation_extended_after_selection():
    """Гонка с janitor: срок продлили (rehold) между выборкой и обработкой — резерв остаётся."""
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)
    order.reserved_until = timezone.now() + timedelta(hours=1)  # уже продлён
    order.save(update_fields=["reserved_until"])

    assert release_reservation(order.pk, only_if_expired=True) is False
    p.refresh_from_db()
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.HELD
    assert p.available_quantity == Decimal("7")

    order.reserved_until = timezone.now() - timedelta(minutes=1)
    order.save(update_fields=["reserved_until"])
    assert release_reservation(order.pk, only_if_expired=True) is True


@pytest.mark.django_db
def test_rehold_sums_same_product_across_lines():
    from apps.orders.reservation import rehold_reservation

    p = _product(qty="5", reserved="0")
    order = _order_with_item(p, qty=3, reservation_status=ReservationStatus.RELEASED)
    OrderItem.objects.create(
        order=order,
        product=p,
        quantity=3,
        price_final=Decimal("100.00"),
        line_total=Decimal("300.00"),
    )
    ok, reason = rehold_reservation(order.pk, ttl=timedelta(hours=1))
    assert not ok and "нет в наличии" in reason  # нужно 6, есть 5
    p.refresh_from_db()
    assert p.available_quantity == Decimal("5")


# ── DRF-2736: оплата в конце окна резерва и после его снятия ────────────────


@pytest.mark.django_db
def test_rehold_when_held_never_shortens_deadline():
    """После ручного расчёта доставки резерв держится 24 часа. «Оплатить» зовёт
    rehold с получасовым окном — срок от этого не должен сжиматься."""
    from apps.orders.reservation import rehold_reservation

    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)
    long_deadline = timezone.now() + timedelta(hours=20)
    order.reserved_until = long_deadline
    order.save(update_fields=["reserved_until"])

    ok, _ = rehold_reservation(order.pk, ttl=timedelta(minutes=30))

    assert ok
    order.refresh_from_db()
    assert order.reserved_until == long_deadline


@pytest.mark.django_db
def test_janitor_keeps_reservation_of_paid_order():
    """Оплата зафиксирована, списание резерва идёт следом (on_commit). Janitor в
    этом окне не должен вернуть в продажу оплаченный товар."""
    p = _product(qty="7", reserved="3")
    order = _order_with_item(
        p,
        qty=3,
        payment_status=PaymentStatus.PAID,
        reserved_until=timezone.now() - timedelta(minutes=1),
    )

    assert release_reservation(order.pk, only_if_expired=True) is False

    p.refresh_from_db()
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.HELD
    assert p.available_quantity == Decimal("7") and p.reserved_quantity == Decimal("3")


@pytest.mark.django_db
def test_confirm_or_take_held_confirms_like_before():
    from apps.orders.reservation import confirm_or_take

    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    assert confirm_or_take(order.pk) is True

    p.refresh_from_db()
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.CONFIRMED
    assert p.available_quantity == Decimal("7") and p.reserved_quantity == Decimal("0")


@pytest.mark.django_db
def test_confirm_or_take_after_release_takes_stock_again():
    """Резерв сняли (истёк срок, пока покупатель был в банке), оплата прошла, товар
    ещё есть — берём его заново и сразу списываем: продаваться дальше он не должен."""
    from apps.orders.reservation import confirm_or_take

    p = _product(qty="10", reserved="0")
    order = _order_with_item(p, qty=3, reservation_status=ReservationStatus.RELEASED)

    assert confirm_or_take(order.pk) is True

    p.refresh_from_db()
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.CONFIRMED
    assert p.available_quantity == Decimal("7")
    assert p.reserved_quantity == Decimal("0")  # удержания не было — списали сразу


@pytest.mark.django_db
def test_confirm_or_take_after_release_without_stock_changes_nothing():
    from apps.orders.reservation import confirm_or_take

    p = _product(qty="2", reserved="0")
    order = _order_with_item(p, qty=3, reservation_status=ReservationStatus.RELEASED)

    assert confirm_or_take(order.pk) is False

    p.refresh_from_db()
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.RELEASED
    assert p.available_quantity == Decimal("2") and p.reserved_quantity == Decimal("0")


@pytest.mark.django_db
def test_confirm_or_take_sums_same_product_across_lines():
    from apps.orders.reservation import confirm_or_take

    p = _product(qty="5", reserved="0")
    order = _order_with_item(p, qty=3, reservation_status=ReservationStatus.RELEASED)
    OrderItem.objects.create(
        order=order,
        product=p,
        quantity=3,
        price_final=Decimal("100.00"),
        line_total=Decimal("300.00"),
    )

    assert confirm_or_take(order.pk) is False  # нужно 6, есть 5

    p.refresh_from_db()
    assert p.available_quantity == Decimal("5")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "kw",
    [
        {"reservation_status": ReservationStatus.CONFIRMED},  # счёт оплачен: уже списано
        {"reservation_status": ReservationStatus.NONE},  # заказ без резерва
        # Отменённый заказ товар не занимает — поздней оплатой занимается payments.
        {"reservation_status": ReservationStatus.RELEASED, "fulfillment_status": "cancelled"},
    ],
)
def test_confirm_or_take_leaves_stock_alone_when_nothing_to_take(kw):
    from apps.orders.reservation import confirm_or_take

    p = _product(qty="10", reserved="0")
    order = _order_with_item(p, qty=3, **kw)

    assert confirm_or_take(order.pk) is True  # не «товара нет» — письма сотрудникам не будет

    p.refresh_from_db()
    order.refresh_from_db()
    assert p.available_quantity == Decimal("10") and p.reserved_quantity == Decimal("0")
    assert order.reservation_status == kw["reservation_status"]


@pytest.fixture
def staff_mail(settings):
    settings.STAFF_NOTIFICATION_EMAILS = ["manager@example.com"]
    settings.DEFAULT_FROM_EMAIL = "site@example.com"
    settings.SITE_URL = "https://proff58.ru"


def _paid_without_stock_logs(order):
    from apps.notifications.models import NotificationLog

    return NotificationLog.objects.filter(idempotency_key=f"staff-paid-without-stock-{order.pk}")


@pytest.mark.django_db
def test_payment_after_release_takes_stock_and_sends_no_letter(staff_mail):
    from django.core import mail

    p = _product(qty="10", reserved="0")
    order = _order_with_item(p, qty=3, reservation_status=ReservationStatus.RELEASED)

    events.payment_succeeded.send(sender=None, order_id=order.pk, payment_id=1)

    p.refresh_from_db()
    assert p.available_quantity == Decimal("7")
    assert mail.outbox == []


@pytest.mark.django_db
def test_payment_without_stock_tells_staff_once(staff_mail):
    """Оплачен, а товар уже купили: сотрудники получают письмо — одно, даже если
    событие оплаты повторилось."""
    from django.core import mail

    p = _product(qty="1", reserved="0")
    order = _order_with_item(
        p, qty=3, reservation_status=ReservationStatus.RELEASED, customer_name="Иван"
    )

    events.payment_succeeded.send(sender=None, order_id=order.pk, payment_id=1)
    events.payment_succeeded.send(sender=None, order_id=order.pk, payment_id=1)

    assert len(mail.outbox) == 1
    letter = mail.outbox[0]
    assert order.order_number in letter.subject
    assert "заявка на" in letter.body and "возврат" in letter.body
    assert f"/admin/orders/order/{order.pk}/change/" in letter.body
    assert _paid_without_stock_logs(order).count() == 1
    p.refresh_from_db()
    assert p.available_quantity == Decimal("1")  # чужой товар не тронут


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status", [ReservationStatus.CONFIRMED, ReservationStatus.NONE, ReservationStatus.HELD]
)
def test_payment_sends_no_letter_when_stock_is_fine(staff_mail, status):
    from django.core import mail

    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3, reservation_status=status)

    events.payment_succeeded.send(sender=None, order_id=order.pk, payment_id=1)

    assert mail.outbox == []
    assert not _paid_without_stock_logs(order).exists()


@pytest.mark.django_db
def test_payment_subscriber_survives_reservation_failure(staff_mail, monkeypatch):
    """Событие оплаты издаётся из on_commit: исключение подписчика оборвало бы
    цепочку, и ``order_paid`` не ушёл бы вовсе. Сбой списания — письмо людям, а
    не исключение."""
    from django.core import mail

    from apps.orders import receivers

    def boom(order_id):
        raise RuntimeError("deadlock detected")

    monkeypatch.setattr(receivers, "confirm_or_take", boom)
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    responses = events.payment_succeeded.send(sender=None, order_id=order.pk, payment_id=1)

    assert all(not isinstance(resp, Exception) for _, resp in responses)
    assert len(mail.outbox) == 1
    assert order.order_number in mail.outbox[0].subject


# ── DRF-2736: честный статус «отменён, оплата получена» ─────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payment_status,expected",
    [
        ("paid", "вернём деньги"),
        ("partially_refunded", "вернём деньги"),
    ],
)
def test_display_status_of_cancelled_order_with_money(payment_status, expected):
    order = Order.objects.create(
        order_number=f"DS-{payment_status}",
        fulfillment_status="cancelled",
        payment_status=payment_status,
        customer_phone="+79001112233",
    )
    assert "отменён" in order.display_status.lower()
    assert expected in order.display_status


@pytest.mark.django_db
@pytest.mark.parametrize("payment_status", ["pending", "expired", "refunded"])
def test_display_status_of_cancelled_order_without_money(payment_status):
    order = Order.objects.create(
        order_number=f"DS-{payment_status}",
        fulfillment_status="cancelled",
        payment_status=payment_status,
        customer_phone="+79001112233",
    )
    assert "вернём деньги" not in order.display_status


@pytest.mark.django_db
def test_confirm_or_take_does_not_write_off_stock_of_cancelled_order():
    """Заказ отменён, а резерв ещё HELD (отмена от 1С снимает его после коммита).
    Событие оплаты в этом окне не должно списать товар под заказ, которого нет."""
    from apps.orders.reservation import confirm_or_take

    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3, fulfillment_status="cancelled")  # HELD

    assert confirm_or_take(order.pk) is True

    p.refresh_from_db()
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.HELD
    assert p.reserved_quantity == Decimal("3")  # вернёт в остаток release отмены

    assert release_reservation(order.pk) is True
    p.refresh_from_db()
    assert p.available_quantity == Decimal("10") and p.reserved_quantity == Decimal("0")


@pytest.mark.django_db
def test_rehold_after_release_never_shortens_deadline_either():
    """После неудачного расчёта доставки заказу даются сутки (срок без удержания).
    Повторное удержание при «Оплатить» не должно сжать их до получаса."""
    from apps.orders.reservation import rehold_reservation

    p = _product(qty="10", reserved="0")
    order = _order_with_item(p, qty=3, reservation_status=ReservationStatus.RELEASED)
    day = timezone.now() + timedelta(hours=20)
    order.reserved_until = day
    order.save(update_fields=["reserved_until"])

    ok, _ = rehold_reservation(order.pk, ttl=timedelta(minutes=30))

    assert ok
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.HELD
    assert order.reserved_until == day


@pytest.mark.django_db
def test_rehold_extension_is_capped_but_rehold_itself_is_not():
    from apps.orders.reservation import PAY_WINDOW_CLOSED, rehold_reservation

    p = _product(qty="10", reserved="3")
    now = timezone.now()
    held = _order_with_item(p, qty=3, reserved_until=now + timedelta(minutes=5))
    cap = now + timedelta(minutes=10)

    ok, _ = rehold_reservation(held.pk, ttl=timedelta(minutes=30), not_after=cap)
    held.refresh_from_db()
    assert ok and held.reserved_until == cap  # продлили, но не дальше потолка

    # Срок вышел, потолок позади — продлевать нечем, в кассу не отправляем.
    held.reserved_until = now - timedelta(minutes=1)
    held.save(update_fields=["reserved_until"])
    ok, reason = rehold_reservation(
        held.pk, ttl=timedelta(minutes=30), not_after=now - timedelta(hours=1)
    )
    assert not ok and reason == PAY_WINDOW_CLOSED

    # Снятый резерв удерживается заново и за потолком: иначе оплатить заказ, к
    # которому вернулись позже, было бы нельзя вовсе.
    released = _order_with_item(p, qty=1, reservation_status=ReservationStatus.RELEASED)
    ok, _ = rehold_reservation(
        released.pk, ttl=timedelta(minutes=30), not_after=now - timedelta(hours=1)
    )
    released.refresh_from_db()
    assert ok and released.reserved_until > now + timedelta(minutes=29)


@pytest.mark.django_db
def test_payment_subscriber_retries_once_on_deadlock(staff_mail, monkeypatch):
    """Дедлок с пакетной заливкой остатков: проигравшая транзакция откатилась целиком,
    повтор безопасен — и письмо сотрудникам не нужно."""
    from django.core import mail

    from apps.orders import receivers

    real = receivers.confirm_or_take
    calls = []

    def flaky(order_id):
        calls.append(order_id)
        if len(calls) == 1:
            raise RuntimeError("deadlock detected")
        return real(order_id)

    monkeypatch.setattr(receivers, "confirm_or_take", flaky)
    p = _product(qty="7", reserved="3")
    order = _order_with_item(p, qty=3)

    events.payment_succeeded.send(sender=None, order_id=order.pk, payment_id=1)

    order.refresh_from_db()
    assert len(calls) == 2
    assert order.reservation_status == ReservationStatus.CONFIRMED
    assert mail.outbox == []


@pytest.mark.django_db
def test_invoice_paid_after_reservation_release_takes_stock_again(staff_mail):
    """Счёт организации отметили оплаченным, когда общий janitor уже снял резерв:
    товар берётся заново, ложного письма «оплачен без товара» нет."""
    from django.core import mail

    p = _product(qty="10", reserved="0")
    order = _order_with_item(
        p, qty=3, reservation_status=ReservationStatus.RELEASED, payment_status=PaymentStatus.PAID
    )

    events.payment_succeeded.send(sender=None, order_id=order.pk, payment_id=None)

    p.refresh_from_db()
    order.refresh_from_db()
    assert order.reservation_status == ReservationStatus.CONFIRMED
    assert p.available_quantity == Decimal("7")
    assert mail.outbox == []
