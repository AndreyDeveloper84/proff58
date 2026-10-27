# Метка времени ручной отметки «Хит продаж»: среди ручных хитов витрина ставит
# первым последний отмеченный (apps.catalog.sales.bestsellers_queryset).
# Уже отмеченным товарам даём одну общую метку «сейчас»: между собой они
# остаются в прежнем (алфавитном) порядке, а всё, что отметят после миграции,
# встанет впереди них.

from django.db import migrations, models
from django.utils import timezone


def backfill_hit_manual_at(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    Product.objects.filter(is_hit_manual=True, hit_manual_at__isnull=True).update(
        hit_manual_at=timezone.now()
    )


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0046_package_dimensions"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="hit_manual_at",
            field=models.DateTimeField(
                blank=True,
                editable=False,
                help_text="Когда поставили галочку «Хит продаж (вручную)». Последний отмеченный идёт в блоке главной первым.",
                null=True,
                verbose_name="Отмечен хитом",
            ),
        ),
        migrations.RunPython(backfill_hit_manual_at, migrations.RunPython.noop),
    ]
