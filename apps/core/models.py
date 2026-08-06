"""Модели ядра: базовые абстракции и конфигурация экземпляра магазина.

`SiteSettings` — singleton с настройками конкретного магазина (бренд, контакты,
реквизиты, регион) и бизнес-feature-флагами. Доступ к флагам — только через
`apps.core.features.is_enabled()`, не напрямую к полям.
"""

from __future__ import annotations

from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

#: HEX-цвет вида #RRGGBB
hex_color_validator = RegexValidator(
    r"^#[0-9A-Fa-f]{6}$", message=_("Цвет должен быть в формате #RRGGBB")
)


class TimeStampedModel(models.Model):
    """Абстрактная база с временными метками создания/обновления.

    Поля намеренно без verbose_name — чтобы перевод существующих моделей на эту
    базу не порождал миграции изменения метаданных.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SiteSettings(TimeStampedModel):
    """Настройки конкретного экземпляра магазина. Singleton (всегда pk=1).

    Всё, что отличает один магазин от другого (бренд, контакты, включённые
    бизнес-модули), живёт здесь, а не в коде.
    """

    # --- Бренд ---
    name = models.CharField(_("Название магазина"), max_length=200, default="Профессионал")
    logo = models.ImageField(_("Логотип"), upload_to="branding/", blank=True)
    primary_color = models.CharField(
        _("Основной цвет"), max_length=7, default="#00A14B", validators=[hex_color_validator]
    )
    accent_color = models.CharField(
        _("Акцентный цвет"), max_length=7, default="#B5E61D", validators=[hex_color_validator]
    )

    # --- Контакты, реквизиты, регион ---
    contacts = models.JSONField(_("Контакты"), default=dict, blank=True)
    requisites = models.JSONField(
        _("Реквизиты"),
        default=dict,
        blank=True,
        help_text=_(
            "Реквизиты поставщика для счетов B2B. Ключи: company_name, inn, kpp, ogrn, "
            "address, phone, bank_name, bank_bik, bank_account, bank_corr_account, "
            "director, accountant. Без банковских полей счёт нельзя оплатить — "
            "покупателю не из чего заполнить платёжное поручение."
        ),
    )
    region = models.CharField(_("Регион"), max_length=100, default="Пенза")

    # --- Бизнес-feature-флаги (переключаются администратором) ---
    reviews_enabled = models.BooleanField(_("Отзывы"), default=False)
    b2b_enabled = models.BooleanField(_("B2B-кабинет"), default=True)
    promotions_enabled = models.BooleanField(_("Акции"), default=False)
    articles_enabled = models.BooleanField(_("Статьи/новости"), default=False)
    max_chat_enabled = models.BooleanField(_("MAX-чат"), default=False)
    ai_assist_enabled = models.BooleanField(_("AI-консультант"), default=False)
    video_reviews_enabled = models.BooleanField(_("Видеообзоры"), default=False)

    class Meta:
        verbose_name = _("Настройки сайта")
        verbose_name_plural = _("Настройки сайта")

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.pk = 1  # singleton: всегда одна запись
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> SiteSettings:
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj
