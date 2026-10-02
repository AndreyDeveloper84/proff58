"""DRF-2735: «телефон подтверждён» в админке — только для чтения и про номер, а не про аккаунт."""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.accounts.admin import UserAdmin

User = get_user_model()


class _Form:
    def __init__(self, changed):
        self.changed_data = changed


@pytest.fixture
def admin_and_request(db):
    staff = User.objects.create_superuser(phone="+79000000009", password="pwd12345")
    request = RequestFactory().post("/admin/accounts/user/")
    request.user = staff
    return UserAdmin(User, AdminSite()), request


def test_phone_verified_is_readonly(admin_and_request):
    admin_obj, request = admin_and_request
    assert "phone_verified" in admin_obj.get_readonly_fields(request)
    shown = [f for _, opts in admin_obj.get_fieldsets(request, User()) for f in opts["fields"]]
    assert "phone_verified" in shown


def test_changing_phone_drops_verification_and_legacy_chat(admin_and_request):
    """Сотрудник сменил или очистил номер — «подтверждён» к новому значению не относится."""
    admin_obj, request = admin_and_request
    user = User.objects.create_user(
        phone="+79001110000", password=None, phone_verified=True, max_chat_id=555
    )

    user.phone = "+79002220000"
    admin_obj.save_model(request, user, _Form(["phone"]), change=True)

    user.refresh_from_db()
    assert user.phone == "+79002220000"
    assert user.phone_verified is False
    assert user.max_chat_id is None


def test_saving_other_fields_keeps_verification(admin_and_request):
    admin_obj, request = admin_and_request
    user = User.objects.create_user(phone="+79001110001", password=None, phone_verified=True)

    user.full_name = "Иван"
    admin_obj.save_model(request, user, _Form(["full_name"]), change=True)

    user.refresh_from_db()
    assert user.phone_verified is True
