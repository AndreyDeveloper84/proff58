"""Тесты CRM-каркаса (#63)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from apps.core import events
from apps.core.features import is_enabled

from .models import ClientProfile, Interaction, InteractionType

User = get_user_model()


# ═══════════════════════════════════════════════════════════════════════
# 1. Feature flag: CRM отключена по умолчанию
# ═══════════════════════════════════════════════════════════════════════


def test_crm_disabled_by_default():
    assert is_enabled("crm") is False


@override_settings(FEATURES={"crm": True})
def test_crm_enabled_via_env():
    assert is_enabled("crm") is True


# ═══════════════════════════════════════════════════════════════════════
# 2. Модели создаются и работают даже при выключенном CRM
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_client_profile_creation():
    user = User.objects.create_user(phone="+79001111111", password="pass")
    profile = ClientProfile.objects.create(user=user, source="website")
    assert str(profile) == f"CRM: {user}"
    assert profile.tags == []


@pytest.mark.django_db
def test_interaction_creation():
    user = User.objects.create_user(phone="+79002222222", password="pass")
    profile = ClientProfile.objects.create(user=user)
    interaction = Interaction.objects.create(
        client=profile,
        interaction_type=InteractionType.ORDER,
        summary="Заказ #42 оформлен",
        metadata={"order_id": 42},
    )
    assert interaction.created_at is not None
    assert profile.interactions.count() == 1


# ═══════════════════════════════════════════════════════════════════════
# 3. Receiver: user_registered создаёт профиль (при включённом CRM)
# ═══════════════════════════════════════════════════════════════════════


@override_settings(FEATURES={"crm": True})
@pytest.mark.django_db
def test_user_registered_creates_profile(django_capture_on_commit_callbacks):
    from . import receivers  # noqa: F401 — подключить обработчики

    user = User.objects.create_user(phone="+79003333333", password="pass")
    events.user_registered.send(sender=User, user_id=user.pk)

    assert ClientProfile.objects.filter(user=user).exists()
    profile = ClientProfile.objects.get(user=user)
    assert profile.interactions.filter(interaction_type=InteractionType.REGISTRATION).exists()


@override_settings(FEATURES={"crm": True})
@pytest.mark.django_db
def test_user_registered_idempotent():
    from . import receivers  # noqa: F401

    user = User.objects.create_user(phone="+79004444444", password="pass")
    events.user_registered.send(sender=User, user_id=user.pk)
    events.user_registered.send(sender=User, user_id=user.pk)
    assert ClientProfile.objects.filter(user=user).count() == 1


# ═══════════════════════════════════════════════════════════════════════
# 4. CRM не влияет на checkout/catalog
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_catalog_works_without_crm():
    from apps.catalog.models import Product

    p = Product.objects.create(name="Дрель")
    assert p.pk is not None


@pytest.mark.django_db
def test_crm_tables_empty_by_default():
    assert ClientProfile.objects.count() == 0
    assert Interaction.objects.count() == 0


# ═══════════════════════════════════════════════════════════════════════
# 5. Deal и Task модели
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_deal_creation():
    from apps.crm_sales.models import Deal, DealStage

    deal = Deal.objects.create(title="Заказ B2B #10", amount=50000)
    assert deal.stage == DealStage.NEW
    assert str(deal) == "Заказ B2B #10"


@pytest.mark.django_db
def test_task_creation():
    from apps.crm_tasks.models import Task, TaskStatus

    task = Task.objects.create(title="Перезвонить клиенту")
    assert task.status == TaskStatus.OPEN
    assert str(task) == "Перезвонить клиенту"
