from django.db import migrations, models
from django.db.models import F


def backfill_webhook_payload_at(apps, schema_editor):
    Payment = apps.get_model("payments", "Payment")
    Payment.objects.exclude(webhook_payload={}).filter(
        webhook_payload_at__isnull=True
    ).update(webhook_payload_at=F("updated_at"))


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0004_refundrequest"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="webhook_payload_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Точка отсчёта retention для диагностического callback snapshot.",
                null=True,
                verbose_name="Когда сохранён webhook payload",
            ),
        ),
        migrations.RunPython(backfill_webhook_payload_at, migrations.RunPython.noop),
    ]
