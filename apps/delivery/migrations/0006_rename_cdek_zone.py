"""DRF-2491: зона СДЭК возит по всей России — имя «Пензенская область (СДЭК)» устарело.

Переименовываем, только если имя не правили в админке: чужую правку не затираем.
"""

from django.db import migrations

OLD_NAME = "Пензенская область (СДЭК)"
NEW_NAME = "СДЭК по России"


def rename(apps, schema_editor):
    DeliveryZone = apps.get_model("delivery", "DeliveryZone")
    DeliveryZone.objects.filter(slug="penza-region", name=OLD_NAME).update(name=NEW_NAME)


def unrename(apps, schema_editor):
    DeliveryZone = apps.get_model("delivery", "DeliveryZone")
    DeliveryZone.objects.filter(slug="penza-region", name=NEW_NAME).update(name=OLD_NAME)


class Migration(migrations.Migration):
    dependencies = [
        ("delivery", "0005_deliveryslot_deliveryslot_uniq_delivery_slot_window_and_more")
    ]
    operations = [migrations.RunPython(rename, unrename)]
