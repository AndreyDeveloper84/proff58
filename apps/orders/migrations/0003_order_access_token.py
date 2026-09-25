from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0002_order_exported_at_order_external_order_number_and_more")]
    operations = [
        migrations.AddField(
            model_name="order",
            name="access_token",
            field=models.CharField(
                blank=True, db_index=True, max_length=64, verbose_name="Токен гостевого доступа"
            ),
        ),
    ]
