from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="user",
            name="max_chat_id",
            field=models.BigIntegerField(
                blank=True,
                db_index=True,
                null=True,
                unique=True,
                verbose_name="MAX chat ID",
            ),
        ),
    ]
