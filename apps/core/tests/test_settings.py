"""Тесты SiteSettings (singleton) и TimeStampedModel (#59)."""

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import Profile, User
from apps.catalog.models import Product
from apps.core.models import SiteSettings


@pytest.mark.django_db
def test_site_settings_is_singleton():
    a = SiteSettings.get_solo()
    a.name = "Магазин-1"
    a.save()
    b = SiteSettings.get_solo()
    b.name = "Магазин-2"
    b.save()

    assert SiteSettings.objects.count() == 1
    assert a.pk == 1 and b.pk == 1
    assert SiteSettings.get_solo().name == "Магазин-2"


@pytest.mark.django_db
def test_site_settings_defaults():
    s = SiteSettings.get_solo()
    assert s.name == "Профессионал"
    assert s.region == "Пенза"
    assert s.contacts == {} and s.requisites == {}
    assert s.b2b_enabled is True
    assert s.reviews_enabled is False


@pytest.mark.django_db
def test_hex_color_validator_rejects_garbage():
    s = SiteSettings.get_solo()
    s.primary_color = "green123"
    with pytest.raises(ValidationError):
        s.full_clean()


@pytest.mark.django_db
def test_timestamped_applied_to_product_and_profile():
    p = Product.objects.create(name="Дрель")
    assert p.created_at is not None and p.updated_at is not None

    user = User.objects.create_user(phone="+79991230000", password="pwd12345")
    profile = Profile.objects.create(user=user)
    assert profile.created_at is not None and profile.updated_at is not None
