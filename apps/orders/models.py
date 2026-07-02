"""Модели заказов и корзины — коммерческий backbone (итерация 1, #26).

Ключевые принципы:

- Статусы заказа живут на ТРЁХ независимых осях (обработка / оплата / выгрузка
  в 1С) — источник истины ``docs/order-lifecycle.md``. Один человекочитаемый
  статус собирается производным свойством :pyattr:`Order.display_status`.
- Заказ хранит СНИМКИ (покупателя, строк, цены): данные заказа не должны
  «плыть» при последующих изменениях товара/цены/профиля.
- Цену в корзине НЕ храним — она считается на лету через ``pricing.price_for``
  (ADR-0006). В заказе фиксируется снимок цены на момент оформления.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import CustomerType
from apps.core.models import TimeStampedModel


# ---------------------------------------------------------------------------
# Оси статусов заказа (строго по docs/order-lifecycle.md)
# ---------------------------------------------------------------------------
class FulfillmentStatus(models.TextChoices):
    """Ось обработки: бизнес-движение заказа от оформления до выдачи."""

    NEW = "new", _("Новый")
    CONFIRMED = "confirmed", _("Подтверждён")
    ASSEMBLING = "assembling", _("Собирается")
    READY = "ready", _("Готов к выдаче")
    SHIPPED = "shipped", _("В доставке")
    COMPLETED = "completed", _("Выполнен")
    CANCELLED = "cancelled", _("Отменён")


class PaymentStatus(models.TextChoices):
    """Ось оплаты: движение денег."""

    PENDING = "pending", _("Ожидает оплаты")
    PAID = "paid", _("Оплачен")
    EXPIRED = "expired", _("Просрочена оплата")
    PARTIALLY_REFUNDED = "partially_refunded", _("Частичный возврат")
    REFUNDED = "refunded", _("Возврат")


class Sync1CStatus(models.TextChoices):
    """Ось выгрузки в 1С: 1С сама забирает заказ с сайта."""

    PENDING = "pending", _("Ожидает выгрузки")
    EXPORTED = "exported", _("Выгружен в 1С")


class ReservationStatus(models.TextChoices):
    """Состояние резерва склада под заказ (#423, B-03).

    Жизненный цикл: NONE → HELD → (RELEASED | CONFIRMED). RELEASED/CONFIRMED —
    терминальные: переходы идемпотентны (повторный release/confirm — no-op).
    """

    NONE = "none", _("Без резерва")
    HELD = "held", _("Удержан")
    RELEASED = "released", _("Возвращён")
    CONFIRMED = "confirmed", _("Списан")


class DeliveryCalcStatus(models.TextChoices):
    """Статус расчёта стоимости доставки (#429, M-05, ADR #444).

    NOT_REQUIRED — доставка не выбрана/не требует расчёта; CALCULATED — стоимость
    посчитана сервером; MANUAL_REQUIRED — авторасчёт невозможен (нет весогабаритов
    для СДЭК): стоимость определит менеджер, итог предварительный, финальный счёт
    не выпускается до ввода стоимости.
    """

    NOT_REQUIRED = "not_required", _("Не требуется")
    CALCULATED = "calculated", _("Рассчитана")
    MANUAL_REQUIRED = "manual_required", _("Ручной расчёт")


# ---------------------------------------------------------------------------
# Заказ
# ---------------------------------------------------------------------------
class Order(TimeStampedModel):
    """Заказ — снимок коммерческой операции на момент оформления."""

    # --- Идентификаторы ---
    order_number = models.CharField(
        _("Номер заказа"),
        max_length=32,
        unique=True,
        help_text=_("Человекочитаемый уникальный номер, генерируется при оформлении."),
    )
    external_order_id = models.CharField(  # noqa: DJ001 — null отличает «не выгружен» от пустого
        _("ID заказа в 1С"),
        max_length=64,
        null=True,
        blank=True,
        help_text=_("Стабильный технический идентификатор документа 1С (onec_order_id)."),
    )
    external_order_number = models.CharField(
        _("Номер документа 1С"),
        max_length=64,
        blank=True,
        help_text=_("Человекочитаемый номер документа 1С, напр. УТ-000987."),
    )
    tracking_number = models.CharField(
        _("Трек-номер доставки"),
        max_length=128,
        blank=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name=_("Покупатель"),
        help_text=_("null — гостевой заказ. SET_NULL: заказ переживает удаление пользователя."),
    )

    # --- Три оси статусов ---
    fulfillment_status = models.CharField(
        _("Статус обработки"),
        max_length=12,
        choices=FulfillmentStatus.choices,
        default=FulfillmentStatus.NEW,
        db_index=True,
    )
    payment_status = models.CharField(
        _("Статус оплаты"),
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True,
    )
    sync_1c_status = models.CharField(
        _("Статус выгрузки в 1С"),
        max_length=12,
        choices=Sync1CStatus.choices,
        default=Sync1CStatus.PENDING,
        db_index=True,
    )

    # --- Снимок покупателя ---
    customer_name = models.CharField(_("ФИО / контактное лицо"), max_length=255, blank=True)
    customer_phone = models.CharField(_("Телефон"), max_length=20, blank=True)
    customer_email = models.EmailField(_("E-mail"), blank=True)
    customer_type = models.CharField(
        _("Тип покупателя"),
        max_length=3,
        choices=CustomerType.choices,
        default=CustomerType.B2C,
    )

    # --- Снимок реквизитов B2B (копия Profile на момент заказа) ---
    company_name = models.CharField(_("Название организации"), max_length=255, blank=True)
    inn = models.CharField(_("ИНН"), max_length=12, blank=True)
    kpp = models.CharField(_("КПП"), max_length=9, blank=True)
    legal_address = models.CharField(_("Юридический адрес"), max_length=512, blank=True)

    # --- Доставка / оплата ---
    delivery_method = models.CharField(_("Способ доставки"), max_length=64, blank=True)
    delivery_address = models.CharField(_("Адрес доставки"), max_length=512, blank=True)
    comment = models.TextField(_("Комментарий к заказу"), blank=True)
    payment_method = models.CharField(
        _("Способ оплаты"),
        max_length=32,
        blank=True,
        help_text=_("Заглушка-выбор (без онлайн-оплаты в #26)."),
    )

    # --- Снимок доставки (#429, M-05, ADR #444) ---
    delivery_zone = models.CharField(_("Зона доставки (slug)"), max_length=100, blank=True)
    delivery_cost = models.DecimalField(
        _("Стоимость доставки"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("null = стоимость ещё не определена (ручной расчёт менеджером)."),
    )
    delivery_calc_status = models.CharField(
        _("Статус расчёта доставки"),
        max_length=16,
        choices=DeliveryCalcStatus.choices,
        default=DeliveryCalcStatus.NOT_REQUIRED,
        db_index=True,
    )
    delivery_snapshot = models.JSONField(_("Снимок тарифа доставки"), default=dict, blank=True)

    # --- Итоги ---
    total = models.DecimalField(
        _("Сумма заказа"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_(
            "Товары + доставка, с НДС. При manual_required — предварительный (только товары)."
        ),
    )
    currency = models.CharField(_("Валюта"), max_length=3, default="RUB")

    # --- Снимок НДС (#430, M-06). Цена включает НДС; ставка фиксируется на момент
    # заказа. Для B2B заполняется; для B2C остаётся нулевой (розничный чек без
    # выделения налога). amount_with_vat == total. ---
    vat_rate = models.PositiveSmallIntegerField(_("Ставка НДС, %"), default=0)
    vat_amount = models.DecimalField(
        _("Сумма НДС"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    amount_without_vat = models.DecimalField(
        _("Сумма без НДС"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )

    # --- Резерв склада (#423, B-03) ---
    reserved_until = models.DateTimeField(
        _("Резерв до"),
        null=True,
        blank=True,
        help_text=_("TTL резерва: после этого момента janitor освобождает неоплаченный резерв."),
    )
    reservation_status = models.CharField(
        _("Статус резерва"),
        max_length=12,
        choices=ReservationStatus.choices,
        default=ReservationStatus.NONE,
        db_index=True,
        help_text=_(
            "NONE — резерв не создавался; HELD — удержан; RELEASED — возвращён в "
            "свободный остаток; CONFIRMED — списан (оплата/подтверждение 1С)."
        ),
    )
    exported_at = models.DateTimeField(
        _("Дата выгрузки в 1С"),
        null=True,
        blank=True,
        help_text=_("Момент первого подтверждения приёма заказа в 1С (sync_1c_status=exported)."),
    )
    access_token = models.CharField(
        _("Токен гостевого доступа"),
        max_length=64,
        blank=True,
        db_index=True,
        help_text=_("Для доступа к заказу без логина (гостевое оформление)."),
    )

    class Meta:
        verbose_name = _("Заказ")
        verbose_name_plural = _("Заказы")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Заказ {self.order_number}"

    @property
    def display_status(self) -> str:
        """Производный человекочитаемый статус по таблице раздела 6
        docs/order-lifecycle.md.

        Приоритет: терминальные состояния (отмена/возврат) важнее, затем
        обработка, оплата — подсказкой.
        """
        # Терминальные состояния — выше всего
        if self.payment_status == PaymentStatus.EXPIRED:
            return "Заказ отменён (не оплачен вовремя)"
        if self.fulfillment_status == FulfillmentStatus.CANCELLED:
            return "Заказ отменён"
        if self.payment_status == PaymentStatus.REFUNDED:
            return "Возврат оформлен"

        # Ось обработки
        if self.fulfillment_status == FulfillmentStatus.NEW:
            if self.payment_status == PaymentStatus.PAID:
                return "Оплачен, передаётся в обработку"
            if self.payment_status == PaymentStatus.PENDING:
                return "Ожидает оплаты"
            return "Новый"
        if self.fulfillment_status == FulfillmentStatus.CONFIRMED:
            return "Подтверждён"
        if self.fulfillment_status == FulfillmentStatus.ASSEMBLING:
            return "Собирается"
        if self.fulfillment_status == FulfillmentStatus.READY:
            return "Готов к выдаче"
        if self.fulfillment_status == FulfillmentStatus.SHIPPED:
            return "В доставке"
        if self.fulfillment_status == FulfillmentStatus.COMPLETED:
            return "Выполнен"
        return "Новый"


class OrderItem(TimeStampedModel):
    """Строка заказа — снимок товара и его цены на момент оформления.

    Снимок переживает удаление/изменение товара: ``product`` обнуляется
    (SET_NULL), но текстовые поля и цена остаются.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Заказ"),
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
        verbose_name=_("Товар"),
    )

    # --- Снимок идентификации товара ---
    code_1c = models.CharField(_("Код 1С"), max_length=50, blank=True)
    article = models.CharField(_("Артикул"), max_length=100, blank=True)
    name = models.CharField(_("Название"), max_length=512)
    unit = models.CharField(_("Единица измерения"), max_length=32, blank=True)

    # --- Снимок цены (из PriceResult) ---
    price_base = models.DecimalField(
        _("Базовая цена"), max_digits=14, decimal_places=2, null=True, blank=True
    )
    price_final = models.DecimalField(_("Итоговая цена"), max_digits=14, decimal_places=2)
    discount = models.DecimalField(
        _("Скидка"), max_digits=14, decimal_places=2, null=True, blank=True
    )
    price_type = models.CharField(_("Тип цены"), max_length=16, blank=True)
    currency = models.CharField(_("Валюта"), max_length=3, default="RUB")

    quantity = models.PositiveIntegerField(_("Количество"))
    line_total = models.DecimalField(
        _("Сумма строки"),
        max_digits=14,
        decimal_places=2,
        help_text=_("price_final * quantity."),
    )

    class Meta:
        verbose_name = _("Строка заказа")
        verbose_name_plural = _("Строки заказа")
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.name} × {self.quantity}"


# ---------------------------------------------------------------------------
# Корзина
# ---------------------------------------------------------------------------
class CartStatus(models.TextChoices):
    ACTIVE = "active", _("Активна")
    ORDERED = "ordered", _("Оформлена в заказ")


class Cart(TimeStampedModel):
    """Корзина покупателя (пользователь или гость по session_key).

    После оформления корзина НЕ удаляется физически: переводится в статус
    ``ordered`` (история + идемпотентность повторного оформления).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="carts",
        verbose_name=_("Покупатель"),
    )
    session_key = models.CharField(
        _("Ключ сессии"),
        max_length=40,
        blank=True,
        help_text=_("Для гостевой корзины (анонимный пользователь)."),
    )
    status = models.CharField(
        _("Статус"),
        max_length=10,
        choices=CartStatus.choices,
        default=CartStatus.ACTIVE,
        db_index=True,
    )
    ordered_at = models.DateTimeField(_("Оформлена"), null=True, blank=True)

    class Meta:
        verbose_name = _("Корзина")
        verbose_name_plural = _("Корзины")
        ordering = ["-created_at"]
        constraints = [
            # Не более одной активной корзины на пользователя.
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status="active", user__isnull=False),
                name="uniq_active_cart_per_user",
            ),
            # Не более одной активной корзины на гостевую сессию.
            models.UniqueConstraint(
                fields=["session_key"],
                condition=Q(status="active", user__isnull=True),
                name="uniq_active_cart_per_session",
            ),
        ]

    def __str__(self) -> str:
        owner = self.user_id or f"session:{self.session_key}"
        return f"Корзина #{self.pk} ({owner})"


class CartItem(TimeStampedModel):
    """Строка корзины. Цену НЕ храним — считается на лету через price_for."""

    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Корзина"),
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="cart_items",
        verbose_name=_("Товар"),
    )
    quantity = models.PositiveIntegerField(_("Количество"), default=1)

    # Soft-delete для undo-удаления (#380): строка скрыта из корзины, но может
    # быть восстановлена через POST /api/cart/items/{id}/restore/ пока открыт тост.
    is_deleted = models.BooleanField(_("Удалена (soft)"), default=False, db_index=True)
    deleted_at = models.DateTimeField(_("Дата мягкого удаления"), null=True, blank=True)

    class Meta:
        verbose_name = _("Строка корзины")
        verbose_name_plural = _("Строки корзины")
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product"],
                condition=models.Q(is_deleted=False),
                name="uniq_cart_product_active",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product} × {self.quantity}"
