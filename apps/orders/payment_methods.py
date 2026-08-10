"""Способы оплаты заказа и правила их доступности (DRF-948, DRF-951).

Раньше связка была жёсткой: физлицо — только онлайн, юрлицо — только счёт.
Магазин принимает деньги и в кассе, поэтому при самовывозе появляются наличные
и карта на месте.

Правило намеренно оформлено обычной функцией, а не автоматом состояний: это
таблица «кто и как получает → чем платит», и её должно быть видно целиком.
Авторитетная проверка — на сервере (см. CreateOrderSerializer): браузер решает,
что показать, но не что разрешить.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class PaymentMethod(models.TextChoices):
    """Способ оплаты в снимке заказа."""

    ONLINE = "online", _("Онлайн-оплата")
    INVOICE = "invoice", _("Счёт для организации")
    CASH_ON_PICKUP = "cash", _("Наличными при получении")
    CARD_ON_PICKUP = "card_on_pickup", _("Картой при получении")


#: Оплата на месте: деньги берёт магазин при выдаче, касса сайта не участвует.
ON_PICKUP_METHODS = (PaymentMethod.CASH_ON_PICKUP, PaymentMethod.CARD_ON_PICKUP)


def available_payment_methods(customer_type: str, delivery_method: str) -> list[str]:
    """Чем можно заплатить за такой заказ.

    Юрлицо платит только по счёту — так устроен документооборот, и наличные в
    кассе магазина эту потребность не закрывают.

    Физлицу при самовывозе доступны все три способа: онлайн, наличные и карта
    на месте. При курьерской доставке — только онлайн: оплату курьеру магазин
    не подтверждал, а показывать способ, которого нет, нельзя.
    """
    if (customer_type or "").lower() == "b2b":
        return [PaymentMethod.INVOICE.value]
    if (delivery_method or "") == "pickup":
        return [
            PaymentMethod.ONLINE.value,
            PaymentMethod.CASH_ON_PICKUP.value,
            PaymentMethod.CARD_ON_PICKUP.value,
        ]
    return [PaymentMethod.ONLINE.value]
