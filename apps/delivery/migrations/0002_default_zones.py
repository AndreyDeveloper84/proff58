from django.db import migrations


def create_default_zones(apps, schema_editor):
    DeliveryZone = apps.get_model("delivery", "DeliveryZone")
    PickupPoint = apps.get_model("delivery", "PickupPoint")
    DeliveryZone.objects.get_or_create(
        slug="penza-city",
        defaults={
            "name": "Пенза (город)",
            "delivery_type": "courier",
            "price": 300,
            "free_from": 5000,
            "sort_order": 1,
        },
    )
    DeliveryZone.objects.get_or_create(
        slug="penza-region",
        defaults={
            "name": "Пензенская область",
            "delivery_type": "courier",
            "price": 500,
            "free_from": 10000,
            "sort_order": 2,
        },
    )
    DeliveryZone.objects.get_or_create(
        slug="pickup",
        defaults={
            "name": "Самовывоз",
            "delivery_type": "pickup",
            "price": 0,
            "free_from": None,
            "sort_order": 3,
        },
    )
    PickupPoint.objects.get_or_create(
        name="Склад «Профессионал»",
        defaults={
            "address": "г. Пенза, ул. Промышленная, 1",
            "working_hours": "Пн-Пт 9:00-18:00, Сб 10:00-15:00",
        },
    )


def remove_default_zones(apps, schema_editor):
    apps.get_model("delivery", "DeliveryZone").objects.filter(
        slug__in=["penza-city", "penza-region", "pickup"]
    ).delete()
    apps.get_model("delivery", "PickupPoint").objects.filter(name="Склад «Профессионал»").delete()


class Migration(migrations.Migration):
    dependencies = [("delivery", "0001_initial")]
    operations = [migrations.RunPython(create_default_zones, remove_default_zones)]
