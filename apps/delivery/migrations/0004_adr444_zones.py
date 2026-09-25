"""#429 (M-05, ADR #444): привести зоны доставки к утверждённому контракту.

- Пенза (курьер): порог бесплатной доставки 5000 → 7000, цена 300 → 500.
- Пензенская область: делаем внешней зоной (СДЭК) — цена по API, порога нет.
"""

from django.db import migrations


def apply_adr(apps, schema_editor):
    DeliveryZone = apps.get_model("delivery", "DeliveryZone")

    DeliveryZone.objects.filter(slug="penza-city").update(
        name="Пенза (курьер)", price=500, free_from=7000, is_external=False
    )
    DeliveryZone.objects.filter(slug="penza-region").update(
        name="Пензенская область (СДЭК)", price=0, free_from=None, is_external=True
    )


def revert_adr(apps, schema_editor):
    DeliveryZone = apps.get_model("delivery", "DeliveryZone")
    DeliveryZone.objects.filter(slug="penza-city").update(
        name="Пенза (город)", price=300, free_from=5000, is_external=False
    )
    DeliveryZone.objects.filter(slug="penza-region").update(
        name="Пензенская область", price=500, free_from=10000, is_external=False
    )


class Migration(migrations.Migration):
    dependencies = [("delivery", "0003_deliveryzone_is_external")]
    operations = [migrations.RunPython(apply_adr, revert_adr)]
