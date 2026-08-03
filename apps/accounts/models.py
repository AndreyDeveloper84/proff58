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
    """Покупатель или сотрудник.

    Вход на витрине — по e-mail с паролем либо через MAX. Телефон логином НЕ
    является: он остаётся контактом (курьеру звонить, 1С выгружает его в заказе)
    и идентификатором для MAX, который знает человека именно по номеру.

    Поэтому телефон необязателен: регистрация по почте его не спрашивает, а
    аккаунт, заведённый через MAX, наоборот приходит с номером, но без почты.
    ``USERNAME_FIELD`` остаётся телефоном — это техническое поле для админки и
    ``createsuperuser``; витринный вход делает EmailBackend (auth_backends.py).
    """

    # unique + null: пустых телефонов может быть сколько угодно (Postgres не
    # считает NULL равными), а заполненный остаётся уникальным.
    phone = models.CharField(_("Телефон"), max_length=20, unique=True, null=True, blank=True)
    # Уникальность среди заполненных — частичным индексом в Meta.constraints:
    # у аккаунтов из MAX почты нет, и пустые значения конфликтовать не должны.
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
    # #421 (B-01): владение номером подтверждено (OTP через MAX). Только для
    # verified-номера разрешён claim гостевых заказов — иначе регистрация чужого
    # незанятого номера захватила бы историю заказов жертвы.
    phone_verified = models.BooleanField(_("Телефон подтверждён"), default=False)

    is_staff = models.BooleanField(_("Доступ в админку"), default=False)
    is_active = models.BooleanField(_("Активен"), default=True)
    date_joined = models.DateTimeField(_("Дата регистрации"), default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = _("Пользователь")
        verbose_name_plural = _("Пользователи")
        constraints = [
            # E-mail — логин витрины, поэтому двух одинаковых быть не может.
            # Условие исключает пустые: аккаунты из MAX заводятся без почты.
            models.UniqueConstraint(
                fields=["email"],
                condition=~models.Q(email=""),
                name="accounts_user_unique_email",
            ),
        ]

    def __str__(self) -> str:
        return self.full_name or self.email or self.phone or f"Пользователь #{self.pk}"

    @property
    def is_b2b(self) -> bool:
        return self.customer_type == CustomerType.B2B

    @property
    def is_b2b_verified(self) -> bool:
        """True только для B2B с подтверждённой верификацией менеджером."""
        try:
            return self.is_b2b and self.profile.is_b2b_verified
        except Profile.DoesNotExist:
            return False


class Profile(TimeStampedModel):
    """Дополнительные данные покупателя.

    Реквизиты заполняются для B2B и используются при выставлении счёта.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    company_name = models.CharField(_("Название организации"), max_length=255, blank=True)
    inn = models.CharField(_("ИНН"), max_length=12, blank=True)
    kpp = models.CharField(_("КПП"), max_length=9, blank=True)
    legal_address = models.CharField(_("Юридический адрес"), max_length=512, blank=True)
    is_b2b_verified = models.BooleanField(_("B2B верифицирован"), default=False)
    pd_consent_at = models.DateTimeField(_("Согласие ПДн"), null=True, blank=True)
    pd_consent_version = models.CharField(_("Версия политики ПДн"), max_length=32, blank=True)

    class Meta:
        verbose_name = _("Профиль")
        verbose_name_plural = _("Профили")

    def __str__(self) -> str:
        return f"Профиль {self.user}"


# #433 (M-10): WishlistItem вынесен в отдельный модуль. Импортируем его здесь,
# чтобы модель регистрировалась при загрузке app (иначе reverse-аксессор
# ``user.wishlist`` и makemigrations «не видят» модель до первого lazy-import,
# и чистый GET /wishlist/ после логина падал 500).
from apps.accounts.wishlist import WishlistItem  # noqa: E402,F401
