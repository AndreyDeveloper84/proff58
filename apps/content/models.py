"""Контент магазина: SEO-страницы, статьи, акции, баннеры (#71).

Каждая подсистема — отдельная модель. Черновики не видны на витрине.
Контент-менеджер работает через admin без shell.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class PublishStatus(models.TextChoices):
    DRAFT = "draft", _("Черновик")
    PUBLISHED = "published", _("Опубликовано")


class SEOPage(TimeStampedModel):
    """Статическая SEO-страница (about, delivery, warranty и т.п.)."""

    slug = models.SlugField(_("Slug"), max_length=100, unique=True)
    title = models.CharField(_("Заголовок"), max_length=255)
    meta_title = models.CharField(_("meta title"), max_length=255, blank=True)
    meta_description = models.TextField(_("meta description"), blank=True)
    body = models.TextField(_("Содержимое"), blank=True)
    status = models.CharField(
        _("Статус"),
        max_length=20,
        choices=PublishStatus.choices,
        default=PublishStatus.DRAFT,
        db_index=True,
    )

    class Meta:
        verbose_name = _("SEO-страница")
        verbose_name_plural = _("SEO-страницы")
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.title

    @property
    def is_published(self) -> bool:
        return self.status == PublishStatus.PUBLISHED


class Article(TimeStampedModel):
    """Новость или статья."""

    slug = models.SlugField(_("Slug"), max_length=150, unique=True)
    title = models.CharField(_("Заголовок"), max_length=255)
    meta_title = models.CharField(_("meta title"), max_length=255, blank=True)
    meta_description = models.TextField(_("meta description"), blank=True)
    excerpt = models.TextField(_("Анонс"), blank=True)
    body = models.TextField(_("Содержимое"), blank=True)
    cover = models.ImageField(_("Обложка"), upload_to="articles/", blank=True)
    published_at = models.DateTimeField(_("Дата публикации"), null=True, blank=True)
    status = models.CharField(
        _("Статус"),
        max_length=20,
        choices=PublishStatus.choices,
        default=PublishStatus.DRAFT,
        db_index=True,
    )

    class Meta:
        verbose_name = _("Статья")
        verbose_name_plural = _("Статьи")
        ordering = ["-published_at", "-created_at"]

    def __str__(self) -> str:
        return self.title

    @property
    def is_published(self) -> bool:
        return self.status == PublishStatus.PUBLISHED


class Promotion(TimeStampedModel):
    """Акция (контентная часть; ценовые правила — в pricing)."""

    slug = models.SlugField(_("Slug"), max_length=150, unique=True)
    title = models.CharField(_("Название акции"), max_length=255)
    description = models.TextField(_("Описание"), blank=True)
    cover = models.ImageField(_("Баннер акции"), upload_to="promotions/", blank=True)
    starts_at = models.DateTimeField(_("Начало"), null=True, blank=True)
    ends_at = models.DateTimeField(_("Конец"), null=True, blank=True)
    status = models.CharField(
        _("Статус"),
        max_length=20,
        choices=PublishStatus.choices,
        default=PublishStatus.DRAFT,
        db_index=True,
    )

    class Meta:
        # Дубль-ловушка: скидочная механика — это promotions.Promotion («Скидки и
        # промокоды»). Здесь только страница-рассказ об акции на витрине, ценами
        # она не управляет — поэтому в названии это сказано прямо.
        verbose_name = _("Страница акции")
        verbose_name_plural = _("Страницы акций (без скидок)")
        ordering = ["-starts_at", "-created_at"]

    def __str__(self) -> str:
        return self.title

    @property
    def is_published(self) -> bool:
        return self.status == PublishStatus.PUBLISHED


class BannerTarget(models.TextChoices):
    HOME = "home", _("Главная")
    CATALOG = "catalog", _("Каталог")
    ALL = "all", _("Везде")


class Banner(TimeStampedModel):
    """Баннер с таргетингом на страницы/категории."""

    title = models.CharField(_("Название"), max_length=255)
    image = models.ImageField(_("Изображение"), upload_to="banners/")
    link = models.CharField(_("Ссылка"), max_length=500, blank=True)
    alt = models.CharField(_("Alt-текст"), max_length=255, blank=True)
    target = models.CharField(
        _("Цель размещения"),
        max_length=20,
        choices=BannerTarget.choices,
        default=BannerTarget.HOME,
        db_index=True,
    )
    sort_order = models.PositiveIntegerField(_("Порядок"), default=0)
    status = models.CharField(
        _("Статус"),
        max_length=20,
        choices=PublishStatus.choices,
        default=PublishStatus.DRAFT,
        db_index=True,
    )

    class Meta:
        verbose_name = _("Баннер")
        verbose_name_plural = _("Баннеры")
        ordering = ["sort_order", "-created_at"]

    def __str__(self) -> str:
        return self.title

    @property
    def is_published(self) -> bool:
        return self.status == PublishStatus.PUBLISHED
