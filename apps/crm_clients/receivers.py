"""Подписчики событий для CRM-клиентов.

Подключаются в AppConfig.ready() только при включённом feature flag `crm`.
"""

import logging

from apps.core import events

from .models import ClientProfile, Interaction, InteractionType

logger = logging.getLogger(__name__)


def _on_user_registered(sender, user_id, **kwargs):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return
    profile, created = ClientProfile.objects.get_or_create(user=user)
    if created:
        Interaction.objects.create(
            client=profile,
            interaction_type=InteractionType.REGISTRATION,
            summary=f"Регистрация: {user.phone}",
        )
        logger.info("CRM: created client profile for user=%s", user_id)


def _on_order_created(sender, order_id, **kwargs):
    logger.info("CRM: order_created received, order_id=%s (handler stub)", order_id)


events.user_registered.connect(_on_user_registered, dispatch_uid="crm_clients_user_registered")
events.order_created.connect(_on_order_created, dispatch_uid="crm_clients_order_created")
