from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_user_inactivity_warning_accountdeletionaudit"),
    ]

    operations = [
        migrations.AlterField(
            model_name="accountdeletionaudit",
            name="reason",
            field=models.CharField(
                choices=[
                    ("user_request", "Запрос пользователя"),
                    ("inactivity", "Длительная неактивность"),
                    ("restore_reconcile", "Повтор после восстановления"),
                ],
                max_length=20,
            ),
        ),
    ]
