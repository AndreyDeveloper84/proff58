"""Модели оплаты — Payment и связь с заказом (#8)."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class PaymentProvider(models.TextChoices):
    """Касса, через которую идут деньги. Действующая — АТОЛ Pay."""

    ATOLPAY = "atolpay", _("АТОЛ Pay")
    YOOKASSA = "yookassa", _("ЮKassa")


class PaymentMethod(models.TextChoices):
    ATOLPAY = "atolpay", _("АТОЛ Pay (карта/СБП)")
    YOOKASSA = "yookassa", _("ЮKassa (карта/СБП)")
    INVOICE = "invoice", _("Счёт (B2B)")
    CASH = "cash", _("При получении")


class PaymentStatus(models.TextChoices):
    PENDING = "pending", _("Ожидает оплаты")
    WAITING_CAPTURE = "waiting_for_capture", _("Ожидает подтверждения")
    SUCCEEDED = "succeeded", _("Оплачен")
    CANCELED = "canceled", _("Отменён")
    PARTIALLY_REFUNDED = "partially_refunded", _("Частично возвращён")
    REFUNDED = "refunded", _("Возвращён")


class Payment(TimeStampedModel):
    """Платёж — привязан к заказу, хранит данные кассы.

    Поля провайдер-агностичны: ``provider`` называет кассу, ``provider_order_id`` —
    идентификатор, который касса знает под нашим номером заказа (у АТОЛ Pay это
    единственный ключ платежа: своего id он не выдаёт), ``provider_payment_id`` —
    идентификатор на стороне кассы (у ЮKassa свой, у АТОЛ равен orderId).
    """

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name=_("Заказ"),
    )
    provider = models.CharField(
        _("Касса"),
        max_length=16,
        choices=PaymentProvider.choices,
        default=PaymentProvider.ATOLPAY,
        db_index=True,
    )
    provider_payment_id = models.CharField(
        _("ID платежа в кассе"),
        max_length=64,
        unique=True,
        null=True,
        blank=True,
    )
    provider_order_id = models.CharField(
        _("Номер заказа для кассы"),
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        help_text=_(
            "orderId, отправленный в кассу. Только ASCII: номер заказа с кириллической «П» "
            "касса не принимает, поэтому у платежа свой идентификатор."
        ),
    )
    method = models.CharField(
        _("Способ оплаты"),
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.ATOLPAY,
    )
    status = models.CharField(
        _("Статус"),
        max_length=24,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    amount = models.DecimalField(_("Сумма"), max_digits=14, decimal_places=2)
    currency = models.CharField(_("Валюта"), max_length=3, default="RUB")
    confirmation_url = models.URLField(_("URL оплаты"), blank=True)
    idempotency_key = models.CharField(
        _("Ключ идемпотентности"),
        max_length=64,
        unique=True,
    )
    webhook_payload = models.JSONField(
        _("Последний webhook payload"),
        default=dict,
        blank=True,
    )
    paid_at = models.DateTimeField(_("Дата оплаты"), null=True, blank=True)

    # --- Фискализация (54-ФЗ). Чек пробивает касса по данным из регистрации
    # платежа и отдельным callback (type=fiscal) сообщает результат. Неуспешный
    # чек транзакцию НЕ отменяет — деньги приняты, разбирается менеджер. ---
    receipt_id = models.CharField(_("ID чека"), max_length=64, blank=True)
    receipt_status = models.CharField(
        _("Статус фискализации"),
        max_length=16,
        blank=True,
        help_text=_("success / fail — из callback type=fiscal."),
    )
    receipt_error = models.TextField(_("Ошибка фискализации"), blank=True)

    class Meta:
        verbose_name = _("Платёж")
        verbose_name_plural = _("Платежи")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Платёж {self.provider_order_id or self.provider_payment_id or self.pk} [{self.status}]"


class RefundStatus(models.TextChoices):
    PENDING = "pending", _("В обработке")
    SUCCEEDED = "succeeded", _("Выполнен")
    FAILED = "failed", _("Ошибка")


class Refund(TimeStampedModel):
    """Ledger возвратов (#437, m-01/m-02).

    Каждый частичный возврат — отдельная строка. Статус платежа/заказа —
    производное от суммы успешных возвратов (см. payments.services.refund).
    """

    payment = models.ForeignKey(
        Payment, on_delete=models.CASCADE, related_name="refunds", verbose_name=_("Платёж")
    )
    amount = models.DecimalField(_("Сумма возврата"), max_digits=14, decimal_places=2)
    currency = models.CharField(_("Валюта"), max_length=3, default="RUB")
    status = models.CharField(
        _("Статус"), max_length=12, choices=RefundStatus.choices, default=RefundStatus.PENDING
    )
    provider_refund_id = models.CharField(_("ID возврата в кассе"), max_length=64, blank=True)
    idempotency_key = models.CharField(_("Ключ идемпотентности"), max_length=80, unique=True)
    error_message = models.TextField(_("Ошибка"), blank=True)

    class Meta:
        verbose_name = _("Возврат")
        verbose_name_plural = _("Возвраты")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Возврат {self.amount} по платежу {self.payment_id} [{self.status}]"
