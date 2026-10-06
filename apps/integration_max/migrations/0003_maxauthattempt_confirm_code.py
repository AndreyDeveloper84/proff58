# DRF-2740: код подтверждения входа через MAX вводится на сайте.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("integration_max", "0002_maxauthattempt_order_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="maxauthattempt",
            name="confirm_code_hash",
            field=models.CharField(
                blank=True, max_length=64, verbose_name="Хэш кода подтверждения"
            ),
        ),
        migrations.AddField(
            model_name="maxauthattempt",
            name="confirm_failures",
            field=models.PositiveSmallIntegerField(default=0, verbose_name="Неверных кодов"),
        ),
        migrations.AddField(
            model_name="maxauthattempt",
            name="code_issues",
            field=models.PositiveSmallIntegerField(default=0, verbose_name="Выдач кода"),
        ),
        migrations.AddField(
            model_name="maxauthattempt",
            name="code_issued_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Код выдан"),
        ),
    ]
