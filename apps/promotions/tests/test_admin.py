"""Админка скидок: колонка «Работает сейчас» и предупреждение о мёртвом контенте.

«Работает сейчас» появилась потому, что ответ приходилось выводить в уме из
галочки и двух дат — и ошибка тут стоит денег: скидка либо не даётся, либо
даётся дольше запланированного.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.admin.sites import AdminSite
from django.utils import timezone

from apps.content.admin import NOT_WIRED_TEMPLATE, ArticleAdmin, BannerAdmin
from apps.content.models import Article, Banner
from apps.promotions.admin import PromotionAdmin
from apps.promotions.models import DiscountType, PromoScope, Promotion


@pytest.fixture
def админ():
    return PromotionAdmin(Promotion, AdminSite())


def _promo(**kwargs):
    defaults = {
        "name": "Скидка",
        "discount_type": DiscountType.PERCENT,
        "discount_value": Decimal("10"),
        "scope": PromoScope.CART,
        "is_active": True,
    }
    defaults.update(kwargs)
    return Promotion(**defaults)


def test_активная_без_дат_работает(админ):
    assert "да" in админ.works_now(_promo())


def test_выключенная_объясняет_причину(админ):
    assert "выключена" in админ.works_now(_promo(is_active=False))


def test_ещё_не_началась(админ):
    promo = _promo(starts_at=timezone.now() + timedelta(days=3))

    text = админ.works_now(promo)

    assert "нет" in text and "начнётся" in text


def test_уже_закончилась(админ):
    promo = _promo(ends_at=timezone.now() - timedelta(days=1))

    text = админ.works_now(promo)

    assert "нет" in text and "закончилась" in text


@pytest.mark.parametrize(
    "тип,значение,ожидание",
    [
        (DiscountType.PERCENT, Decimal("15"), "−15%"),
        (DiscountType.FIXED, Decimal("500"), "−500 ₽"),
        (DiscountType.FREE_DELIVERY, Decimal("0"), "бесплатная доставка"),
    ],
)
def test_выгода_читается_словами(админ, тип, значение, ожидание):
    assert админ.benefit(_promo(discount_type=тип, discount_value=значение)) == ожидание


def test_автоматическая_и_кодовая_различимы(админ):
    assert админ.kind(_promo()) == "автоматически"
    assert "SALE10" in админ.kind(_promo(promo_code="sale10"))


@pytest.mark.parametrize("admin_cls,model", [(ArticleAdmin, Article), (BannerAdmin, Banner)])
def test_неподключённый_контент_предупреждает(admin_cls, model):
    """Витрина apps.content не читает — человек не должен заполнять его вслепую."""
    assert admin_cls(model, AdminSite()).change_list_template == NOT_WIRED_TEMPLATE
