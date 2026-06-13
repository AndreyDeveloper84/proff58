import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import CustomerType

User = get_user_model()


@pytest.mark.django_db
def test_create_user_by_phone():
    user = User.objects.create_user(phone="+79000000001", password="pwd12345")
    assert user.phone == "+79000000001"
    assert user.customer_type == CustomerType.B2C
    assert user.is_b2b is False
    assert user.check_password("pwd12345")


@pytest.mark.django_db
def test_create_b2b_user():
    user = User.objects.create_user(
        phone="+79000000002", password="pwd12345", customer_type=CustomerType.B2B
    )
    assert user.is_b2b is True


@pytest.mark.django_db
def test_create_user_requires_phone():
    with pytest.raises(ValueError):
        User.objects.create_user(phone="", password="pwd12345")


@pytest.mark.django_db
def test_create_superuser():
    admin = User.objects.create_superuser(phone="+79000000003", password="pwd12345")
    assert admin.is_staff is True
    assert admin.is_superuser is True
