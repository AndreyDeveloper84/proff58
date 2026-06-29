"""Модели пользователей и профилей.

Магазин обслуживает два типа покупателей:
- B2C — физические лица;
- B2B — юридические лица и ИП (нужны реквизиты для счёта).

Тип покупателя определяет витрину (цены, доступность опта) и сценарий
оформления заказа (онлайн-оплата против счёта).
"""

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

from .managers import UserManager


class CustomerType(models.TextChoices):
    B2C = "b2c", _("Физическое лицо (B2C)")
    B2B = "b2b", _("Юридическое лицо / ИП (B2B)")


class User(AbstractBaseUser, PermissionsMixin):
    """Пользователь с входом по телефону или e-mail."""

    phone = models.CharField(_("Телефон"), max_length=20, unique=True)
    email = models.EmailField(_("E-mail"), blank=True)
    full_name = models.CharField(_("ФИО"), max_length=255, blank=True)
    customer_type = models.CharField(
        _("Тип покупателя"),
        max_length=3,
        choices=CustomerType.choices,
        default=CustomerType.B2C,
    )

    max_chat_id = models.BigIntegerField(
        _("MAX chat ID"),
        null=True,
        blank=True,
        unique=True,
        db_index=True,
    )

    is_staff = models.BooleanField(_("Доступ в админку"), default=False)
    is_active = models.BooleanField(_("Активен"), default=True)
    date_joined = models.DateTimeField(_("Дата регистрации"), default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = _("Пользователь")
        verbose_name_plural = _("Пользователи")

    def __str__(self) -> str:
        return self.full_name or self.phone

    @property
    def is_b2b(self) -> bool:
        return self.customer_type == CustomerType.B2B


class Profile(TimeStampedModel):
    """Дополнительные данные покупателя.

    Реквизиты заполняются для B2B и используются при выставлении счёта.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    company_name = models.CharField(_("Название организации"), max_length=255, blank=True)
    inn = models.CharField(_("ИНН"), max_length=12, blank=True)
    kpp = models.CharField(_("КПП"), max_length=9, blank=True)
    legal_address = models.CharField(_("Юридический адрес"), max_length=512, blank=True)

    class Meta:
        verbose_name = _("Профиль")
        verbose_name_plural = _("Профили")

    def __str__(self) -> str:
        return f"Профиль {self.user}"
