"""#421 (B-01): нормализовать customer_phone у существующих заказов.

Приводит уже сохранённые номера к канону (+7XXXXXXXXXX), чтобы claim гостевых
заказов по verified-телефону находил их независимо от исходного формата ввода.
"""

from django.db import migrations


def _normalize_phones(apps, schema_editor):
    from apps.accounts.phone import normalize_phone

    Order = apps.get_model("orders", "Order")
    to_update = []
    for order in Order.objects.exclude(customer_phone="").only("id", "customer_phone").iterator():
        canon = normalize_phone(order.customer_phone)
        if canon != order.customer_phone:
            order.customer_phone = canon
            to_update.append(order)
    if to_update:
        Order.objects.bulk_update(to_update, ["customer_phone"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0004_cartitem_soft_delete"),
        ("accounts", "0005_user_phone_verified"),
    ]

    operations = [
        migrations.RunPython(_normalize_phones, migrations.RunPython.noop),
    ]
